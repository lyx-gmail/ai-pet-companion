"""Repeat software guards and live authentication failures; no cloud/model call."""
import asyncio
import hashlib
import io
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from pet_official_proxy import backend_mode


def main():
    config=json.loads((ROOT/'.tools/upstream/xiaozhi-esp32-server/main/xiaozhi-server/data/.config.yaml').read_text(encoding='utf-8'))
    path=Path(config['pet_official']['mode_file'])
    mode=backend_mode(json.loads(path.read_text(encoding='utf-8')) if path.exists() else {})
    suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(name) for name in
        ('test_official_proxy','test_official_memory','test_official_ai_probe'))
    output=io.StringIO();tests=unittest.TextTestRunner(stream=output).run(suite)
    result={'ok':False,'software_tests_run':tests.testsRun,
        'software_tests_passed':tests.testsRun-len(tests.errors)-len(tests.failures),
        'live_backend_mode':mode,'cloud_model_called':False,
        'physical_cloud_care_verified':False,'physical_memory_confirmation_verified':False,
        'files':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
            ('backend/pet_official_proxy.py','backend/pet_official_memory.py','scripts/voice_pet_patch.py','scripts/prepare-voice.py')}}
    async def check():
        import websockets
        device=config['Memory']['PetMemory']['expected_device_id']
        client=json.loads((ROOT/'.runtime/official-ai/device-identity.json').read_text(encoding='utf-8'))['uuid']
        headers={'Device-Id':device,'Client-Id':client,'Authorization':'Bearer invalid'}
        async with websockets.connect(config['server']['websocket'],additional_headers=headers,open_timeout=3) as socket:
            denial=await asyncio.wait_for(socket.recv(),3)
            await asyncio.wait_for(socket.wait_closed(),3)
        headers['Device-Id']='02:00:00:00:00:ff'
        async with websockets.connect(config['server']['websocket'],additional_headers=headers,open_timeout=3) as socket:
            await asyncio.wait_for(socket.wait_closed(),3)
            other=socket.close_code==1008
        return denial=='认证失败',other
    try:
        invalid,other=asyncio.run(check())
        result.update(live_invalid_HMAC_rejected=invalid,live_wrong_device_rejected=other)
        result['ok']=tests.wasSuccessful() and invalid and other and mode=='local'
    except Exception as error:result['error_type']=type(error).__name__
    if not tests.wasSuccessful():
        (ROOT/'.runtime/official-ai/boundary-test-failure.log').write_text(output.getvalue(),encoding='utf-8')
    (ROOT/'evaluation/official-proxy-check.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result));return 0 if result['ok'] else 1


if __name__=='__main__':raise SystemExit(main())
