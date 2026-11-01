"""Authenticated local device fixture: silent Opus + real memory invalidation, no AI calls."""
import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
SERVER=ROOT/'.tools/upstream/xiaozhi-esp32-server/main/xiaozhi-server'
FOLDER=ROOT/'.runtime/audio-cancel'


async def run(config):
    import websockets
    import opuslib_next
    from aiohttp import web
    from core.api.ota_handler import OTAHandler
    from core.auth import AuthManager
    from core.pet_network import device_allowed
    from core.connection import ConnectionHandler
    from core.providers.memory.mem_pet.mem_pet import MemoryProvider
    from core.utils.dialogue import Message
    config=deepcopy(config);config['Memory']['PetMemory']['endpoint']='http://127.0.0.1:8767'
    ota=OTAHandler(config)
    empty=FOLDER/'empty-bin';empty.mkdir(exist_ok=True);ota.bin_dir=str(empty)
    http=web.Application();http.router.add_post('/xiaozhi/ota/',ota.handle_post)
    runner=web.AppRunner(http);await runner.setup()
    await web.TCPSite(runner,config['server']['ip'],8003).start()
    auth=AuthManager(config['server']['auth_key'],config['server'].get('auth',{}).get('expire_seconds'))
    async def handler(ws):
        headers=ws.request.headers;token=headers.get('Authorization','')
        if (not device_allowed(headers,config) or not token.startswith('Bearer ') or
                not auth.verify_token(token[7:],headers.get('Client-ID',''),headers.get('Device-ID',''))):
            await ws.close(code=1008);return
        conn=ConnectionHandler(config,None,None,None,None,None)
        conn.websocket=ws;conn.loop=asyncio.get_running_loop();conn.sentence_id='cancel-fixture'
        conn.memory=MemoryProvider(config['Memory']['PetMemory'])
        conn.memory.init_memory(config['Memory']['PetMemory']['expected_device_id'],None,pet_connection=conn)
        conn.dialogue.put(Message('system','仅使用已确认资料。<memory></memory>'))
        conn.dialogue.put(Message('user','你好'))
        receiver=None
        try:
            hello=json.loads(await asyncio.wait_for(ws.recv(),5))
            if hello.get('type')!='hello':raise ValueError('HELLO_REQUIRED')
            await ws.send(json.dumps({'type':'hello','version':1,'transport':'websocket','session_id':conn.session_id,
                'audio_params':{'format':'opus','sample_rate':24000,'channels':1,'frame_duration':60}}))
            async def drain_input():
                async for _ in ws:pass
            receiver=asyncio.create_task(drain_input())
            await conn.memory.query_pet_memory('你好','cancel-fixture')
            await ws.send(json.dumps({'type':'tts','state':'start','session_id':conn.session_id}))
            encoder=opuslib_next.Encoder(24000,1,opuslib_next.APPLICATION_AUDIO)
            packet=encoder.encode(bytes(1440*2),1440)
            for _ in range(200):await ws.send(packet)
            (FOLDER/'audio-ready').write_text('ready',encoding='ascii')
            deadline=asyncio.get_running_loop().time()+20
            while not (FOLDER/'invalidate').exists():
                if asyncio.get_running_loop().time()>deadline:raise ValueError('TRIGGER_TIMEOUT')
                await asyncio.sleep(.05)
            client=conn.memory.client;profile=await asyncio.to_thread(client.profile)
            draft=await asyncio.to_thread(client.request,'propose',{
                'kind':'profile','op':'delete','field':'name','expectedRevision':profile['revision']})
            receipt=await asyncio.to_thread(client.request,'confirm',{'id':draft['id'],'requestId':'fixture-'+draft['id']})
            # ESP closes its audio path before the library's default 10s close
            # handshake timeout completes; device queue clearing is checked separately.
            await asyncio.wait_for(ws.wait_closed(),15)
            (FOLDER/'result.json').write_text(json.dumps({'ok':conn.client_abort and conn.stop_event.is_set(),
                'revision':receipt['revision'],'sent_silent_opus_packets':200,'model_called':False}),encoding='utf-8')
        except Exception:
            import traceback
            (FOLDER/'error.log').write_text(traceback.format_exc(),encoding='utf-8')
            raise
        finally:
            if receiver is not None:
                receiver.cancel();await asyncio.gather(receiver,return_exceptions=True)
            await conn.close(ws)
    try:
        async with websockets.serve(handler,config['server']['ip'],8000,ping_interval=None):
            (FOLDER/'server-ready').write_text('ready',encoding='ascii')
            await asyncio.Future()
    finally:await runner.cleanup()


if __name__=='__main__':
    binaries=ROOT/'.tools/voice-native/bin'
    os.environ['PATH']=str(binaries)+os.pathsep+os.environ['PATH']
    sys.path.insert(0,str(SERVER));os.chdir(SERVER)
    with os.add_dll_directory(str(binaries)):
        import core.connection
        from config.config_loader import load_config
        asyncio.run(run(asyncio.run(load_config())))
