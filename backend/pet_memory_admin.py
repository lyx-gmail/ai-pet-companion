"""Device-bound HTTP bridge; credentials stay on the PC and no LLM is involved."""
import asyncio
import json
import re
from aiohttp import web
from core.auth import AuthManager
from core.pet_network import device_allowed
from core.providers.memory.mem_pet.client import PetMemoryClient, MemoryUnavailable


class PetMemoryHandler:
    def __init__(self,config):
        self.config=config
        auth=config['server']
        self.auth=AuthManager(auth['auth_key'],auth.get('auth',{}).get('expire_seconds'))
        memory=config['Memory']['PetMemory']
        self.memory=PetMemoryClient(memory['endpoint'],memory['token'],memory.get('timeout',3))

    async def handle(self,request):
        def reply(status,value):
            return web.json_response(value,status=status,headers={
                'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})
        if not device_allowed(request.headers,self.config):
            return reply(403,{'error':'DEVICE_NOT_BOUND'})
        bearer=request.headers.get('Authorization','')
        if not bearer.startswith('Bearer ') or not self.auth.verify_token(
                bearer[7:],request.headers['Client-ID'],request.headers['Device-ID']):
            return reply(401,{'error':'UNAUTHORIZED'})
        if request.content_type!='application/json':
            return reply(415,{'error':'JSON_REQUIRED'})
        try:
            if request.content_length is not None and request.content_length>1024:
                return reply(413,{'error':'BODY_TOO_LARGE'})
            raw=await request.read()
            if len(raw)>1024: return reply(413,{'error':'BODY_TOO_LARGE'})
            body=json.loads(raw)
            if not isinstance(body,dict): raise ValueError()
            action=body.get('action')
            if action=='profile' and set(body)=={'action'}:
                result=await asyncio.to_thread(self.memory.profile)
            elif action=='delete' and set(body)=={'action','field','revision'}:
                field=body['field']; revision=body['revision']
                if (field not in ('name','preference0','preference1','preference2','preference3','all')
                        or type(revision) is not int or not 0<=revision<=9007199254740991):
                    raise ValueError()
                result=await asyncio.to_thread(self.memory.request,'propose',{
                    'kind':'profile','op':'delete_all' if field=='all' else 'delete',
                    'field':None if field=='all' else field,'expectedRevision':revision})
            elif action in ('confirm','cancel') and set(body)=={'action','id'}:
                identity=body['id']
                if not isinstance(identity,str) or not re.fullmatch(
                        r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',identity):
                    raise ValueError()
                data={'id':identity}
                if action=='confirm': data['requestId']='device-delete-'+identity
                result=await asyncio.to_thread(self.memory.request,action,data)
            else:
                raise ValueError()
            return reply(200,result)
        except (ValueError,UnicodeError):
            return reply(400,{'error':'REQUEST_INVALID'})
        except MemoryUnavailable as error:
            code=str(error)
            if code in ('CONFLICT','BUSY','EXPIRED','NOT_FOUND'):
                return reply(409,{'error':code})
            return reply(503,{'error':'MEMORY_UNAVAILABLE'})
