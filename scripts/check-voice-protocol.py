"""Real upstream auth + hello on an ephemeral loopback port; client is software."""
from pathlib import Path
from datetime import date
import asyncio
import contextlib
import copy
import io
import ipaddress
import json
import os
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


async def exercise(config):
    import websockets
    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer
    from core.api.ota_handler import OTAHandler
    from core.auth import AuthManager
    from core.websocket_server import WebSocketServer
    config = copy.deepcopy(config)
    device = '02:00:00:00:00:01' # fictitious local protocol fixture, never saved as device binding
    client = 'pet-local-protocol-test'
    config['Memory']['PetMemory']['expected_device_id'] = device
    server = WebSocketServer(config)
    headers = {'Device-ID':device,'Client-ID':client}
    hello = {'type':'hello','version':1,'transport':'websocket','features':{'mcp':False},
             'audio_params':{'format':'opus','sample_rate':16000,'channels':1,'frame_duration':60}}
    ota = OTAHandler(config)
    application = web.Application()
    application.router.add_post('/xiaozhi/ota/', ota.handle_post)
    with tempfile.TemporaryDirectory(prefix='pet-ota-empty-') as bins:
        ota.bin_dir = bins
        # Discovery uses a deterministic loopback address in this software test.
        with patch('core.api.ota_handler.get_local_ip', return_value='127.0.0.1'):
            async with TestClient(TestServer(application, host='127.0.0.1')) as http:
                async with http.post('/xiaozhi/ota/', headers={'Device-ID':'02:00:00:00:00:02','Client-ID':client}, json={}) as response:
                    if response.status!=403 or (await response.json()).get('error')!='DEVICE_NOT_BOUND':
                        raise RuntimeError('OTA accepted an unbound device')
                async with http.post('/xiaozhi/ota/', headers=headers,
                                     json={'application':{'version':'2.0.4'}}) as response:
                    discovery = await response.json()
                    if response.status!=200:
                        raise RuntimeError('Bound discovery failed')
    token = discovery.get('websocket',{}).get('token','')
    if not AuthManager(config['server']['auth_key']).verify_token(token,client,device):
        raise RuntimeError('OTA did not issue a valid bound token')
    if discovery.get('firmware',{}).get('url'):
        raise RuntimeError('Protocol fixture unexpectedly offered a firmware update')
    async with websockets.serve(server._handle_connection,'127.0.0.1',0,
                                process_request=server._http_response,ping_interval=None) as listener:
        port = listener.sockets[0].getsockname()[1]
        url = f'ws://127.0.0.1:{port}/xiaozhi/v1/'
        rejected = False
        async with websockets.connect(url,additional_headers=headers) as socket:
            try:
                response = await asyncio.wait_for(socket.recv(),3)
                rejected = response=='认证失败'
            except websockets.exceptions.ConnectionClosed:
                rejected = True
        if not rejected:
            raise RuntimeError('Unauthenticated client was not rejected')
        other = '02:00:00:00:00:02'
        other_headers = {'Device-ID':other,'Client-ID':client,
                         'Authorization':'Bearer '+AuthManager(config['server']['auth_key']).generate_token(client,other)}
        async with websockets.connect(url,additional_headers=other_headers) as socket:
            try:
                await asyncio.wait_for(socket.recv(),3)
            except websockets.exceptions.ConnectionClosed as closed:
                if closed.code!=1008:
                    raise RuntimeError('Unexpected unbound-device close status')
            else:
                raise RuntimeError('WebSocket accepted another signed device')
        headers['Authorization'] = 'Bearer '+token
        async with websockets.connect(url,additional_headers=headers) as socket:
            await socket.send(json.dumps(hello))
            reply = json.loads(await asyncio.wait_for(socket.recv(),5))
            if reply.get('type')!='hello' or reply.get('audio_params')!=hello['audio_params']:
                raise RuntimeError('Unexpected server hello or audio negotiation')
            if not reply.get('session_id'):
                raise RuntimeError('Server did not establish a session')
            await asyncio.sleep(0.3)
        await asyncio.sleep(0.3)
    return {'unauthenticated_rejected':True,'authenticated_hello':True,
            'unbound_ota_rejected':True,'unbound_signed_websocket_rejected':True,
            'bound_ota_token_used_for_hello':True,'ota_local_ip_fixture':True,
            'audio_params':reply['audio_params'],'configured_encoder_rate':config['xiaozhi']['audio_params']['sample_rate']}


def main():
    attempts = []
    def audit(event,args):
        if event=='socket.connect':
            address = args[1]
            try:
                allowed = isinstance(address,tuple) and ipaddress.ip_address(address[0]).is_loopback
            except ValueError:
                allowed = False
            if not allowed:
                attempts.append('blocked')
                raise RuntimeError('Protocol check blocks all non-loopback connections')
    sys.addaudithook(audit)
    binaries = ROOT/'.tools/voice-native/bin'
    source = ROOT/'.tools/upstream/xiaozhi-esp32-server/main/xiaozhi-server'
    os.environ['PATH'] = str(binaries)+os.pathsep+os.environ['PATH']
    os.chdir(source)
    sys.path.insert(0,str(source))
    result = {'date':date.today().isoformat(),'software_client':True,'hardware_voice_verified':False,
              'non_loopback_connections_blocked':True}
    try:
        with os.add_dll_directory(str(binaries)),contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            import app
            from config.config_loader import load_config
            config = asyncio.run(load_config())
            if config['server']['ip']!='127.0.0.1' or config['server']['auth'].get('enabled') is not True:
                raise RuntimeError('Unsafe voice config')
            result.update(asyncio.run(asyncio.wait_for(exercise(config),20)))
            from loguru import logger
            logger.remove()
        if attempts:
            raise RuntimeError('Unexpected external connection attempt')
        result['ok'] = True
    except Exception as error:
        result['ok'] = False
        result['error_type'] = type(error).__name__
    result['external_connection_attempts'] = len(attempts)
    (ROOT/'evaluation/voice-protocol-check.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))
    return 0 if result['ok'] else 1


if __name__=='__main__':
    raise SystemExit(main())
