"""Physical pet with owned PC voice service stopped; not a device Wi-Fi outage test.

Caller must disconnect voice and restore it in finally. No model calls or memory writes.
"""
import json
from pathlib import Path
import re
import socket
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]


def main():
    import serial
    from device_command import analyze
    config=json.loads((ROOT/'.tools/upstream/xiaozhi-esp32-server/main/xiaozhi-server/data/.config.yaml').read_text(encoding='utf-8'))
    for number in (8000,8003):
        with socket.socket() as probe:
            if probe.connect_ex((config['server']['ip'],number))==0:raise ValueError('VOICE_SERVICE_MUST_BE_OFFLINE')
    build=json.loads((ROOT/'evaluation/firmware-build.json').read_text(encoding='utf-8'))
    flash=json.loads((ROOT/'evaluation/device-flash.json').read_text(encoding='utf-8'))
    if not flash.get('app_readback_verified') or flash['app_sha256']!=build['app_sha256']:
        raise ValueError('CURRENT_VERIFIED_IMAGE_REQUIRED')
    folder=ROOT/'.runtime/backend-offline';folder.mkdir(parents=True,exist_ok=True)
    result={'ok':False,'source':'physical_USB_with_owned_PC_voice_service_stopped',
        'app_sha256':build['app_sha256'],'model_called':False,'device_wifi_disconnected':False,
        'physical_switch_contact_verified':False,'visual_or_acoustic_acceptance':False}
    raw=bytearray();port=serial.Serial(port=None,baudrate=115200,timeout=.1,write_timeout=2)
    port.dtr=False;port.rts=False;port.port='COM4'
    def drain(seconds):
        end=time.monotonic()+seconds
        while time.monotonic()<end:raw.extend(port.read(min(max(port.in_waiting,1),4096)))
    def send(command):port.write(('pet.'+command+'\n').encode('ascii'));port.flush()
    def state():
        offset=len(raw);send('state');drain(1.5)
        response=analyze('state',raw[offset:].decode('utf-8',errors='replace'))
        if not response['ok']:raise ValueError('STATE_UNAVAILABLE')
        return response['state']
    try:
        port.open();port.reset_input_buffer();before=state();result['before']=before
        if before['sleeping'] or before['memory_admin_phase']!=0 or before['pet_cooldown_seconds'] or before['mood']>=100:
            raise ValueError('CARE_PRECONDITION_NOT_MET')
        offset=len(raw);started=time.monotonic();send('main');idle=False
        while time.monotonic()-started<10:
            drain(.1);text=raw[offset:].decode('utf-8',errors='replace')
            if 'Application: STATE: connecting' in text and 'Application: STATE: idle' in text:
                idle=True;break
        result['voice_wait_seconds']=round(time.monotonic()-started,3)
        if not idle:raise ValueError('VOICE_WAIT_EXCEEDED_10_SECONDS')
        result['returned_to_idle_with_backend_offline']=True
        send('pet');drain(4);petted=state();result['petted']=petted
        if petted['mood']!=min(100,before['mood']+8) or petted['persisted_revision']<=before['persisted_revision']:
            raise ValueError('OFFLINE_PET_OR_SAVE_FAILED')
        send('feed_hold');drain(2);asleep=state();result['asleep']=asleep
        if not asleep['sleeping']:raise ValueError('OFFLINE_SLEEP_FAILED')
        send('feed');drain(2);awake=state();result['awake']=awake
        if awake['sleeping'] or abs(awake['satiety']-petted['satiety'])>1 or awake['feed_cooldown_seconds']>petted['feed_cooldown_seconds']:
            raise ValueError('WAKE_UNEXPECTEDLY_FED')
        port.close()
        with (folder/'reset.log').open('wb') as log:
            subprocess.run([sys.executable,'-m','esptool','--chip','esp32s3','--port','COM4',
                '--baud','460800','--before','usb_reset','--after','hard_reset','--connect-attempts','3',
                'chip_id'],cwd=ROOT,stdout=log,stderr=log,check=True,timeout=20)
        port.open();drain(13);restored=state();result['restored']=restored
        if (restored['sleeping'] or restored['mood']!=awake['mood'] or
                abs(restored['satiety']-awake['satiety'])>1 or restored['time_trusted']):
            raise ValueError('BACKEND_OFFLINE_REBOOT_STATE_MISMATCH')
        text=raw.decode('utf-8',errors='replace')
        if re.search(r'Guru Meditation|Stack overflow|Task watchdog got triggered|assert failed:',text,re.I):
            raise ValueError('DEVICE_CRASH_OBSERVED')
        if 'Pet local boot: activation wait skipped' not in text:raise ValueError('LOCAL_BOOT_NOT_OBSERVED')
        result.update(ok=True,care_save_and_reboot_verified=True,wake_did_not_feed=True,
            local_boot_without_activation=True)
    except Exception as error:
        result['error_type']=type(error).__name__
        if re.fullmatch('[A-Z_0-9]+',str(error)):result['error_code']=str(error)
    finally:
        if port.is_open:port.close()
        (folder/'usb.log').write_bytes(raw)
        (ROOT/'evaluation/device-backend-offline-check.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:result[key] for key in ('ok','voice_wait_seconds','error_code','care_save_and_reboot_verified') if key in result}))
    return 0 if result['ok'] else 1


if __name__=='__main__':raise SystemExit(main())
