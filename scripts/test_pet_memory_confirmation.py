import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

PATH=Path(__file__).resolve().parents[1]/'backend/xiaozhi_memory/mem_pet/confirmation.py'
spec=importlib.util.spec_from_file_location('pet_confirmation',PATH)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ConfirmationTests(unittest.IsolatedAsyncioTestCase):
    async def run_case(self, decisions, current=lambda: True):
        operations=[]
        token='b82c20fa-467a-4c7d-a9a5-7a5149323411'
        def request(path, body):
            operations.append(path)
            if path=='remember': return dict(status='PENDING',id=token,field='name',value='小林',expiresAt=9999999999999)
            if path=='confirm': return dict(ok=True,revision=2)
            return dict(cancelled=True)
        async def call(name, args):
            if name=='self_pet_memory_offer': return dict(ok=True,id=token,status='pending')
            choice=decisions.pop(0)
            return dict(ok=True,id=token if choice!='wrong_id' else 'other',status=choice)
        result=await module.confirm_memory('请记住我叫小林',request,call,current,poll_seconds=0,timeout=.05)
        return result,operations

    async def test_spoken_prompt_precedes_decision_and_commit(self):
        events=[]
        token='b82c20fa-467a-4c7d-a9a5-7a5149323411'
        def request(path,body):
            events.append(path)
            if path=='remember': return dict(status='PENDING',id=token,field='name',value='小林',expiresAt=9999999999999)
            return dict(ok=True)
        async def call(name,args):
            events.append(name)
            return dict(ok=True,id=token,status='pending' if name.endswith('offer') else 'confirmed')
        async def announce(text):
            self.assertIn('称呼：小林',text)
            self.assertIn('按中键保存，按左键取消',text)
            events.append('spoken_prompt')
        result=await module.confirm_memory('请记住我叫小林',request,call,lambda:True,announce=announce)
        self.assertIn('已按键确认',result)
        self.assertLess(events.index('self_pet_memory_offer'),events.index('spoken_prompt'))
        self.assertLess(events.index('spoken_prompt'),events.index('self_pet_memory_status'))
        self.assertEqual(events[-1],'confirm')

    async def test_only_matching_device_confirmation_commits(self):
        result,ops=await self.run_case(['pending','confirmed'])
        self.assertIn('已按键确认',result)
        self.assertEqual(ops,['remember','confirm'])

    async def test_cancel_unknown_id_and_stale_turn_never_commit(self):
        for choices,current in ((['cancelled'],lambda:True),(['wrong_id'],lambda:True),([],lambda:False)):
            result,ops=await self.run_case(choices,current)
            self.assertNotIn('confirm',ops)
            if 'remember' in ops: self.assertIn('cancel',ops)
            self.assertIn('未保存',result)

    async def test_mcp_error_cancels_draft(self):
        calls=[]
        def request(path,body):
            calls.append(path)
            return dict(status='PENDING',id='b82c20fa-467a-4c7d-a9a5-7a5149323411',field='name',value='小林',expiresAt=9999999999999)
        async def broken(*args): raise ConnectionError()
        result=await module.confirm_memory('叫我小林',request,broken,lambda:True,poll_seconds=0,timeout=.01)
        self.assertIn('未保存',result)
        self.assertEqual(calls,['remember','cancel'])

    async def test_commit_transport_failure_is_reported_as_unknown(self):
        token='b82c20fa-467a-4c7d-a9a5-7a5149323411'
        def request(path,body):
            if path=='remember': return dict(status='PENDING',id=token,field='name',value='小林',expiresAt=9999999999999)
            if path=='confirm': raise TimeoutError()
            return {}
        async def call(name,args):
            return dict(ok=True,id=token,status='pending' if name.endswith('offer') else 'confirmed')
        result=await module.confirm_memory('叫我小林',request,call,lambda:True)
        self.assertIn('结果未知',result)
        self.assertNotIn('未保存',result)

    def test_preference_and_save_wording_enter_real_confirmation(self):
        for text in ('我喜欢天文学','我现在喜欢天文学','好，那存进去，我现在喜欢天文学。','请保存我的偏好，我喜欢天文学'):
            with self.subTest(text=text): self.assertTrue(module.wants_memory(text))
        for text in ('我喜欢什么？','我现在喜欢什么','我喜欢天文学吗？','不要保存我喜欢天文学','别存我喜欢什么'):
            with self.subTest(text=text): self.assertFalse(module.wants_memory(text))

    def test_negative_and_plain_chat_do_not_propose(self):
        for text in ('你好','不要记住我的名字','不用记我说的','别记住这个','我叫什么？','我叫啥'):
            self.assertFalse(module.wants_memory(text))
        self.assertTrue(module.wants_memory('以后叫我小林'))


if __name__=='__main__': unittest.main()
