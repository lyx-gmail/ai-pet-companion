import importlib.util
import asyncio
import json
from pathlib import Path
import sys
import threading
from types import ModuleType,SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
PACKAGE=ROOT/'backend/xiaozhi_memory/mem_pet'
package=ModuleType('pet_revision_fixture'); package.__path__=[str(PACKAGE)]
base=ModuleType('core.providers.memory.base')
class Base:
    def __init__(self,config): self.config=config; self.role_id=None
    def init_memory(self,role_id,llm,**kwargs): self.role_id=role_id
base.MemoryProviderBase=Base
spec=importlib.util.spec_from_file_location('pet_revision_fixture.mem_pet',PACKAGE/'mem_pet.py')
provider_module=importlib.util.module_from_spec(spec)
with patch.dict(sys.modules,{'pet_revision_fixture':package,'core.providers.memory.base':base}):
    spec.loader.exec_module(provider_module)
spec=importlib.util.spec_from_file_location('actual_pet_dialogue',ROOT/'.tools/upstream/xiaozhi-esp32-server/main/xiaozhi-server/core/utils/dialogue.py')
dialogue_module=importlib.util.module_from_spec(spec); spec.loader.exec_module(dialogue_module)
Message,Dialogue=dialogue_module.Message,dialogue_module.Dialogue


class RevisionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.conn=SimpleNamespace(dialogue=Dialogue(),sentence_id='one',client_abort=False,stop_event=threading.Event())
        self.conn.dialogue.put(Message('system','保持简短。<memory></memory>'))
        self.conn.dialogue.put(Message('user','你好'))
        self.provider=provider_module.MemoryProvider({'expected_device_id':'fixture','token':'fictional-token'})
        self.provider.init_memory('fixture',None,pet_connection=self.conn)
        self.snapshot={'profile':{'revision':1},'context':'已确认称呼：旧称呼'}
        self.provider.client=SimpleNamespace(recall=lambda q:self.snapshot['context'],recall_snapshot=lambda q:self.snapshot,
                                             profile=lambda:self.snapshot['profile'],
                                             request=lambda *args:{'status':'NO_PROPOSAL'})
        await self.provider.query_pet_memory('你好','one')

    async def asyncTearDown(self):
        if hasattr(self.provider,'stop_memory_watch'):await self.provider.stop_memory_watch()

    async def test_active_revision_change_aborts_queued_reply_and_closes_connection(self):
        events=[]
        async def close(**kwargs):events.append('closed')
        self.conn.websocket=SimpleNamespace(close=close)
        self.conn.clear_queues=lambda:events.append('cleared')
        self.conn.dialogue.put(Message('assistant','旧称呼的旧回答'))
        self.conn.tts=SimpleNamespace(_sentence_text_map={'old':'旧称呼'})
        self.snapshot={'profile':{'revision':2},'context':''}
        self.assertTrue(await self.provider.check_memory_revision())
        self.assertTrue(self.conn.client_abort)
        self.assertTrue(self.conn.stop_event.is_set())
        self.assertIsNone(self.conn.sentence_id)
        self.assertEqual(events,['cleared','closed'])
        self.assertEqual([m.role for m in self.conn.dialogue.dialogue],['system'])
        self.assertEqual(self.conn.tts._sentence_text_map,{})

    async def test_unchanged_live_revision_does_not_interrupt_and_own_query_is_not_cancelled(self):
        self.assertFalse(await self.provider.check_memory_revision())
        self.provider.querying=1
        self.snapshot={'profile':{'revision':2},'context':''}
        self.assertFalse(await self.provider.check_memory_revision())
        self.assertFalse(self.conn.client_abort)
        self.provider.querying=0

    async def test_late_watch_result_does_not_cancel_a_new_snapshot(self):
        def late():
            self.provider.last_revision=2
            return {'revision':1}
        self.provider.client.profile=late
        self.assertFalse(await self.provider.check_memory_revision())
        self.assertFalse(self.conn.client_abort)

    async def test_watch_stops_without_leaking_task(self):
        self.assertIsNotNone(self.provider.watch_task)
        task=self.provider.watch_task
        await self.provider.stop_memory_watch()
        self.assertTrue(task.done())
        self.assertIsNone(self.provider.watch_task)

    async def test_background_watch_detects_change_without_another_user_turn(self):
        closed=asyncio.Event()
        async def close(**kwargs):closed.set()
        self.conn.websocket=SimpleNamespace(close=close)
        self.conn.clear_queues=lambda:None
        self.snapshot={'profile':{'revision':2},'context':''}
        await asyncio.wait_for(closed.wait(),2)
        self.assertTrue(self.conn.client_abort)

    async def test_failed_watch_does_not_prevent_connection_cleanup(self):
        await self.provider.stop_memory_watch()
        async def failed():raise ConnectionError('closed fixture connection')
        self.provider.watch_task=asyncio.create_task(failed())
        await asyncio.sleep(0)
        await self.provider.stop_memory_watch()
        self.assertIsNone(self.provider.watch_task)

    async def test_unavailable_or_invalid_revision_cannot_keep_personal_reply_running(self):
        for invalid in (True,'not-a-revision'):
            self.conn.stop_event.clear();self.conn.client_abort=False;self.provider.last_revision=1
            async def close(**kwargs):pass
            self.conn.websocket=SimpleNamespace(close=close);self.conn.clear_queues=lambda:None
            self.provider.client.profile=lambda:{'revision':invalid}
            self.assertTrue(await self.provider.check_memory_revision())
            self.assertTrue(self.conn.client_abort)

    def new_turn(self,query):
        self.conn.sentence_id='two'
        user=Message('user',query); self.conn.dialogue.put(user)
        return user

    async def test_correction_removes_old_tool_and_chat_history_before_real_dialogue_render(self):
        self.conn.dialogue.put(Message('assistant','你叫旧称呼'))
        self.conn.dialogue.put(Message('tool','旧称呼'))
        self.conn.tts=SimpleNamespace(_sentence_text_map={'old':'你叫旧称呼'})
        current=self.new_turn('我叫什么？')
        self.snapshot={'profile':{'revision':2},'context':'已确认称呼：新称呼'}
        context=await self.provider.query_pet_memory('我叫什么？','two')
        rendered=json.dumps(self.conn.dialogue.get_llm_dialogue_with_memory(context),ensure_ascii=False)
        self.assertNotIn('旧称呼',rendered); self.assertIn('新称呼',rendered)
        self.assertIs(self.conn.dialogue.dialogue[-1],current)
        self.assertEqual([m.role for m in self.conn.dialogue.dialogue],['system','user'])
        self.assertEqual(self.conn.tts._sentence_text_map,{})

    async def test_delete_and_memory_outage_do_not_fall_back_to_personal_chat_history(self):
        for outage in (False,True):
            self.conn.dialogue.put(Message('assistant','你叫旧称呼'))
            self.new_turn('你知道我的称呼吗？')
            self.snapshot={'profile':{'revision':3},'context':'尚无已确认称呼'}
            if outage:
                def broken(q): raise provider_module.MemoryUnavailable('MEMORY_UNAVAILABLE')
                self.provider.client.recall_snapshot=broken; self.provider.client.recall=broken
            context=await self.provider.query_pet_memory('你知道我的称呼吗？','two')
            rendered=json.dumps(self.conn.dialogue.get_llm_dialogue_with_memory(context),ensure_ascii=False)
            self.assertNotIn('旧称呼',rendered)

    async def test_unchanged_revision_preserves_conversation(self):
        previous=Message('assistant','刚才说到天文学'); self.conn.dialogue.put(previous)
        self.new_turn('继续说')
        await self.provider.query_pet_memory('继续说','two')
        self.assertIn(previous,self.conn.dialogue.dialogue)

    async def test_late_old_query_never_clears_the_new_turn(self):
        def late(query):
            self.conn.sentence_id='three'
            self.conn.dialogue.put(Message('user','较新的问题'))
            return {'profile':{'revision':2},'context':'私有新称呼'}
        self.provider.client.recall_snapshot=late
        self.new_turn('旧问题')
        context=await self.provider.query_pet_memory('旧问题','two')
        self.assertNotIn('私有新称呼',context)
        self.assertEqual(self.conn.dialogue.dialogue[-1].content,'较新的问题')

    async def test_shared_server_prototype_produces_independent_connections(self):
        first=self.provider.for_connection(self.conn)
        other=SimpleNamespace()
        second=self.provider.for_connection(other)
        self.assertIs(first,self.provider)
        self.assertIsNot(first,second)
        self.assertEqual(second.handled,{})
        self.assertIsNone(second.connection)


if __name__=='__main__': unittest.main()
