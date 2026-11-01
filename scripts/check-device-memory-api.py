"""Real authenticated bridge + isolated Node SQLite store; no device or LLM calls."""
import asyncio
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

ROOT=Path(__file__).resolve().parents[1]
SERVER=ROOT/'.tools/upstream/xiaozhi-esp32-server/main/xiaozhi-server'
sys.path[:0]=[str(ROOT/'backend'),str(SERVER)]
from pet_memory_admin import PetMemoryHandler
from core.auth import AuthManager
from core.providers.memory.mem_pet.client import PetMemoryClient, MemoryUnavailable


async def exercise(config):
    # Only this copy points at the disposable RAM database. Formal service is unchanged.
    config=json.loads(json.dumps(config))
    config['Memory']['PetMemory']['endpoint']='http://127.0.0.1:8767'
    handler=PetMemoryHandler(config)
    memory=handler.memory
    device=config['Memory']['PetMemory']['expected_device_id']
    headers={'Device-ID':device,'Client-ID':'isolated-device-menu',
        'Authorization':'Bearer '+AuthManager(config['server']['auth_key']).generate_token('isolated-device-menu',device)}
    app=web.Application();app.router.add_post('/pet/memory',handler.handle)
    async with TestClient(TestServer(app)) as http:
        async def request(body,status=200):
            response=await http.post('/pet/memory',json=body,headers=headers)
            assert response.status==status,(response.status,status)
            assert response.headers['Cache-Control']=='no-store'
            return await response.json()
        def seed(field,value,kind='profile'):
            revision=memory.profile()['revision']
            draft=memory.request('propose',{'kind':kind,'field':field,'value':value,
                'source':'虚构资料'+value,'quote':value,'expectedRevision':revision})
            return memory.request('confirm',{'id':draft['id'],'requestId':'fixture-'+draft['id']})
        await asyncio.to_thread(seed,'name','虚构伙伴')
        before=await request({'action':'profile'})
        assert before['name']=='虚构伙伴' and before['revision']==1
        draft=await request({'action':'delete','field':'name','revision':1})
        assert draft['status']=='PENDING'
        assert (await request({'action':'profile'}))==before
        await request({'action':'cancel','id':draft['id']})
        assert (await request({'action':'profile'}))==before
        assert (await request({'action':'delete','field':'name','revision':0},409))['error']=='CONFLICT'
        draft=await request({'action':'delete','field':'name','revision':1})
        first=await request({'action':'confirm','id':draft['id']})
        repeated=await request({'action':'confirm','id':draft['id']})
        assert first==repeated and first['revision']==2
        after=await request({'action':'profile'})
        assert after['name'] is None and after['revision']==2
        await asyncio.to_thread(seed,'preference0','喜欢虚构星星')
        await asyncio.to_thread(seed,None,'一次虚构观星经历','experience')
        profile=await request({'action':'profile'})
        draft=await request({'action':'delete','field':'all','revision':profile['revision']})
        assert (await request({'action':'profile'}))==profile
        await request({'action':'confirm','id':draft['id']})
        after=await request({'action':'profile'})
        recalled=await asyncio.to_thread(memory.recall_snapshot,'虚构观星')
        assert after['name'] is None and not after['preferences'] and not recalled['memories']
        # Removing a cancelled draft cannot silently become a successful commit.
        assert (await request({'action':'confirm','id':'00000000-0000-4000-8000-000000000001'},409))['error']=='NOT_FOUND'
    return {'pending_does_not_delete':True,'cancel_preserves_profile':True,'stale_revision_rejected':True,
        'duplicate_confirm_is_idempotent':True,'delete_all_clears_profile_and_experiences':True,
        'unknown_confirmation_rejected':True,'final_revision':after['revision']}


def main():
    config=json.loads((SERVER/'data/.config.yaml').read_text(encoding='utf-8'))
    result={'ok':False,'source':'real_HTTP_bridge_and_isolated_Node_SQLite',
        'formal_database_used':False,'cloud_api_called':False,'hardware_verified':False}
    process=None
    try:
        with socket.socket() as probe:
            if probe.connect_ex(('127.0.0.1',8767))==0: raise RuntimeError('FIXTURE_PORT_OCCUPIED')
        log=ROOT/'.runtime/voice/memory-admin-fixture.log';log.parent.mkdir(parents=True,exist_ok=True)
        with log.open('wb') as output:
            process=subprocess.Popen([str(ROOT/'.tools/node22/node-v22.23.4-win-x64/node.exe'),
                str(ROOT/'scripts/start-memory-fixture.cjs')],cwd=ROOT,stdout=output,stderr=subprocess.STDOUT)
            client=PetMemoryClient('http://127.0.0.1:8767',config['Memory']['PetMemory']['token'],.3)
            deadline=time.monotonic()+12
            while True:
                try:
                    assert client.profile()['revision']==0
                    break
                except MemoryUnavailable:
                    if process.poll() is not None or time.monotonic()>deadline: raise
                    time.sleep(.1)
            result.update(asyncio.run(exercise(config)),ok=True)
    except Exception as error:
        result['error_type']=type(error).__name__
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
    (ROOT/'evaluation/device-memory-api-check.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))
    return 0 if result['ok'] else 1


if __name__=='__main__':raise SystemExit(main())
