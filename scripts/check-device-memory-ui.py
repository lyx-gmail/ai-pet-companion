"""Actual device HTTP/menu deletion against an isolated RAM store; no model API."""
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
    memory=config['Memory']['PetMemory'];formal=PetMemoryClient(memory['endpoint'],memory['token'])
    before=formal.profile();fixture=PetMemoryClient('http://127.0.0.1:8767',memory['token'])
    flash=json.loads((ROOT/'evaluation/device-flash.json').read_text(encoding='utf-8'))
    build=json.loads((ROOT/'evaluation/firmware-build.json').read_text(encoding='utf-8'))
    if not flash.get('app_readback_verified') or flash['app_sha256']!=build['app_sha256']:
        raise ValueError('LATEST_READBACK_VERIFIED_IMAGE_REQUIRED')
    folder=ROOT/'.runtime/memory-ui';folder.mkdir(parents=True,exist_ok=True)
    trace=folder/'requests.jsonl';trace.write_text('',encoding='utf-8')
    flags=[folder/'delay-profile-once',folder/'drop-confirm-once']
    for flag in flags:flag.unlink(missing_ok=True)
    processes=[];logs=[];raw=bytearray();opened=False
    result={'ok':False,'source':'physical_device_menu_HTTP_and_USB_keys_isolated_Node_RAM_database',
        'app_sha256':flash['app_sha256'],'formal_memory_unchanged':False,'cloud_model_called':False,
        'physical_switch_contact_verified':False,'visual_layout_verified':False}
    port=serial.Serial(port=None,baudrate=115200,timeout=.1,write_timeout=2)
    port.dtr=False;port.rts=False;port.port='COM4'
    def drain(seconds):
        end=time.monotonic()+seconds
        while time.monotonic()<end:raw.extend(port.read(min(max(port.in_waiting,1),4096)))
    def send(command):port.write(('pet.'+command+'\n').encode('ascii'));port.flush();drain(1.2)
    def state():
        offset=len(raw);send('state');deadline=time.monotonic()+3
        values=re.findall(rb'PetUsb: state=(\{[^\r\n]*\})',raw[offset:])
        while not values and time.monotonic()<deadline:
            drain(.3);values=re.findall(rb'PetUsb: state=(\{[^\r\n]*\})',raw[offset:])
        if not values:raise ValueError('USB_STATE_MISSING')
        return json.loads(values[-1])
    def phase(wanted,seconds=10):
        deadline=time.monotonic()+seconds
        while True:
            value=state()
            if value.get('memory_admin_phase')==wanted and not value.get('memory_admin_busy'):return value
            if time.monotonic()>deadline:raise ValueError('UNEXPECTED_MENU_PHASE_'+str(wanted))
            drain(.2)
    def seed(kind,field,value):
        current=fixture.profile()
        draft=fixture.request('propose',{'kind':kind,'op':'set','field':field,'value':value,
            'source':value,'quote':value,'expectedRevision':current['revision']})
        fixture.request('confirm',{'id':draft['id'],'requestId':'fixture-'+draft['id']})
    def launch(executable,entry,name):
        output=(folder/(name+'.log')).open('wb');logs.append(output)
        process=subprocess.Popen([str(executable),str(entry)],cwd=ROOT,stdout=output,stderr=output,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));processes.append(process)
        return process
    try:
        # Caller must stop only the owned formal voice service and restore it in finally.
        for address in (('127.0.0.1',8767),(config['server']['ip'],8003)):
            with socket.socket() as probe:probe.bind(address)
        node=launch(ROOT/'.tools/node22/node-v22.23.4-win-x64/node.exe',ROOT/'scripts/start-memory-fixture.cjs','node')
        deadline=time.monotonic()+12
        while True:
            try:
                if fixture.profile()!={'revision':0,'name':None,'preferences':[]}:raise ValueError('NONEMPTY_FIXTURE')
                break
            except Exception:
                if node.poll() is not None or time.monotonic()>deadline:raise
                time.sleep(.1)
        seed('profile','name','菜单测试称呼');seed('profile','preference0','喜欢看星星');seed('experience',None,'一起看过测试星星')
        bridge=launch(ROOT/'.tools/voice-venv/Scripts/python.exe',ROOT/'scripts/serve-memory-ui-fixture.py','http')
        deadline=time.monotonic()+10
        while True:
            with socket.socket() as probe:
                if probe.connect_ex((config['server']['ip'],8003))==0:break
            if bridge.poll() is not None or time.monotonic()>deadline:raise ValueError('FIXTURE_HTTP_NOT_READY')
            time.sleep(.1)
        port.open();port.reset_input_buffer();drain(1)
        if state().get('memory_admin_phase')!=0:raise ValueError('INITIAL_MENU_NOT_CLOSED')
        send('main_hold');opened=True;send('pet');send('pet');send('main')
        loaded=phase(2);assert loaded['memory_admin_valid'] and loaded['memory_admin_revision']==3
        result['profile_read_verified']=True
        initial=fixture.profile()
        send('main');phase(4);assert fixture.profile()==initial
        send('pet');phase(2);assert fixture.profile()==initial
        result['cancel_preserves_profile']=True
        # A concurrent confirmed change makes the already-viewed revision stale.
        seed('profile','preference1','喜欢听轻音乐')
        revised=fixture.profile();send('main');phase(7);assert fixture.profile()==revised
        result['stale_revision_rejected']=True
        send('main');phase(2)
        send('main');phase(4);phase(2,32);assert fixture.profile()==revised
        result['timeout_preserves_profile']=True
        flags[1].write_text('owned one-shot test',encoding='ascii')
        send('main');phase(4);send('main');uncertain=phase(6)
        assert uncertain['memory_admin_unresolved'] and not uncertain['memory_admin_valid']
        after=fixture.profile();assert after['name'] is None and after['revision']==revised['revision']+1
        send('pet');phase(0);send('main');phase(6) # reopen retains unresolved transaction
        send('main');phase(8);assert fixture.profile()==after
        requests=[json.loads(line) for line in trace.read_text(encoding='utf-8').splitlines()]
        identities=[item['id'] for item in requests if item.get('action')=='confirm']
        assert len(identities)>=2 and identities[-1]==identities[-2]
        result.update(lost_receipt_retry_same_id=True,reopen_preserves_uncertain_operation=True,
            retry_does_not_increment_revision_twice=True,name_delete_preserves_other_memory=bool(after['preferences']))
        send('main');phase(2)
        for _ in range(5):send('pet')
        assert state()['memory_admin_page']==5
        send('main');phase(4);send('main');phase(8)
        empty=fixture.profile();recalled=fixture.recall_snapshot('测试星星')
        assert empty['name'] is None and not empty['preferences'] and not recalled['memories']
        result['delete_all_clears_profile_and_experiences']=True
        bridge.terminate();bridge.wait(timeout=5)
        send('main');failed=phase(7)
        result['outage_invalidates_displayed_profile']=failed['memory_admin_valid'] is False
        send('main_hold');opened=False;phase(0)
        result['formal_memory_unchanged']=formal.profile()==before
        result['ok']=result['formal_memory_unchanged'] and result['outage_invalidates_displayed_profile']
    except Exception as error:
        result['error_type']=type(error).__name__
        if re.fullmatch('[A-Z_0-9]+',str(error)):result['error_code']=str(error)
    finally:
        if port.is_open:
            if opened:
                try:send('main_hold')
                except Exception:pass
            port.close()
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
        for log in logs:log.close()
        for flag in flags:flag.unlink(missing_ok=True)
        try:result['formal_memory_unchanged']=formal.profile()==before
        except Exception:pass
        (folder/'usb.log').write_bytes(raw)
        (ROOT/'evaluation/device-memory-ui-check.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result));return 0 if result['ok'] else 1


if __name__=='__main__':raise SystemExit(main())
