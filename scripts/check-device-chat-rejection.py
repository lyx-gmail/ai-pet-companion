"""One real model state query over diagnostic text; it must not earn ASR credit."""
import argparse
import json
from pathlib import Path
import re
import time

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--connectivity-only',action='store_true',
        help='Verify a reply without claiming a scoring-rejection test.')
    args=parser.parse_args()
    import serial
    flash=json.loads((ROOT/'evaluation/device-flash.json').read_text(encoding='utf-8'))
    if not flash.get('app_readback_verified'): raise RuntimeError('VERIFIED_IMAGE_REQUIRED')
    result={'ok':False,'app_sha256':flash['app_sha256'],'diagnostic_text_accepted':False,
        'reply_started':False,'reply_finished':False,'relationship_count_unchanged':False,
        'hardware_ASR_verified':False,'acoustic_playback_verified':False,
        'scoring_rejection_verified':False,'connectivity_only':args.connectivity_only}
    raw=bytearray()
    port=serial.Serial(port=None,baudrate=115200,timeout=.1,write_timeout=2)
    port.dtr=False; port.rts=False; port.port='COM4'
    def send(command): port.write(('pet.'+command+'\n').encode('ascii'))
    def drain(seconds):
        end=time.monotonic()+seconds
        while time.monotonic()<end: raw.extend(port.read(min(max(port.in_waiting,1),4096)))
    def text(offset=0): return raw[offset:].decode('utf-8',errors='replace')
    def state():
        offset=len(raw); send('state'); drain(1.5)
        matches=re.findall(r'PetUsb: state=(\{[^\r\n]*\})',text(offset))
        if not matches: raise RuntimeError('USB_STATE_MISSING')
        value=json.loads(matches[-1])
        return {k:value[k] for k in ('relationship_interactions','relationship_window_seconds','relationship_spacing_seconds','sleeping')}
    try:
        port.open(); port.reset_input_buffer()
        result['before']=state()
        result['scoring_eligible_before']=(result['before']['relationship_interactions']<3 and
            result['before']['relationship_spacing_seconds']>=600)
        if not result['scoring_eligible_before'] and not args.connectivity_only:
            raise RuntimeError('SCORING_CAP_OR_SPACING_BLOCKS_TEST')
        if result['before']['sleeping']:
            send('main'); drain(1)
        send('main'); deadline=time.monotonic()+40; attempts=0
        while time.monotonic()<deadline and attempts<6:
            drain(.2)
            states=re.findall(r'STATE: (\w+)',text())
            if not states or states[-1]!='listening': continue
            offset=len(raw); send('query_state'); attempts+=1; drain(1.5)
            ack=re.findall(r'text_sent=(\d+)',text(offset))
            if ack and ack[-1]=='1': result['diagnostic_text_accepted']=True; break
            if not ack: raise RuntimeError('DIAGNOSTIC_ACK_MISSING')
        if not result['diagnostic_text_accepted']: raise RuntimeError('DIAGNOSTIC_NOT_ACCEPTED')
        deadline=time.monotonic()+35
        while time.monotonic()<deadline:
            drain(.2); turn=text(offset)
            started=re.search(r'STATE: speaking',turn)
            result['reply_started']=started is not None
            if started and re.search(r'STATE: (listening|idle)',turn[started.end():]):
                result['reply_finished']=True; break
        if not result['reply_finished']: raise RuntimeError('REPLY_NOT_FINISHED')
        drain(2); result['after']=state()
        before,after=result['before'],result['after']
        if after['relationship_window_seconds']<before['relationship_window_seconds']: raise RuntimeError('WINDOW_ROLLED_OVER')
        result['relationship_count_unchanged']=after['relationship_interactions']==before['relationship_interactions']
        if not result['relationship_count_unchanged']: raise RuntimeError('DIAGNOSTIC_EARNED_CREDIT')
        result['scoring_rejection_verified']=result['scoring_eligible_before'] and not args.connectivity_only
        result['ok']=True
    except Exception as error:
        result['error_type']=type(error).__name__
        if re.fullmatch('[A-Z_]+',str(error)): result['error_code']=str(error)
    finally:
        if port.is_open:
            try:
                send('main_hold'); drain(2); send('main_hold'); drain(2)
            finally: port.close()
        name='chat-connectivity' if args.connectivity_only else 'chat-rejection'
        (ROOT/'.runtime/flash'/('usb-'+name+'.log')).write_bytes(raw)
        (ROOT/'evaluation'/('device-'+name+'-check.json')).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result)); return 0 if result['ok'] else 1

if __name__=='__main__': raise SystemExit(main())
