"""Open the real device menu and read formal memory; never request deletion."""
import json
from pathlib import Path
import re
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend/xiaozhi_memory'))
from mem_pet.client import PetMemoryClient


def main():
    import serial
    config=json.loads((ROOT/'.tools/upstream/xiaozhi-esp32-server/main/xiaozhi-server/data/.config.yaml').read_text(encoding='utf-8'))
    memory=config['Memory']['PetMemory'];client=PetMemoryClient(memory['endpoint'],memory['token'])
    before=client.profile()
    flash=json.loads((ROOT/'evaluation/device-flash.json').read_text(encoding='utf-8'))
    build=json.loads((ROOT/'evaluation/firmware-build.json').read_text(encoding='utf-8'))
    if not flash.get('app_readback_verified') or flash['app_sha256']!=build['app_sha256']:
        raise ValueError('LATEST_READBACK_VERIFIED_IMAGE_REQUIRED')
    result={'ok':False,'source':'physical_device_memory_menu_HTTP_read_via_USB_key_dispatch',
        'app_sha256':flash['app_sha256'],'delete_requested':False,'formal_memory_unchanged':False,
        'physical_switch_contact_verified':False,'visual_layout_verified':False}
    raw=bytearray();opened=False
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
    try:
        port.open();port.reset_input_buffer();drain(3)
        if state().get('memory_admin_phase')!=0:raise ValueError('INITIAL_MENU_NOT_CLOSED')
        send('main_hold');opened=True
        send('pet');send('pet');send('main')
        deadline=time.monotonic()+10
        while True:
            current=state()
            if current.get('memory_admin_phase')==2 and current.get('memory_admin_valid') is True:break
            if time.monotonic()>deadline:raise ValueError('MEMORY_PROFILE_NOT_READY')
            drain(.2)
        result.update(profile_revision_matched=current['memory_admin_revision']==before['revision'],
            profile_entry_count=(1 if before['name'] else 0)+len(before['preferences']),
            device_menu_phase=current['memory_admin_phase'])
        send('pet');current=state()
        result['next_page_navigation_verified']=current.get('memory_admin_page')==1
        send('feed');current=state()
        result['previous_page_navigation_verified']=current.get('memory_admin_page')==0
        send('main_hold');opened=False;current=state()
        result['menu_closed']=current.get('memory_admin_phase')==0 and not current.get('memory_admin_valid')
        result['formal_memory_unchanged']=client.profile()==before
        result['ok']=all(result.get(key) is True for key in ('profile_revision_matched',
            'next_page_navigation_verified','previous_page_navigation_verified','menu_closed','formal_memory_unchanged'))
    except Exception as error:
        result['error_type']=type(error).__name__
        if re.fullmatch('[A-Z_]+',str(error)):result['error_code']=str(error)
    finally:
        if port.is_open:
            if opened:
                try:send('main_hold')
                except Exception:pass
            port.close()
        try:result['formal_memory_unchanged']=client.profile()==before
        except Exception:pass
        (ROOT/'.runtime/flash/usb-memory-view.log').write_bytes(raw)
        (ROOT/'evaluation/device-memory-view-check.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result));return 0 if result['ok'] else 1


if __name__=='__main__':raise SystemExit(main())
