import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

spec = importlib.util.spec_from_file_location('pet_identity',Path(__file__).with_name('pet_identity.py'))
identity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(identity)


class IdentityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.conn = SimpleNamespace(sentence_id='turn-1',client_abort=False)
        self.client = SimpleNamespace()

    @identity.bind_pet_call
    async def invoke(self,conn,data):
        return await identity.care_request_id(conn,self.client,data.get('name','self.pet.feed'),data.get('arguments'))

    async def test_sleep_target_identity_and_validation(self):
        data = {'id':'sleep-A','_pet_sentence_id':'turn-1','name':'self.pet.set_sleep','arguments':{'sleeping':True}}
        self.assertEqual(await self.invoke(self.conn,data),1)
        self.assertEqual(await self.invoke(self.conn,dict(data,id='sleep-B')),1)
        self.assertEqual(await self.invoke(self.conn,dict(data,id='wake-A',arguments={'sleeping':False})),2)
        for arguments in ({},{'sleeping':'true'},{'sleeping':1}):
            with self.assertRaises(ValueError):
                await self.invoke(self.conn,dict(data,id='invalid',arguments=arguments))
        with self.assertRaises(ValueError):
            await self.invoke(self.conn,dict(data,arguments={'sleeping':False}))

    async def test_retry_and_concurrent_duplicates(self):
        data = {'id':'call-A','_pet_sentence_id':'turn-1'}
        self.assertEqual(await asyncio.gather(self.invoke(self.conn,data),self.invoke(self.conn,data)),[1,1])
        self.assertEqual(await self.invoke(self.conn,dict(data,id='call-B')),1)
        self.assertEqual(await self.invoke(self.conn,dict(data,id='call-C',name='self.pet.pet')),2)
        with self.assertRaises(ValueError):
            await self.invoke(self.conn,dict(data,name='self.pet.pet'))

    async def test_fail_closed_and_context_reset(self):
        with self.assertRaises(ValueError):
            await identity.care_request_id(self.conn,self.client,'self.pet.feed')
        for data in [{'id':'call-A'}, {'id':'','_pet_sentence_id':'turn-1'},
                     {'id':'call-A','_pet_sentence_id':'old-turn'}]:
            with self.assertRaises(ValueError):
                await self.invoke(self.conn,data)
        self.conn.client_abort = True
        with self.assertRaises(ValueError):
            await self.invoke(self.conn,{'id':'call-A','_pet_sentence_id':'turn-1'})
        self.assertIsNone(await identity.care_request_id(self.conn,self.client,'self.pet.get_state'))

    async def test_capacity_does_not_evict_old_identity(self):
        for index in range(256):
            self.conn.sentence_id = f'turn-{index}'
            self.assertEqual(await self.invoke(self.conn,{'id':str(index),'_pet_sentence_id':self.conn.sentence_id}),index+1)
        with self.assertRaises(ValueError):
            self.conn.sentence_id = 'overflow-turn'
            await self.invoke(self.conn,{'id':'overflow','_pet_sentence_id':self.conn.sentence_id})
        self.conn.sentence_id = 'turn-0'
        self.assertEqual(await self.invoke(self.conn,{'id':'0','_pet_sentence_id':'turn-0'}),1)
        self.assertFalse(identity._current_call.get())


if __name__=='__main__':
    unittest.main()
