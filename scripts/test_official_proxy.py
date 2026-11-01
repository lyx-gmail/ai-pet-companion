"""Cloud bridge boundaries, independent of cloud availability and physical care."""
import json
from pathlib import Path
import sys
import unittest
import asyncio
import tempfile
from unittest.mock import AsyncMock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from pet_official_proxy import PetSession, backend_mode, official_endpoint, relay, proxy_if_selected


def care(number=1,name='self.pet.feed',arguments=None):
    return {'type':'mcp','payload':{'jsonrpc':'2.0','id':number,'method':'tools/call',
        'params':{'name':name,'arguments':arguments or {},'_meta':{'pet_request_id':999}}}}


class BridgeChecks(unittest.TestCase):
    def voice(self,session):
        session.device({'type':'listen','state':'start','mode':'manual'})
        session.device(b'opus')
        session.device({'type':'listen','state':'stop'})
        return session.cloud({'type':'stt','text':'喂我一次'})

    def test_audio_provenance_and_cancel(self):
        session=PetSession(1)
        self.assertFalse(session.cloud({'type':'stt','text':'text only','pet_audio':True})['pet_audio'])
        with self.assertRaises(ValueError):session.cloud(care())
        self.assertTrue(self.voice(session)['pet_audio'])
        self.assertEqual(session.cloud(care())['payload']['params']['_meta'],{'pet_request_id':1})
        with self.assertRaises(ValueError):session.device({'type':'abort'})
        with self.assertRaises(ValueError):session.cloud(care(2))

    def test_retries_and_mutated_ids_are_safe_across_turns(self):
        session=PetSession(1);self.voice(session)
        def number(message):return session.cloud(message)['payload']['params']['_meta']['pet_request_id']
        self.assertEqual(number(care(7)),number(care(8)))
        with self.assertRaises(ValueError):number(care(7,'self.pet.pet'))
        session.cloud({'type':'tts','state':'stop'})
        with self.assertRaises(ValueError):number(care(9))
        self.voice(session)
        with self.assertRaises(ValueError):number(care(7))
        self.assertEqual(number(care(10)),2)
        with self.assertRaises(ValueError):number(care(11,arguments={'_pet_epoch':1}))
        with self.assertRaises(ValueError):number(care(12,'self.pet.set_sleep',{'sleeping':1}))

    def test_read_and_memory_rpc_ids_cannot_be_reused_for_care(self):
        for name in ('self.pet.get_state','self.pet.remember'):
            session=PetSession(1);self.voice(session)
            session.cloud(care(7,name))
            with self.assertRaises(ValueError):session.cloud(care(7,'self.pet.feed'))

    def test_unimplemented_tools_hidden_and_calls_rejected(self):
        session=PetSession(1)
        result=session.device({'type':'mcp','payload':{'id':1,'result':{'tools':[
            {'name':'self.pet.get_state'},{'name':'self.pet.memory.offer'},
            {'name':'self.system.reboot'},{'name':'self.pet.feed'}]}}})
        self.assertEqual([x['name'] for x in result['payload']['result']['tools']],
            ['self.pet.get_state','self.pet.feed'])
        with self.assertRaises(ValueError):session.cloud(care(1,'self.system.reboot'))

    def test_configuration_and_official_tls_fail_closed(self):
        self.assertEqual(backend_mode({}),'local')
        for value in ({'mode':'automatic'},{'mode':'official','extra':1}):
            with self.assertRaises(ValueError):backend_mode(value)
        for url in ('ws://api.tenclass.net/a','wss://evil.test/a','wss://api.tenclass.net:444/a'):
            with self.assertRaises(ValueError):official_endpoint({'url':url,'token':'private'})
        self.assertEqual(official_endpoint({'url':'wss://api.tenclass.net/a','token':'abc'})[1],'Bearer abc')

class RelayChecks(unittest.IsolatedAsyncioTestCase):
    async def test_real_sockets_forward_audio_tool_metadata_and_cancel_upstream(self):
        import websockets
        closed=asyncio.Event();failures=[]
        async def cloud(socket):
            try:
                self.assertEqual(json.loads(await socket.recv())['type'],'listen')
                self.assertEqual(await socket.recv(),b'opus')
                await socket.send(json.dumps({'type':'stt','text':'feed'}))
                await socket.send(json.dumps(care(42)))
                await socket.wait_closed()
            except Exception as error:failures.append(error)
            finally:closed.set()
        async with websockets.serve(cloud,'127.0.0.1',0) as upstream:
            url='ws://127.0.0.1:'+str(upstream.sockets[0].getsockname()[1])
            async def bridge(socket):
                try:await relay(socket,url,{},1)
                except ValueError:pass # abort invalidates and closes this cloud channel
            async with websockets.serve(bridge,'127.0.0.1',0) as server:
                async with websockets.connect('ws://127.0.0.1:'+str(server.sockets[0].getsockname()[1])) as client:
                    await client.send(json.dumps({'type':'listen','state':'start'}))
                    await client.send(b'opus')
                    transcript=json.loads(await asyncio.wait_for(client.recv(),3))
                    self.assertTrue(transcript['pet_audio'])
                    request=json.loads(await asyncio.wait_for(client.recv(),3))
                    self.assertEqual(request['payload']['params']['_meta'],{'pet_request_id':1})
                    await client.send(json.dumps({'type':'abort'}))
                    await asyncio.wait_for(closed.wait(),3)
        self.assertFalse(failures)

    async def test_missing_mode_uses_local_without_touching_connection(self):
        socket=AsyncMock()
        with patch('pet_official_proxy.discover') as discover:
            self.assertFalse(await proxy_if_selected(socket,{}))
            discover.assert_not_called();socket.close.assert_not_called()

    async def test_invalid_mode_fails_closed_without_cloud_contact(self):
        root=Path(__file__).resolve().parents[1]
        (root/'.runtime/checks').mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root/'.runtime/checks') as folder:
            path=Path(folder)/'mode.json';path.write_text('{"mode":"automatic"}',encoding='utf-8')
            socket=AsyncMock()
            with patch('pet_official_proxy.discover') as discover:
                self.assertTrue(await proxy_if_selected(socket,{'pet_official':{'mode_file':str(path)}}))
                discover.assert_not_called();socket.close.assert_awaited_once()
                self.assertNotIn('automatic',socket.send.call_args.args[0])

    async def test_redirect_never_receives_cloud_credentials(self):
        import websockets
        contacted=[]
        async def forbidden(socket):contacted.append(True)
        async with websockets.serve(forbidden,'127.0.0.1',0) as other:
            destination='ws://127.0.0.1:'+str(other.sockets[0].getsockname()[1])
            def redirect(socket,request):
                response=socket.respond(302,'Redirect forbidden')
                response.headers['Location']=destination
                return response
            async with websockets.serve(forbidden,'127.0.0.1',0,process_request=redirect) as upstream:
                with self.assertRaises(Exception):
                    await relay(AsyncMock(),'ws://127.0.0.1:'+str(upstream.sockets[0].getsockname()[1]),
                        {'Authorization':'Bearer test-secret'},1)
        self.assertFalse(contacted)


if __name__=='__main__':unittest.main()
