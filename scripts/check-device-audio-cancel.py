"""Physical decoder/playback queue cancellation using silent Opus and isolated RAM memory."""
import json
from pathlib import Path
import re
import socket
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend/xiaozhi_memory'))
from mem_pet.client import PetMemoryClient


def main():
    import serial
    config=json.loads((ROOT/'.tools/upstream/xiaozhi-esp32-server/main/xiaozhi-server/data/.config.yaml').read_text(encoding='utf-8'))
    settings=config['Memory']['PetMemory'];formal=PetMemoryClient(settings['endpoint'],settings['token'])
    original=formal.profile();fixture=PetMemoryClient('http://127.0.0.1:8767',settings['token'])
    flash=json.loads((ROOT/'evaluation/device-flash.json').read_text(encoding='utf-8'))
    build=json.loads((ROOT/'evaluation/firmware-build.json').read_text(encoding='utf-8'))
    if not flash['app_readback_verified'] or flash['app_sha256']!=build['app_sha256']:raise ValueError('VERIFIED_IMAGE_REQUIRED')
    folder=ROOT/'.runtime/audio-cancel';folder.mkdir(parents=True,exist_ok=True)
    flags=[folder/name for name in ('server-ready','audio-ready','invalidate','result.json')]
    for flag in flags:flag.unlink(missing_ok=True)
    (folder/'error.log').unlink(missing_ok=True)
    result={'ok':False,'source':'physical_device_silent_Opus_queue_and_real_memory_version_invalidation',
        'app_sha256':flash['app_sha256'],'model_called':False,'acoustic_acceptance':False,
        'formal_memory_unchanged':False,'physical_switch_contact_verified':False}
    children=[];logs=[];raw=bytearray()
    port=serial.Serial(port=None,baudrate=115200,timeout=.1,write_timeout=2)
    port.dtr=False;port.rts=False;port.port='COM4'
    def launch(exe,entry,name):
        log=(folder/(name+'.log')).open('wb');logs.append(log)
        child=subprocess.Popen([str(exe),str(entry)],cwd=ROOT,stdout=log,stderr=log,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));children.append(child);return child
    def drain(seconds):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:raw.extend(port.read(min(max(port.in_waiting,1),4096)))
    def wait_file(flag,seconds):
        deadline=time.monotonic()+seconds
        while not flag.exists():
            if (folder/'error.log').exists():raise ValueError('FIXTURE_HANDLER_FAILED')
            if any(child.poll() is not None for child in children):raise ValueError('FIXTURE_EXITED')
            if time.monotonic()>deadline:raise ValueError('FIXTURE_TIMEOUT')
            if port.is_open:drain(.1)
            else:time.sleep(.1)
    try:
        for address in (('127.0.0.1',8767),(config['server']['ip'],8000),(config['server']['ip'],8003)):
            with socket.socket() as probe:probe.bind(address)
        launch(ROOT/'.tools/node22/node-v22.23.4-win-x64/node.exe',ROOT/'scripts/start-memory-fixture.cjs','node')
        deadline=time.monotonic()+10
        while True:
            try:profile=fixture.profile();break
            except Exception:
                if time.monotonic()>deadline:raise
                time.sleep(.1)
        if profile!={'revision':0,'name':None,'preferences':[]}:raise ValueError('EMPTY_FIXTURE_REQUIRED')
        value='取消测试称呼'
        draft=fixture.request('propose',{'kind':'profile','op':'set','field':'name','value':value,
            'source':value,'quote':value,'expectedRevision':0})
        fixture.request('confirm',{'id':draft['id'],'requestId':'fixture-'+draft['id']})
        launch(ROOT/'.tools/voice-venv/Scripts/python.exe',ROOT/'scripts/serve-device-audio-cancel-fixture.py','server')
        wait_file(flags[0],15)
        port.open();port.reset_input_buffer();drain(1)
        port.write(b'pet.main\n');port.flush()
        wait_file(flags[1],15);drain(1.5)
        offset=len(raw);flags[2].write_text('owned test trigger',encoding='ascii')
        wait_file(flags[3],20);drain(3)
        text=raw[offset:].decode('utf-8',errors='replace')
        discards=[tuple(map(int,item)) for item in re.findall(
            r'PetAudio: discard generation=(\d+) decode=(\d+) playback=(\d+) remaining=(\d+)',text)]
        if not any(decode+playback>0 and remaining==0 for _,decode,playback,remaining in discards):
            raise ValueError('QUEUED_AUDIO_DISCARD_NOT_OBSERVED')
        states=re.findall(r'STATE: (\w+)',text)
        if not states or states[-1]!='idle':raise ValueError('IDLE_NOT_OBSERVED')
        backend=json.loads(flags[3].read_text(encoding='utf-8'))
        if not backend['ok'] or backend['revision']!=2:raise ValueError('BACKEND_CANCEL_NOT_VERIFIED')
        result.update(queued_audio_discard_observed=True,discard_samples=discards,returned_to_idle=True,
            memory_invalidation_closed_connection=True,formal_memory_unchanged=formal.profile()==original)
        result['ok']=result['formal_memory_unchanged']
    except Exception as error:
        result['error_type']=type(error).__name__
        if re.fullmatch('[A-Z_]+',str(error)):result['error_code']=str(error)
    finally:
        if port.is_open:port.close()
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
                try:child.wait(timeout=5)
                except subprocess.TimeoutExpired:child.kill();child.wait(timeout=5)
        for log in logs:log.close()
        try:result['formal_memory_unchanged']=formal.profile()==original
        except Exception:pass
        (folder/'usb.log').write_bytes(raw)
        (ROOT/'evaluation/device-audio-cancel-check.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        for flag in flags:flag.unlink(missing_ok=True)
    print(json.dumps(result));return 0 if result['ok'] else 1


if __name__=='__main__':raise SystemExit(main())
