import unittest
from unittest.mock import AsyncMock
from official_ai_probe import ReadOnlyTools, mentions_satiety, FixtureConsentTools


class ProbeChecks(unittest.IsolatedAsyncioTestCase):
    async def test_fixture_consent_requires_matching_adapter_draft(self):
        tools=FixtureConsentTools(AsyncMock(),'confirmed')
        async def call(name,args):
            return await tools.handle({'id':12,'method':'tools/call','params':{'name':name,'arguments':args}})
        token='11111111-1111-4111-8111-111111111111'
        self.assertIn('error',await call('self.pet.memory_status',{'id':token}))
        offer=await call('self.pet.memory_offer',{'id':token,'label':'称呼：小明'})
        self.assertIn('pending',str(offer))
        self.assertIn('confirmed',str(await call('self.pet.memory_status',{'id':token})))
        self.assertIn('error',await call('self.pet.memory_status',{'id':token,'confirm':True}))
    def test_spoken_numbers_match_only_the_satiety_field(self):
        self.assertTrue(mentions_satiety('有的是饱食度九十五、心情八十七。',95))
        self.assertTrue(mentions_satiety('饱食度是95。',95))
        for text in ('心情95，饱食度80。','饱食度950。','饱食度九十五。'):
            self.assertFalse(mentions_satiety(text,9))
        self.assertFalse(mentions_satiety('心情95，饱食度80。',95))
    async def test_unlisted_tool_and_extra_arguments_never_touch_device(self):
        read=AsyncMock(return_value={'ok':True,'satiety':51})
        tools=ReadOnlyTools(read)
        for params in ({'name':'self.pet.feed','arguments':{}},
                       {'name':'self.pet.get_state','arguments':{'command':'feed'}}):
            response=await tools.handle({'jsonrpc':'2.0','id':1,'method':'tools/call','params':params})
            self.assertIn('error',response)
        read.assert_not_called()

    async def test_read_is_fresh_and_device_failure_not_invented(self):
        read=AsyncMock(side_effect=[{'ok':True,'satiety':51},RuntimeError('private error')])
        tools=ReadOnlyTools(read)
        request={'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'self.pet.get_state','arguments':{}}}
        response=await tools.handle(request)
        self.assertIn('51',response['result']['content'][0]['text'])
        self.assertEqual(read.await_count,1)
        failed=await tools.handle(dict(request,id=3))
        self.assertIn('error',failed)
        self.assertNotIn('private',str(failed))


if __name__=='__main__':unittest.main()
