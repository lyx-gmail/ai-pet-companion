"""Real RAM memory, pinned connection/TTS queues and loopback WebSocket; no model calls."""
import asyncio
import contextlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
SERVER=ROOT/'.tools/upstream/xiaozhi-esp32-server/main/xiaozhi-server'


async def exercise(config):
    import websockets
    from core.connection import ConnectionHandler
    from core.providers.memory.mem_pet.mem_pet import MemoryProvider
    from core.providers.memory.mem_pet.client import PetMemoryClient
    from core.providers.tts.edge import TTSProvider
    from core.utils.dialogue import Message
    settings=dict(config['Memory']['PetMemory'],endpoint='http://127.0.0.1:8767')
    client=PetMemoryClient(settings['endpoint'],settings['token'])
    formal=PetMemoryClient(config['Memory']['PetMemory']['endpoint'],settings['token'])
    original=await asyncio.to_thread(formal.profile)
    async def change(value,op='set'):
        current=await asyncio.to_thread(client.profile)
        draft=await asyncio.to_thread(client.request,'propose',dict(kind='profile',op=op,field='name',
            value=value,source=value,quote=value,expectedRevision=current['revision']))
        return await asyncio.to_thread(client.request,'confirm',{'id':draft['id'],'requestId':'fixture-'+draft['id']})
    await change('旧测试称呼')
    evidence=[]
    for operation,value in (('set','新测试称呼'),('delete','新测试称呼')):
        ready=asyncio.Event();finished=asyncio.Event();state={}
        async def handler(ws):
            conn=ConnectionHandler(config,None,None,None,None,None)
            state['conn']=conn
            conn.websocket=ws;conn.loop=asyncio.get_running_loop();conn.sentence_id='fixture-turn'
            conn.tts=TTSProvider(config['TTS']['EdgeTTS'],True);conn.tts.conn=conn
            conn.memory=MemoryProvider(settings)
            conn.memory.init_memory(settings['expected_device_id'],None,pet_connection=conn)
            conn.dialogue.put(Message('system','仅使用已确认记忆。<memory></memory>'))
            conn.dialogue.put(Message('user','你好'))
            try:
                await conn.memory.query_pet_memory('你好','fixture-turn')
                conn.dialogue.put(Message('assistant','含有旧资料的待发送回答'))
                conn.tts._sentence_text_map['fixture-turn']='含有旧资料的语音'
                conn.tts.tts_text_queue.put('old-text');conn.tts.tts_audio_queue.put(b'old-audio')
                ready.set()
                await ws.wait_closed()
            finally:
                await conn.close(ws);finished.set()
        async with websockets.serve(handler,'127.0.0.1',0) as listener:
            port=listener.sockets[0].getsockname()[1]
            async with websockets.connect(f'ws://127.0.0.1:{port}') as ws:
                await asyncio.wait_for(ready.wait(),5)
                started=time.monotonic();await change(value,operation)
                await asyncio.wait_for(ws.wait_closed(),5)
                await asyncio.wait_for(finished.wait(),5)
                conn=state['conn']
                assert conn.client_abort and conn.sentence_id is None and conn.stop_event.is_set()
                assert conn.tts.tts_text_queue.empty() and conn.tts.tts_audio_queue.empty()
                assert not conn.tts._sentence_text_map and conn.memory.watch_task is None
                assert all(message.role=='system' for message in conn.dialogue.dialogue)
                evidence.append({'operation':operation,'close_code':ws.close_code,
                    'observed_seconds':round(time.monotonic()-started,3),'queues_empty':True,
                    'personal_history_cleared':True,'watch_task_stopped':True})
    assert await asyncio.to_thread(formal.profile)==original
    return evidence


def main():
    config=json.loads((SERVER/'data/.config.yaml').read_text(encoding='utf-8'))
    result={'ok':False,'source':'isolated_RAM_HTTP_pinned_ConnectionHandler_TTS_queues_real_loopback_WebSocket',
        'model_called':False,'audio_stream_generated':False,'hardware_verified':False}
    process=None
    folder=ROOT/'.runtime/voice';folder.mkdir(parents=True,exist_ok=True)
    try:
        with socket.socket() as probe:probe.bind(('127.0.0.1',8767))
        with (folder/'cancel-node.log').open('wb') as output:
            process=subprocess.Popen([str(ROOT/'.tools/node22/node-v22.23.4-win-x64/node.exe'),
                str(ROOT/'scripts/start-memory-fixture.cjs')],cwd=ROOT,stdout=output,stderr=output,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        deadline=time.monotonic()+10
        while True:
            with socket.socket() as probe:
                if probe.connect_ex(('127.0.0.1',8767))==0:break
            if process.poll() is not None or time.monotonic()>deadline:raise RuntimeError('FIXTURE_NOT_READY')
            time.sleep(.1)
        binaries=ROOT/'.tools/voice-native/bin'
        os.environ['PATH']=str(binaries)+os.pathsep+os.environ['PATH']
        sys.path.insert(0,str(SERVER));os.chdir(SERVER)
        with os.add_dll_directory(str(binaries)),(folder/'cancel-flow.log').open('w',encoding='utf-8') as output:
            with contextlib.redirect_stdout(output),contextlib.redirect_stderr(output):
                import core.connection  # Logging configuration precedes asyncio.run, as in normal startup.
                from config.config_loader import load_config
                config=asyncio.run(load_config())
                result['cases']=asyncio.run(exercise(config))
        result.update(ok=True,formal_memory_unchanged=True)
    except Exception as error:
        result['error_type']=type(error).__name__
        import traceback
        (folder/'cancel-error.log').write_text(traceback.format_exc(),encoding='utf-8')
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
    (ROOT/'evaluation/voice-memory-cancel-flow-check.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result));return 0 if result['ok'] else 1


if __name__=='__main__':raise SystemExit(main())
