"""Actual device/model care test; protocol text and USB dispatch bypass ASR/contacts."""
import ast
import json
from pathlib import Path
import re
import time

ROOT=Path(__file__).resolve().parents[1]


def main():
    import serial
    flash=json.loads((ROOT/'evaluation/device-flash.json').read_text(encoding='utf-8'))
    if not (flash.get('written') and flash.get('app_readback_verified')):
        raise RuntimeError('VERIFIED_DEVICE_IMAGE_REQUIRED')
    server=ROOT/'.runtime/voice/logs/server.log'
    raw=bytearray(); state='idle'; sent=None; ack_offset=0
    port=serial.Serial(port=None,baudrate=115200,timeout=.1,write_timeout=2)
    port.dtr=False; port.rts=False; port.port='COM4'
    def send(command): port.write(('pet.'+command+'\n').encode('ascii'))
    def drain(seconds):
        nonlocal state,sent
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            part=port.read(min(max(port.in_waiting,1),4096)); raw.extend(part)
        text=raw.decode('utf-8',errors='replace')
        states=re.findall(r'STATE: (\w+)',text)
        if states: state=states[-1]
        acks=re.findall(r'text_sent=(\d+)',raw[ack_offset:].decode('utf-8',errors='replace'))
        if acks: sent=acks[-1]=='1'
    def receipt(offset,tool):
        text=server.read_bytes()[offset:].decode('utf-8',errors='replace')
        for line in text.splitlines():
            match=re.search(r'客户端mcp工具调用 '+re.escape(tool)+r' 成功，原始结果: (.*)',line)
            if not match: continue
            try:
                envelope=ast.literal_eval(match[1]); data=json.loads(envelope['content'][0]['text'])
                return {'tool':tool,**{key:data[key] for key in ('ok','code','delta','durable','satiety','revision','applied') if key in data}}
            except (ValueError,KeyError,IndexError,SyntaxError): continue
        return None
    result={'source':'actual_device_model_and_MCP_after_fixed_protocol_text','app_sha256':flash['app_sha256'],'hardware_ASR_verified':False,
            'physical_button_contact_verified':False,'hardware_acoustic_playback_verified':False,'cases':[],'ok':False}
    try:
        port.open(); port.reset_input_buffer(); send('main')
        for command,tool in (('query_state','self.pet.get_state'),('request_feed','self.pet.feed')):
            accepted=False; retries=0; deadline=time.monotonic()+40
            while time.monotonic()<deadline and retries<6:
                drain(.2)
                if state!='listening': continue
                offset=server.stat().st_size; ack_offset=len(raw); sent=None; send(command); retries+=1; drain(1.5)
                if sent: accepted=True; break
                # A rejected (text_sent=0) diagnostic never reaches the model.
            if not accepted: raise RuntimeError('DIAGNOSTIC_TEXT_NOT_ACCEPTED')
            deadline=time.monotonic()+25; actual=None
            while time.monotonic()<deadline:
                drain(.2); actual=receipt(offset,tool)
                if actual: break
            case={'command':command,'text_accepted':accepted,'rejected_attempts':retries-1,'receipt':actual}
            case['ok']=bool(actual and actual.get('ok') is True and (tool.endswith('get_state') or actual.get('durable') is True))
            result['cases'].append(case)
            if not case['ok']: raise RuntimeError('DEVICE_TOOL_RESULT_FAILED')
            if tool.endswith('feed'):
                start=len(raw); send('state'); drain(2)
                states=re.findall(rb'PetUsb: state=(\{[^\r\n]*\})',raw[start:])
                if not states: raise RuntimeError('POST_ACTION_STATE_MISSING')
                readback=json.loads(states[-1])
                checked={key:readback.get(key) for key in ('satiety','revision','persisted_revision','feed_cooldown_seconds')}
                result['post_action_USB_state']=checked
                if not (type(checked['satiety']) is int and actual['satiety']-1<=checked['satiety']<=actual['satiety']
                        and checked['persisted_revision']>=actual['revision'] and checked['feed_cooldown_seconds']>0):
                    raise RuntimeError('POST_ACTION_STATE_MISMATCH')
        result['ok']=True
    except Exception as error:
        result['error_type']=type(error).__name__
        if re.fullmatch('[A-Z_]+',str(error)): result['error_code']=str(error)
    finally:
        if port.is_open:
            try:
                send('main_hold'); drain(2); send('main_hold'); drain(2)
            finally: port.close()
        (ROOT/'.runtime/flash/usb-care-flow.log').write_bytes(raw)
        (ROOT/'evaluation/device-care-voice-check.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))
    return 0 if result['ok'] else 1


if __name__=='__main__': raise SystemExit(main())
