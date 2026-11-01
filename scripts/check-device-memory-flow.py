"""Actual device/LLM/USB confirmation test against isolated loopback memory only.

Protocol text bypasses ASR; key dispatch bypasses the physical switch. Neither
is acoustic or physical-contact acceptance. No official pet memory is changed.
"""
import json
from pathlib import Path
import re
import time
from urllib.request import Request,build_opener,ProxyHandler

ROOT=Path(__file__).resolve().parents[1]


def main():
    import serial
    config=json.loads((ROOT/'.tools/upstream/xiaozhi-esp32-server/main/xiaozhi-server/data/.config.yaml').read_text(encoding='utf-8'))
    memory=config['Memory']['PetMemory']
    if memory['endpoint']!='http://127.0.0.1:8767': raise RuntimeError('ISOLATED_FIXTURE_REQUIRED')
    opener=build_opener(ProxyHandler({}))
    def profile():
        req=Request(memory['endpoint']+'/api/profile',headers={'Authorization':'Bearer '+memory['token']})
        with opener.open(req,timeout=3) as response: return json.loads(response.read(65536))
    baseline=profile()
    if baseline['revision']!=0: raise RuntimeError('EMPTY_FIXTURE_REQUIRED')
    port=serial.Serial(port=None,baudrate=115200,timeout=.1,write_timeout=2)
    port.dtr=False; port.rts=False; port.port='COM4'
    raw=bytearray()
    latest={}
    def send(command): port.write(('pet.'+command+'\n').encode('ascii'))
    def drain(seconds):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            raw.extend(port.read(min(max(port.in_waiting,1),4096)))
        for value in re.findall(rb'PetUsb: state=(\{[^\r\n]*\})',raw):
            try: latest.update(json.loads(value))
            except ValueError: pass
    result={'source':'actual_device_protocol_text_and_USB_key_dispatch','isolated_memory_fixture':True,
            'real_llm_extraction':True,'hardware_ASR_verified':False,'physical_switch_contact_verified':False,
            'hardware_acoustic_playback_verified':False,'cases':[],'ok':False}
    try:
        port.open(); port.reset_input_buffer()
        for choice,expected in (('main',1),('pet',1),('timeout',1)):
            send('main'); drain(4)
            start=len(raw); send('memory_demo')
            deadline=time.monotonic()+40
            prompted=False
            while time.monotonic()<deadline:
                send('state'); drain(1)
                if latest.get('memory_confirmation_pending'):
                    prompted=True; break
            if not prompted: raise RuntimeError('DEVICE_CONFIRMATION_NOT_PRESENTED')
            before=profile()
            if choice!='timeout': send(choice)
            deadline=time.monotonic()+(34 if choice=='timeout' else 12)
            while time.monotonic()<deadline:
                send('state'); drain(1)
                if not latest.get('memory_confirmation_pending'):
                    if choice=='main' and profile()['revision']!=expected: continue
                    break
            after=profile()
            case={'decision':choice,'prompt_presented':prompted,'revision_before':before['revision'],
                  'revision_after':after['revision'],'pending_cleared':not latest.get('memory_confirmation_pending',True),
                  'confirmed_name_matches_fixture':after.get('name')=='测试伙伴',
                  'text_sent_on_device':'PetUsb: text_sent=1' in raw[start:].decode('utf-8',errors='replace')}
            case['ok']=case['pending_cleared'] and case['text_sent_on_device'] and after['revision']==expected and case['confirmed_name_matches_fixture']
            result['cases'].append(case)
            if not case['ok']: raise RuntimeError('MEMORY_FLOW_ASSERTION_FAILED')
            send('main_hold'); drain(2); send('main_hold'); drain(2)
        result['ok']=True
    except Exception as error:
        result['error_type']=type(error).__name__
        if re.fullmatch(r'[A-Z_]+',str(error)): result['error_code']=str(error)
    finally:
        if port.is_open:
            try:
                send('main_hold'); drain(2); send('main_hold'); drain(2)
            finally: port.close()
        (ROOT/'.runtime/flash/usb-memory-flow.log').write_bytes(raw)
        (ROOT/'evaluation/device-memory-flow-check.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))
    return 0 if result['ok'] else 1


if __name__=='__main__': raise SystemExit(main())
