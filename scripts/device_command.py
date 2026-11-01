"""Send one explicit command to the optional native USB development interface."""
import argparse
import json
from pathlib import Path
import re
import time

ROOT=Path(__file__).resolve().parents[1]
COMMANDS={'state':1,'main':2,'main_hold':3,'feed':4,'feed_hold':5,'pet':6,'pet_hold':7,
          'memory_demo':8,'query_state':9,'request_feed':10,'wifi_pause':11}
NUMBERS={'satiety','mood','energy','closeness','feed_cooldown_seconds','pet_cooldown_seconds',
         'revision','persisted_revision','event_elapsed_seconds','relationship_interactions',
         'relationship_window_seconds','relationship_spacing_seconds',
          'memory_admin_phase','memory_admin_page','memory_admin_revision','offline_journal_events'}
FLAGS={'ok','sleeping','sleep_pending','muted','unsaved_changes','time_trusted',
       'offline_catchup_pending','offline_gap_omitted','memory_confirmation_pending',
       'memory_admin_valid','memory_admin_unresolved','memory_admin_busy','wifi_connected'}


def analyze(command,text):
    text=re.sub(r'\x1b\[[0-9;]*m','',text)
    dispatched=COMMANDS[command] in [int(x) for x in re.findall(r'PetUsb: dispatch=(\d+)',text)]
    state=None
    for raw in re.findall(r'PetUsb: state=(\{[^\r\n]*\})',text):
        try:
            value=json.loads(raw)
            if not isinstance(value,dict): continue
            state={key:item for key,item in value.items()
                   if (key in NUMBERS and type(item) is int and 0<=item<=0xffffffff)
                   or (key in FLAGS and type(item) is bool)}
        except ValueError:
            continue
    return {'source':'physical_native_USB_development_command','command':command,
            'command_dispatched':dispatched,'state':state,
            'physical_button_press_verified':False,
            'ok':dispatched and (command!='state' or bool(state and state.get('ok')))}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=COMMANDS,nargs='?',default='state')
    parser.add_argument('--seconds',type=int,default=5,choices=range(3,31))
    args=parser.parse_args()
    import serial
    reader=serial.Serial(port=None,baudrate=115200,timeout=0.1,write_timeout=2)
    reader.dtr=False; reader.rts=False; reader.port='COM4'
    raw=bytearray()
    try:
        reader.open()
        reader.reset_input_buffer()
        reader.write(('pet.'+args.command+'\n').encode('ascii'))
        started=time.monotonic()
        while time.monotonic()-started<args.seconds:
            raw.extend(reader.read(min(max(reader.in_waiting,1),4096)))
    finally:
        reader.close()
    private=ROOT/'.runtime/flash'
    private.mkdir(parents=True,exist_ok=True)
    (private/('usb-'+args.command+'.log')).write_bytes(raw)
    result=analyze(args.command,raw.decode('utf-8',errors='replace'))
    (ROOT/'evaluation'/('device-usb-'+args.command+'.json')).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))
    return 0 if result['ok'] else 1


if __name__=='__main__': raise SystemExit(main())
