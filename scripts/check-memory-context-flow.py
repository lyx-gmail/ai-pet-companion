"""Real isolated store + HTTP memory provider + pinned dialogue render; no LLM/hardware."""
import asyncio
import contextlib
import io
import json
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
from urllib.request import Request,build_opener,ProxyHandler

ROOT=Path(__file__).resolve().parents[1]


async def exercise(token,prompt):
    server=ROOT/'.tools/upstream/xiaozhi-esp32-server/main/xiaozhi-server'
    sys.path.insert(0,str(server))
    from core.providers.memory.mem_pet.mem_pet import MemoryProvider
    from core.utils.dialogue import Dialogue,Message
    opener=build_opener(ProxyHandler({}))
    def post(path,body):
        request=Request('http://127.0.0.1:8767/api/'+path,data=json.dumps(body,ensure_ascii=False).encode('utf-8'),
                        headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
        with opener.open(request,timeout=3) as response: return json.load(response)
    def change(value,revision,operation='set'):
        source='以后叫我'+value
        draft=post('propose',dict(kind='profile',op=operation,field='name',value=value,
                                 source=source,quote=value,expectedRevision=revision))
        return post('confirm',{'id':draft['id'],'requestId':'fixture-'+draft['id']})
    conn=SimpleNamespace(dialogue=Dialogue(),sentence_id='one',client_abort=False,stop_event=threading.Event())
    conn.dialogue.put(Message('system',prompt))
    provider=MemoryProvider({'endpoint':'http://127.0.0.1:8767','token':token,'expected_device_id':'fixture'})
    provider.init_memory('fixture',None,pet_connection=conn)
    async def ask(number,query):
        conn.sentence_id=str(number); conn.dialogue.put(Message('user',query))
        context=await provider.query_pet_memory(query,str(number))
        return json.dumps(conn.dialogue.get_llm_dialogue_with_memory(context),ensure_ascii=False)
    assert change('虚构旧称呼',0)['revision']==1
    first=await ask(1,'你好')
    assert '虚构旧称呼' in first
    conn.dialogue.put(Message('assistant','你叫虚构旧称呼'))
    conn.dialogue.put(Message('tool','虚构旧称呼'))
    assert change('虚构新称呼',1)['revision']==2
    rendered=await ask(2,'我叫什么？')
    assert '虚构旧称呼' not in rendered and '虚构新称呼' in rendered
    conn.dialogue.put(Message('assistant','你叫虚构新称呼'))
    assert change('虚构新称呼',2,'delete')['revision']==3
    rendered=await ask(3,'你知道我的称呼吗？')
    assert '虚构新称呼' not in rendered and '虚构旧称呼' not in rendered
    previous=Message('assistant','我们刚才聊到星星'); conn.dialogue.put(previous)
    await ask(4,'继续说')
    assert previous in conn.dialogue.dialogue
    conn.dialogue.put(Message('assistant','不应在服务故障后复用的虚构个人资料'))
    return conn,provider,ask


def main():
    config=json.loads((ROOT/'.tools/upstream/xiaozhi-esp32-server/main/xiaozhi-server/data/.config.yaml').read_text(encoding='utf-8'))
    token=config['Memory']['PetMemory']['token']
    result={'source':'real_isolated_Node_store_HTTP_provider_and_pinned_dialogue_renderer','cloud_api_called':False,
            'hardware_verified':False,'fixture_only':True,'ok':False}
    process=None
    log=ROOT/'.runtime/voice/context-fixture.log'
    try:
        with socket.socket() as sock:
            if sock.connect_ex(('127.0.0.1',8767))==0: raise RuntimeError('FIXTURE_PORT_IN_USE')
        with log.open('wb') as output:
            process=subprocess.Popen([str(ROOT/'.tools/node22/node-v22.23.4-win-x64/node.exe'),str(ROOT/'scripts/start-memory-fixture.cjs')],
                                     cwd=ROOT,stdout=output,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        for _ in range(40):
            if process.poll() is not None: raise RuntimeError('FIXTURE_START_FAILED')
            with socket.socket() as sock:
                if sock.connect_ex(('127.0.0.1',8767))==0: break
            time.sleep(.1)
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            # Match real startup: config/logger imports run before asyncio.run.
            sys.path.insert(0,str(ROOT/'.tools/upstream/xiaozhi-esp32-server/main/xiaozhi-server'))
            from core.providers.memory.mem_pet.mem_pet import MemoryProvider
            conn,provider,ask=asyncio.run(exercise(token,config['prompt']))
            process.terminate(); process.wait(timeout=5)
            rendered=asyncio.run(ask(5,'服务还好吗？'))
            assert '不应在服务故障后复用的虚构个人资料' not in rendered and '暂时不可用' in rendered
        result.update(ok=True,correction_old_chat_and_tool_history_removed=True,deletion_not_recalled=True,
                      unchanged_revision_preserves_chat=True,outage_removes_personal_history=True,
                      official_memory_database_unchanged_by_design=True,actual_quick_prompt_render_verified=True)
    except Exception as error:
        result['error_type']=type(error).__name__
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
    (ROOT/'evaluation/voice-memory-context-check.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))
    return 0 if result['ok'] else 1


if __name__=='__main__': raise SystemExit(main())
