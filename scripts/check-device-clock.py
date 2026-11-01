"""Physical delayed-clock/reboot check. No model calls or synthetic wall-clock jumps.

Run with the owned voice service disconnected; restore it in the caller's finally.
The child serves authenticated pinned OTA only. Device care state is preserved.
"""
import argparse
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
FOLDER=ROOT/'.runtime/clock-check'


def configuration():
    return json.loads((ROOT/'.tools/upstream/xiaozhi-esp32-server/main/xiaozhi-server/data/.config.yaml').read_text(encoding='utf-8'))


async def serve(config):
    from aiohttp import web
    import websockets
    server=ROOT/'.tools/upstream/xiaozhi-esp32-server/main/xiaozhi-server'
    sys.path.insert(0,str(server))
    from core.api.ota_handler import OTAHandler
    from core.auth import AuthManager
    from core.pet_network import device_allowed
    ota=OTAHandler(config)
    empty=FOLDER/'empty-bin';empty.mkdir(exist_ok=True);ota.bin_dir=str(empty)
    async def discovery(request):
        response=await ota.handle_post(request)
        if response.status!=200:return response
        value=json.loads(response.text)
        if not (FOLDER/'allow-time').exists():value.pop('server_time',None)
        return web.json_response(value)
    app=web.Application();app.router.add_post('/xiaozhi/ota/',discovery)
    runner=web.AppRunner(app);await runner.setup()
    auth=AuthManager(config['server']['auth_key'],config['server'].get('auth',{}).get('expire_seconds'))
    async def voice(ws):
        headers=ws.request.headers;token=headers.get('Authorization','')
        if (not device_allowed(headers,config) or not token.startswith('Bearer ') or
                not auth.verify_token(token[7:],headers.get('Client-ID',''),headers.get('Device-ID',''))):
            await ws.close(code=1008);return
        import asyncio
        hello=json.loads(await asyncio.wait_for(ws.recv(),5))
        if hello.get('type')!='hello':await ws.close(code=1008);return
        await ws.send(json.dumps({'type':'hello','version':1,'transport':'websocket','session_id':'clock-fixture',
            'audio_params':{'format':'opus','sample_rate':24000,'channels':1,'frame_duration':60}}))
        await asyncio.sleep(.5)
        await ws.close()
    try:
        await web.TCPSite(runner,config['server']['ip'],8003).start()
        import asyncio
        async with websockets.serve(voice,config['server']['ip'],8000,ping_interval=None):
            (FOLDER/'ready').write_text('ready',encoding='ascii')
            await asyncio.Future()
    finally:await runner.cleanup()


def main():
    import serial
    from device_command import analyze
    config=configuration();FOLDER.mkdir(parents=True,exist_ok=True)
    ready=FOLDER/'ready';allow=FOLDER/'allow-time'
    ready.unlink(missing_ok=True);allow.unlink(missing_ok=True)
    build=json.loads((ROOT/'evaluation/firmware-build.json').read_text(encoding='utf-8'))
    flash=json.loads((ROOT/'evaluation/device-flash.json').read_text(encoding='utf-8'))
    if not flash.get('app_readback_verified') or build['app_sha256']!=flash['app_sha256']:
        raise ValueError('VERIFIED_IMAGE_REQUIRED')
    for number in (8000,8003):
        with socket.socket() as probe:probe.bind((config['server']['ip'],number))
    result={'ok':False,'app_sha256':build['app_sha256'],'source':'physical_USB_and_authenticated_OTA',
            'model_called':False,'synthetic_clock_jump':False,'power_loss_fault_injection':False}
    raw=bytearray();child=None
    port=serial.Serial(port=None,baudrate=115200,timeout=.1,write_timeout=2)
    port.dtr=False;port.rts=False;port.port='COM4'
    def drain(seconds):
        end=time.monotonic()+seconds
        while time.monotonic()<end:raw.extend(port.read(min(max(port.in_waiting,1),4096)))
    def state():
        offset=len(raw);port.write(b'pet.state\n');port.flush();drain(2)
        value=analyze('state',raw[offset:].decode('utf-8',errors='replace'))
        if not value['ok']:raise ValueError('STATE_UNAVAILABLE')
        return value['state']
    def reset():
        if port.is_open:port.close()
        with (FOLDER/'reset.log').open('wb') as log:
            subprocess.run([sys.executable,'-m','esptool','--chip','esp32s3','--port','COM4',
                '--before','usb_reset','--after','hard_reset','chip_id'],cwd=ROOT,
                stdout=log,stderr=log,check=True,timeout=20)
        port.open();drain(12)
    def sync():
        allow.write_text('UTC allowed',encoding='ascii')
        port.write(b'pet.main\n');port.flush();drain(8)
        value=state()
        if not value['time_trusted'] or value['offline_catchup_pending']:
            raise ValueError('CLOCK_NOT_RECONCILED')
        return value
    try:
        with (FOLDER/'server.log').open('wb') as log:
            child=subprocess.Popen([str(ROOT/'.tools/voice-venv/Scripts/python.exe'),__file__,'--serve'],
                cwd=ROOT,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            end=time.monotonic()+15
            while not ready.exists():
                if child.poll() is not None or time.monotonic()>end:raise ValueError('FIXTURE_NOT_READY')
                time.sleep(.1)
            # A real sleep/wake pair commits a UTC anchor without a factory reset.
            allow.write_text('UTC allowed',encoding='ascii');reset();initial=sync()
            for _ in range(2):port.write(b'pet.feed_hold\n');port.flush();drain(2)
            seeded=state();result['seeded']=seeded
            if seeded['sleeping']:raise ValueError('SEED_NOT_AWAKE')
            allow.unlink();reset();before=state();result['untrusted_boot']=before
            if before['time_trusted']:
                raise ValueError('BOOT_USED_UNTRUSTED_RTC')
            if not before['offline_catchup_pending']:raise ValueError('UTC_ANCHOR_NOT_SAVED')
            # Side-key care goes through the actual runtime dispatcher and NVS save.
            port.write(b'pet.pet\n');port.flush();drain(4)
            accepted=state();result['accepted_action']=accepted
            if not accepted['offline_catchup_pending'] or accepted['offline_journal_events']!=1:
                raise ValueError('ACCEPTED_ACTION_NOT_JOURNALED')
            reconciled=sync();result['reconciled']=reconciled;drain(4);saved=state()
            if saved['unsaved_changes'] and saved['persisted_revision']<=accepted['persisted_revision']:
                raise ValueError('RECONCILED_CHECKPOINT_NOT_SAVED')
            if reconciled['offline_journal_events']!=0:raise ValueError('JOURNAL_NOT_CLEARED')
            # Reboot without time: the UTC anchor survives, but RTC alone is untrusted.
            allow.unlink();reset();restored=state();result['restored']=restored
            if restored['time_trusted'] or not restored['offline_catchup_pending']:
                raise ValueError('CHECKPOINT_RESTORE_FAILED')
            port.write(b'pet.feed\n');port.flush();drain(4);before_ambiguous=state()
            if before_ambiguous['offline_journal_events']!=1:
                raise ValueError('PRE_RESTART_ACTION_NOT_JOURNALED')
            reset();frozen=state()
            if (frozen['time_trusted'] or frozen['offline_catchup_pending'] or
                    not frozen['offline_gap_omitted'] or
                    frozen['satiety']<before_ambiguous['satiety']-1):
                raise ValueError('AMBIGUOUS_RESTART_LOST_CARE')
            final=sync()
            result.update(ok=True,untrusted_boot=before,accepted_action=accepted,
                reconciled=reconciled,restored=restored,before_ambiguous=before_ambiguous,
                frozen_after_clockless_restart=frozen,final=final,
                reconciliations_observed=raw.count(b'Offline timeline reconciled once using UTC'))
    except Exception as error:
        result['error_type']=type(error).__name__
        if re.fullmatch('[A-Z_]+',str(error)):result['error_code']=str(error)
    finally:
        if port.is_open:port.close()
        if child is not None and child.poll() is None:
            child.terminate()
            try:child.wait(timeout=5)
            except subprocess.TimeoutExpired:child.kill();child.wait(timeout=5)
        (FOLDER/'usb.log').write_bytes(raw)
        (ROOT/'evaluation/device-clock-check.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        ready.unlink(missing_ok=True);allow.unlink(missing_ok=True)
    print(json.dumps({key:result[key] for key in ('ok','app_sha256','source','model_called','error_code') if key in result}))
    return 0 if result['ok'] else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--serve',action='store_true')
    if parser.parse_args().serve:
        import asyncio
        binaries=ROOT/'.tools/voice-native/bin'
        os.environ['PATH']=str(binaries)+os.pathsep+os.environ['PATH']
        os.chdir(ROOT/'.tools/upstream/xiaozhi-esp32-server/main/xiaozhi-server')
        sys.path.insert(0,str(ROOT/'.tools/upstream/xiaozhi-esp32-server/main/xiaozhi-server'))
        with os.add_dll_directory(str(binaries)):
            import core.connection
            from config.config_loader import load_config
            asyncio.run(serve(asyncio.run(load_config())))
    else:raise SystemExit(main())
