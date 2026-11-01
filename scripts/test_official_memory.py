"""Confirmed memory must arrive through a current state result before speech."""
import asyncio
from copy import deepcopy
from pathlib import Path
import sys
import unittest
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend/xiaozhi_memory'))
from pet_official_memory import MemoryGate, DeviceRpc
from pet_official_proxy import PetSession


class Client:
    revision=1
    failed=False
    def recall_snapshot(self,query):
        if self.failed:raise RuntimeError('private detail')
        return {'profile':{'revision':self.revision,'name':'测试小林','preferences':[]},'context':'confirmed data '+str(self.revision)}
    def profile(self):
        if self.failed:raise RuntimeError('private detail')
        return {'revision':self.revision}


def request(number=7):
    return {'type':'mcp','payload':{'id':number,'method':'tools/call','params':{'name':'self.pet.get_state','arguments':{}}}}


def response(number=7):
    return {'type':'mcp','payload':{'id':number,'result':{'content':[{'type':'text','text':'{"satiety":95}'}],'isError':False}}}


class MemoryChecks(unittest.IsolatedAsyncioTestCase):
    def voice(self,session):
        session.device({'type':'listen','state':'start'})
        session.device(b'opus')
        session.cloud({'type':'stt','text':'我叫什么'})

    async def test_state_result_contains_confirmed_memory_and_gates_speech(self):
        client=Client();gate=MemoryGate(client);session=PetSession(1);self.voice(session)
        with self.assertRaises(ValueError):gate.allow_audio(session)
        await gate.cloud(request(),session)
        with self.assertRaises(ValueError):gate.allow_audio(session)
        message=await gate.device(response(),session)
        self.assertEqual(len(message['payload']['result']['content']),1)
        self.assertIn('confirmed_memory',message['payload']['result']['content'][0]['text'])
        self.assertIn('confirmed data 1',message['payload']['result']['content'][-1]['text'])
        gate.allow_audio(session)
        self.assertNotIn('confirmed data',str(response()))

    async def test_late_result_revision_change_and_outage_never_release_speech(self):
        for mutation in ('revision','outage','newturn'):
            client=Client();gate=MemoryGate(client);session=PetSession(1);self.voice(session)
            await gate.cloud(request(),session)
            if mutation=='revision':client.revision=2
            if mutation=='outage':client.failed=True
            if mutation=='newturn':
                session.cloud({'type':'tts','state':'stop'});self.voice(session)
            with self.assertRaises((ValueError,RuntimeError)):await gate.device(response(),session)
            with self.assertRaises(ValueError):gate.allow_audio(session)

    async def test_each_new_turn_requires_fresh_memory_and_failed_device_result_is_not_ready(self):
        client=Client();gate=MemoryGate(client);session=PetSession(1);self.voice(session)
        await gate.cloud(request(),session)
        failed=response();failed['payload']['result']['isError']=True
        await gate.device(failed,session)
        with self.assertRaises(ValueError):gate.allow_audio(session)
        await gate.device(response(),session);gate.allow_audio(session)
        session.cloud({'type':'tts','state':'stop'});self.voice(session)
        with self.assertRaises(ValueError):gate.allow_audio(session)
        with self.assertRaises(ValueError):await gate.cloud(request(),session)

    async def test_watcher_detects_changed_memory_without_waiting_for_next_turn(self):
        client=Client();gate=MemoryGate(client);session=PetSession(1);self.voice(session)
        await gate.cloud(request(),session);await gate.device(response(),session)
        client.revision=2
        with self.assertRaises(ValueError):await asyncio.wait_for(gate.watch(session,interval=.001),1)

    async def test_virtual_remember_requires_literal_intent_and_device_decision(self):
        class DraftClient(Client):
            def __init__(self):self.operations=[];self.revision=1
            def request(self,operation,body):
                self.operations.append(operation)
                if operation=='remember':return {'status':'PENDING','id':'draft','field':'name','value':'测试小林','expiresAt':time.time()*1000+30000}
                if operation=='confirm':self.revision+=1;return {'ok':True}
                return {'ok':True}
        for decision in ('confirmed','cancelled'):
            client=DraftClient();gate=MemoryGate(client);session=PetSession(1);self.voice(session)
            await gate.cloud(request(),session);await gate.device(response(),session)
            async def call(name,args):return {'ok':True,'id':'draft','status':'pending' if name.endswith('offer') else decision}
            gate.rpc=SimpleNamespace(call=call)
            with self.assertRaises(ValueError):await gate.remember(session)
            session.transcript='请记住，以后叫我测试小林'
            await gate.cloud({'type':'stt','text':session.transcript},session)
            with self.assertRaises(ValueError):gate.allow_audio(session)
            result=await gate.remember(session)
            gate.allow_audio(session)
            self.assertEqual('confirm' in client.operations,decision=='confirmed')
            self.assertEqual('cancel' in client.operations,decision=='cancelled')
            operations=list(client.operations)
            self.assertEqual(await gate.remember(session),result)
            self.assertEqual(client.operations,operations)


class RpcChecks(unittest.IsolatedAsyncioTestCase):
    async def test_only_matching_device_reply_can_complete_internal_confirmation_rpc(self):
        sent=[]
        async def send(raw):sent.append(json.loads(raw))
        rpc=DeviceRpc(send,lambda:'cloud-session',lambda:True)
        task=asyncio.create_task(rpc.call('self_pet_memory_status',{'id':'draft'}))
        await asyncio.sleep(0)
        number=sent[0]['payload']['id']
        self.assertGreaterEqual(number,0x70000000)
        self.assertFalse(rpc.accept({'type':'mcp','payload':{'id':1,'result':{}}}))
        self.assertFalse(task.done())
        self.assertTrue(rpc.accept({'type':'mcp','payload':{'id':number,'result':{
            'content':[{'type':'text','text':'{"ok":true,"id":"draft","status":"confirmed"}'}]}}}))
        self.assertEqual((await task)['status'],'confirmed')
        with self.assertRaises(ValueError):await rpc.call('self.pet.feed',{})

    async def test_timeout_and_cancel_drop_late_replies(self):
        send=AsyncMock();rpc=DeviceRpc(send,lambda:'session',lambda:True)
        with self.assertRaises(asyncio.TimeoutError):await rpc.call('self_pet_memory_status',{'id':'draft'},timeout=.001)
        number=json.loads(send.call_args.args[0])['payload']['id']
        self.assertTrue(rpc.accept({'type':'mcp','payload':{'id':number,'result':{}}}))
        task=asyncio.create_task(rpc.call('self_pet_memory_status',{'id':'draft'}))
        await asyncio.sleep(0);rpc.close()
        with self.assertRaises(asyncio.CancelledError):await task


if __name__=='__main__':unittest.main()
