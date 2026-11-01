"""Authentication and strict operation boundaries for the device memory route."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'.tools/upstream/xiaozhi-esp32-server/main/xiaozhi-server')]
from pet_memory_admin import PetMemoryHandler
from core.auth import AuthManager
from core.providers.memory.mem_pet.client import MemoryUnavailable


class DeviceMemoryChecks(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.config={'server':{'auth_key':'fictional-secret','auth':{'enabled':True,'allowed_devices':[]}},
                     'Memory':{'PetMemory':{'expected_device_id':'02:00:00:00:00:01',
                         'endpoint':'http://127.0.0.1:8766','token':'fictional-memory-token'}}}
        self.mock=patch('pet_memory_admin.PetMemoryClient',autospec=True)
        self.memory=self.mock.start().return_value
        self.memory.profile.return_value={'revision':2,'name':'虚构伙伴','preferences':[]}
        self.memory.request.return_value={'id':'00000000-0000-4000-8000-000000000001','status':'PENDING'}
        handler=PetMemoryHandler(self.config)
        app=web.Application();app.router.add_post('/pet/memory',handler.handle)
        self.http=TestClient(TestServer(app));await self.http.start_server()
        self.headers={'Device-ID':'02:00:00:00:00:01','Client-ID':'fixture',
            'Authorization':'Bearer '+AuthManager('fictional-secret').generate_token('fixture','02:00:00:00:00:01')}

    async def asyncTearDown(self):
        await self.http.close();self.mock.stop()

    async def test_authentication_precedes_any_memory_read(self):
        for headers in ({},dict(self.headers,Authorization='Bearer invalid'),
                        dict(self.headers,**{'Device-ID':'02:00:00:00:00:02'})):
            response=await self.http.post('/pet/memory',json={'action':'profile'},headers=headers)
            self.assertIn(response.status,(401,403))
        self.memory.profile.assert_not_called();self.memory.request.assert_not_called()

    async def test_strict_fields_and_pending_delete_never_commits(self):
        for body in ({'action':'set','value':'x'}, {'action':'delete','field':'event/123','revision':2},
                     {'action':'delete','field':'name','revision':True},
                     {'action':'delete','field':'name','revision':2,'value':'x'}):
            response=await self.http.post('/pet/memory',json=body,headers=self.headers)
            self.assertEqual(response.status,400)
        self.memory.request.assert_not_called()
        response=await self.http.post('/pet/memory',json={'action':'delete','field':'name','revision':2},headers=self.headers)
        self.assertEqual(response.status,200)
        self.assertEqual((await response.json())['status'],'PENDING')
        self.memory.request.assert_called_once_with('propose',{'kind':'profile','op':'delete','field':'name','expectedRevision':2})

    async def test_profile_no_store_and_fixed_confirmation_identity(self):
        response=await self.http.post('/pet/memory',json={'action':'profile'},headers=self.headers)
        self.assertEqual((await response.json())['name'],'虚构伙伴')
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        identity='00000000-0000-4000-8000-000000000001'
        response=await self.http.post('/pet/memory',json={'action':'confirm','id':identity},headers=self.headers)
        self.assertEqual(response.status,200)
        self.memory.request.assert_called_once_with('confirm',{'id':identity,'requestId':'device-delete-'+identity})

    async def test_outage_and_invalid_body_never_claim_success(self):
        for raw in ('[]','{"action":"profile"','{"action":"profile","padding":"'+'x'*1100+'"}'):
            response=await self.http.post('/pet/memory',data=raw,
                headers=dict(self.headers,**{'Content-Type':'application/json'}))
            self.assertIn(response.status,(400,413))
        self.memory.profile.assert_not_called();self.memory.request.assert_not_called()
        self.memory.profile.side_effect=MemoryUnavailable('private failure details')
        response=await self.http.post('/pet/memory',json={'action':'profile'},headers=self.headers)
        self.assertEqual(response.status,503)
        self.assertEqual(await response.json(),{'error':'MEMORY_UNAVAILABLE'})
        self.memory.request.side_effect=MemoryUnavailable('CONFLICT')
        response=await self.http.post('/pet/memory',json={'action':'delete','field':'all','revision':2},headers=self.headers)
        self.assertEqual(response.status,409)
        self.assertEqual(await response.json(),{'error':'CONFLICT'})


if __name__=='__main__':unittest.main()
