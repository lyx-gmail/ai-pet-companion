"""Request official discovery for the owned bound device, without applying updates."""
import json
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, ProxyHandler

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend/xiaozhi_memory'))
from mem_pet.client import NoRedirect


def main():
    config=json.loads((ROOT/'.tools/upstream/xiaozhi-esp32-server/main/xiaozhi-server/data/.config.yaml').read_text(encoding='utf-8'))
    device=config['Memory']['PetMemory']['expected_device_id']
    identity=json.loads((ROOT/'.runtime/official-ai/device-identity.json').read_text())['uuid']
    if not re.fullmatch(r'(?:[0-9a-f]{2}:){5}[0-9a-f]{2}',device) or not re.fullmatch(r'[0-9a-f-]{36}',identity):
        raise ValueError('OWNED_DEVICE_IDENTITY_REQUIRED')
    # Same identity and hardware metadata as the backed-up board. This is a PC
    # protocol probe; it does not pretend to be a microphone or change firmware.
    body={'version':2,'language':'zh-CN','flash_size':16777216,'mac_address':device,'uuid':identity,
        'chip_model_name':'esp32s3','application':{'name':'xiaozhi','version':'2.0.4'},
        'board':{'type':'xingzhi-cube-1.54tft-wifi'}}
    request=Request('https://api.tenclass.net/xiaozhi/ota/',
        data=json.dumps(body).encode('utf-8'),headers={
            'Content-Type':'application/json','Device-Id':device,'Client-Id':identity,
            'Activation-Version':'1','User-Agent':'xiaozhi/2.0.4 (official-compatibility-probe)'},method='POST')
    result={'ok':False,'source':'official_HTTPS_discovery_with_owned_device_identity',
        'firmware_changed':False,'cloud_model_called':False,'hardware_ASR_verified':False}
    try:
        with build_opener(ProxyHandler({}),NoRedirect()).open(request,timeout=15) as response:
            raw=response.read(65537)
            result['http_status']=response.status
        if len(raw)>65536: raise ValueError('RESPONSE_TOO_LARGE')
        value=json.loads(raw)
        if not isinstance(value,dict): raise ValueError('RESPONSE_INVALID')
        (ROOT/'.runtime/official-ai/discovery.json').write_text(json.dumps(value)+'\n',encoding='utf-8')
        activation=value.get('activation',{})
        result.update(ok=True,websocket_config_available=isinstance(value.get('websocket'),dict),
            mqtt_config_available=isinstance(value.get('mqtt'),dict),
            activation_required=bool(isinstance(activation,dict) and (activation.get('code') or activation.get('challenge'))),
            firmware_update_offered=bool(isinstance(value.get('firmware'),dict) and value['firmware'].get('url')))
    except HTTPError as error:
        result.update(http_status=error.code,error_type='HTTPError')
        error.close()
    except (URLError,TimeoutError,ValueError) as error:
        result['error_type']=type(error).__name__
    (ROOT/'evaluation/official-ai-discovery-check.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))
    return 0 if result['ok'] else 1


if __name__=='__main__':raise SystemExit(main())
