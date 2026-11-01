"""Explicit official-AI bridge behind the existing authenticated device socket."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import re
import struct
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

CARE=frozenset(('self.pet.feed','self.pet.pet','self.pet.set_sleep'))
TOOLS=CARE|{'self.pet.get_state','self.pet.remember'}


def backend_mode(value):
    if value=={}:return 'local'
    if (not isinstance(value,dict) or set(value)!={'mode'} or
            value['mode'] not in ('local','official')):
        raise ValueError('BACKEND_MODE_INVALID')
    return value['mode']


def official_endpoint(value):
    if not isinstance(value,dict):raise ValueError('OFFICIAL_ENDPOINT_REQUIRED')
    url=value.get('url','');token=value.get('token','')
    parsed=urlsplit(url)
    if (parsed.scheme!='wss' or parsed.hostname!='api.tenclass.net' or
            parsed.port not in (None,443) or parsed.username or parsed.password or
            parsed.fragment or not isinstance(token,str) or not 1<=len(token)<=8192 or
            any(c in token for c in ('\r','\n'))):
        raise ValueError('OFFICIAL_TLS_ENDPOINT_REQUIRED')
    return url,token if ' ' in token else 'Bearer '+token


class PetSession:
    def __init__(self,version):
        if version not in (1,2,3):raise ValueError('PROTOCOL_VERSION_INVALID')
        self.version=version
        self.turn=0;self.listening=False;self.audio=False;self.active=False;self.cancelled=False
        self.transcript=''
        self.calls={};self.actions={}

    def device(self,message):
        if self.cancelled:raise ValueError('TURN_CANCELLED')
        if isinstance(message,bytes):
            size=len(message)
            if self.version==2:
                if size<=16 or struct.unpack('!H',message[:2])[0]!=2 or struct.unpack('!I',message[12:16])[0]!=size-16:
                    raise ValueError('AUDIO_FRAME_INVALID')
            elif self.version==3:
                if size<=4 or struct.unpack('!H',message[2:4])[0]!=size-4:
                    raise ValueError('AUDIO_FRAME_INVALID')
            elif not size:raise ValueError('AUDIO_FRAME_INVALID')
            if self.listening:self.audio=True
            return message
        message=deepcopy(message)
        if message.get('type')=='abort':
            self.cancelled=True;self.active=False
            raise ValueError('TURN_CANCELLED')
        if message.get('type')=='listen':
            state=message.get('state')
            if state=='start':
                if self.active or self.listening:raise ValueError('OVERLAPPING_TURN')
                self.turn+=1
                if self.turn>0x7fffffff:raise ValueError('TURN_CAPACITY')
                self.listening=True;self.audio=False
            elif state=='stop':self.listening=False
            elif state=='detect':
                # Wake words are not an ASR turn and cannot authorize care.
                self.audio=False
        payload=message.get('payload')
        if message.get('type')=='mcp' and isinstance(payload,dict):
            result=payload.get('result')
            if isinstance(result,dict) and isinstance(result.get('tools'),list):
                result['tools']=[tool for tool in result['tools']
                    if isinstance(tool,dict) and tool.get('name') in TOOLS-{'self.pet.remember'}]
        return message

    def cloud(self,message):
        if self.cancelled:raise ValueError('TURN_CANCELLED')
        message=deepcopy(message)
        if message.get('type')=='stt':
            # Consume actual forwarded input once. Server/model-supplied provenance
            # is always replaced, including on text/wake-word diagnostic paths.
            valid=self.audio and self.turn>0 and isinstance(message.get('text'),str) and bool(message['text'].strip())
            self.audio=False;self.active=bool(valid);self.listening=False
            self.transcript=message['text'] if valid else ''
            message.update(pet_audio=bool(valid),pet_turn=self.turn if valid else 0)
        if message.get('type')=='tts' and message.get('state')=='stop':self.active=False
        payload=message.get('payload')
        if message.get('type')!='mcp' or not isinstance(payload,dict) or payload.get('method')!='tools/call':
            return message
        params=payload.get('params',{});number=payload.get('id')
        if not isinstance(params,dict):raise ValueError('TOOL_ARGUMENTS_INVALID')
        name=params.get('name');args=params.get('arguments',{})
        if name not in TOOLS:raise ValueError('PET_TOOL_NOT_AVAILABLE')
        if type(number) is not int or not 0<=number<0x70000000:raise ValueError('CLOUD_RPC_ID_INVALID')
        if not isinstance(args,dict):raise ValueError('TOOL_ARGUMENTS_INVALID')
        if name=='self.pet.set_sleep':
            if set(args)!={'sleeping'} or type(args['sleeping']) is not bool:raise ValueError('TOOL_ARGUMENTS_INVALID')
        elif args:raise ValueError('TOOL_ARGUMENTS_INVALID')
        # No metadata supplied by the model/cloud may impersonate this adapter.
        params.pop('_meta',None)
        if name in CARE and not self.active:
            raise ValueError('ACTIVE_AUDIO_TURN_REQUIRED')
        action=(self.turn,name,args.get('sleeping'))
        if number in self.calls and self.calls[number]!=action:raise ValueError('CALL_ID_REUSED')
        if number not in self.calls and len(self.calls)>=512:raise ValueError('CALL_CAPACITY')
        self.calls[number]=action
        if name not in CARE:return message
        if action not in self.actions:
            if len(self.actions)>=256:raise ValueError('ACTION_CAPACITY')
            self.actions[action]=len(self.actions)+1
        params['_meta']={'pet_request_id':self.actions[action]}
        return message


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def discover(device,client):
    body={'version':2,'language':'zh-CN','flash_size':16777216,'mac_address':device,'uuid':client,
        'chip_model_name':'esp32s3','application':{'name':'xiaozhi','version':'2.0.4'},
        'board':{'type':'xingzhi-cube-1.54tft-wifi'}}
    request=Request('https://api.tenclass.net/xiaozhi/ota/',data=json.dumps(body).encode(),
        headers={'Content-Type':'application/json','Device-Id':device,'Client-Id':client,'Activation-Version':'1'},method='POST')
    with build_opener(ProxyHandler({}),NoRedirect()).open(request,timeout=8) as response:
        raw=response.read(65537)
    if len(raw)>65536:raise ValueError('DISCOVERY_RESPONSE_TOO_LARGE')
    data=json.loads(raw)
    activation=data.get('activation',{})
    if activation and (activation.get('code') or activation.get('challenge')):raise ValueError('OFFICIAL_BINDING_REQUIRED')
    return official_endpoint(data.get('websocket'))


async def relay(device_socket,url,headers,version,memory=None):
    import websockets
    class DirectConnect(websockets.connect):
        def process_redirect(self,error):return error
    session=PetSession(version)
    async with DirectConnect(url,additional_headers=headers,open_timeout=10,close_timeout=2,
            max_size=65536,max_queue=16) as cloud_socket:
        if memory:memory.bind(device_socket.send,cloud_socket.send,session)
        async def forward(source,target,from_device):
            async for raw in source:
                if isinstance(raw,bytes):
                    outgoing=session.device(raw) if from_device else raw
                    if not from_device and memory:memory.allow_audio(session)
                else:
                    if len(raw)>65536:raise ValueError('MESSAGE_TOO_LARGE')
                    value=json.loads(raw)
                    if not isinstance(value,dict):raise ValueError('MESSAGE_INVALID')
                    try:
                        outgoing=session.device(value) if from_device else session.cloud(value)
                        if memory:
                            outgoing=await memory.device(outgoing,session) if from_device else await memory.cloud(outgoing,session)
                    except ValueError:
                        payload=value.get('payload',{})
                        if (not from_device and isinstance(payload,dict) and
                                payload.get('method')=='tools/call' and 'id' in payload):
                            await cloud_socket.send(json.dumps({'type':'mcp','session_id':value.get('session_id',''),
                                'payload':{'jsonrpc':'2.0','id':payload['id'],
                                    'error':{'code':-32602,'message':'PET_TOOL_REJECTED'}}}))
                            continue
                        raise
                    if outgoing is None:continue
                    outgoing=json.dumps(outgoing,ensure_ascii=False)
                    if len(outgoing.encode('utf-8'))>65536:raise ValueError('MESSAGE_TOO_LARGE')
                await target.send(outgoing)
        tasks=[asyncio.create_task(forward(device_socket,cloud_socket,True)),
            asyncio.create_task(forward(cloud_socket,device_socket,False))]
        if memory:tasks.append(asyncio.create_task(memory.watch(session)))
        try:
            done,_=await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
            for task in done:task.result()
        finally:
            session.cancelled=True
            if memory:memory.close()
            for task in tasks:task.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)


async def proxy_if_selected(socket,config):
    """Called only AFTER local device binding and HMAC authentication succeed."""
    settings=config.get('pet_official',{})
    path=settings.get('mode_file')
    if not path:return False
    try:
        mode_path=Path(path)
        raw=mode_path.read_bytes() if mode_path.exists() else b'{}'
        if len(raw)>1024:raise ValueError('BACKEND_MODE_INVALID')
        if backend_mode(json.loads(raw))=='local':return False
        headers={key.lower():value for key,value in socket.request.headers.items()}
        device=headers.get('device-id','');client=headers.get('client-id','')
        expected=config.get('Memory',{}).get('PetMemory',{}).get('expected_device_id','')
        identity=json.loads(Path(settings['identity_file']).read_text(encoding='utf-8'))
        if (not re.fullmatch(r'(?:[0-9a-f]{2}:){5}[0-9a-f]{2}',device) or device!=expected or
                client!=identity.get('uuid') or not re.fullmatch(r'[0-9a-f-]{36}',client)):
            raise ValueError('OWNED_DEVICE_REQUIRED')
        version=int(headers.get('protocol-version','1'))
        PetSession(version)
        url,bearer=await asyncio.to_thread(discover,device,client)
        from core.pet_official_memory import MemoryGate
        from core.providers.memory.mem_pet.client import PetMemoryClient
        memory_config=config['Memory']['PetMemory']
        memory=MemoryGate(PetMemoryClient(memory_config['endpoint'],memory_config['token'],memory_config.get('timeout',3)))
        await relay(socket,url,{'Device-Id':device,'Client-Id':client,
            'Protocol-Version':str(version),'Authorization':bearer},version,memory)
    except Exception:
        # Never expose cloud URLs, credentials, transcripts, or private exceptions.
        try:await socket.send(json.dumps({'type':'alert','status':'error',
            'message':'官方语音暂不可用，请重试或切回本地。','emotion':'sad'},ensure_ascii=False))
        except Exception:pass
    await socket.close()
    return True
