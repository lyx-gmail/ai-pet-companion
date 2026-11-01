"""One official-model query, exposing only a fresh USB read of the owned pet."""
import asyncio
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time
import sys
from contextlib import AsyncExitStack
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
PRIVATE=ROOT/'.runtime/official-ai'


def mentions_satiety(text,number):
    if type(number) is not int or not 0<=number<=100:return False
    digits='零一二三四五六七八九'
    if number==100:spoken='一百'
    elif number<10:spoken=digits[number]
    else:spoken=(digits[number//10] if number>=20 else '')+'十'+(digits[number%10] if number%10 else '')
    return bool(re.search(r'饱食度\s*(?:是|为|：|:)?\s*(?:百分之)?(?:'+str(number)+'|'+spoken+r')(?![\d零一二三四五六七八九十百])',text))


class ReadOnlyTools:
    def __init__(self,read):
        self.read=read
        self.listed=False
        self.states=[]

    async def handle(self,request):
        if not isinstance(request,dict) or 'id' not in request: return None
        response={'jsonrpc':'2.0','id':request['id']}
        method=request.get('method');params=request.get('params',{})
        if method=='initialize':
            response['result']={'protocolVersion':'2024-11-05','capabilities':{'tools':{}},
                'serverInfo':{'name':'owned-pet-readonly-compatibility-probe','version':'1'}}
        elif method=='tools/list':
            self.listed=True
            response['result']={'tools':[{'name':'self.pet.get_state',
                'description':'Read this real pet device state. You MUST call this before answering satiety questions; do not invent values. Read only, no care action.',
                'inputSchema':{'type':'object','properties':{},'required':[],'additionalProperties':False}}]}
        elif method=='tools/call' and isinstance(params,dict) and params.get('name')=='self.pet.get_state' and params.get('arguments',{})=={}:
            try:
                state=await self.read()
                if state.get('ok') is not True: raise RuntimeError('DEVICE_UNAVAILABLE')
                self.states.append(state)
                response['result']={'content':[{'type':'text','text':json.dumps(state,ensure_ascii=False)}],'isError':False}
            except Exception:
                response['error']={'code':-32603,'message':'DEVICE_READ_UNAVAILABLE'}
        else:
            response['error']={'code':-32601,'message':'READ_ONLY_TOOL_REQUIRED'}
        return response


class FixtureConsentTools(ReadOnlyTools):
    """Software consent fixture ONLY; never described as a physical key test."""
    def __init__(self,read,decision):
        super().__init__(read)
        if decision not in ('confirmed','cancelled'):raise ValueError('FIXTURE_DECISION_INVALID')
        self.decision=decision;self.offers=0;self.status_reads=0;self.draft=None

    async def handle(self,request):
        if not isinstance(request,dict):return None
        params=request.get('params',{})
        name=params.get('name') if isinstance(params,dict) else None
        if request.get('method')!='tools/call' or name not in ('self.pet.memory_offer','self.pet.memory_status'):
            return await super().handle(request)
        response={'jsonrpc':'2.0','id':request.get('id')};args=params.get('arguments',{})
        try:
            token=args.get('id')
            if not isinstance(token,str) or not re.fullmatch(r'[0-9a-f-]{36}',token):raise ValueError()
            if name=='self.pet.memory_offer':
                if set(args)!={'id','label'} or not isinstance(args['label'],str) or not 1<=len(args['label'].encode('utf-8'))<=100:raise ValueError()
                self.draft=token;self.offers+=1;status='pending'
            else:
                if set(args)!={'id'} or token!=self.draft:raise ValueError()
                self.status_reads+=1;status=self.decision
            response['result']={'content':[{'type':'text','text':json.dumps({'ok':True,'id':token,'status':status})}],'isError':False}
        except (ValueError,TypeError,AttributeError):
            response['error']={'code':-32602,'message':'SOFTWARE_FIXTURE_DRAFT_REQUIRED'}
        return response


async def read_device():
    def invoke():
        process=subprocess.run([str(ROOT/'.tools/espressif/python_env/idf5.5_py3.12_env/Scripts/python.exe'),
            str(ROOT/'scripts/device_command.py'),'state','--seconds','3'],cwd=ROOT,
            capture_output=True,timeout=12,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if process.returncode: raise RuntimeError('DEVICE_READ_FAILED')
        value=json.loads(process.stdout)
        if value.get('ok') is not True or not isinstance(value.get('state'),dict):
            raise RuntimeError('DEVICE_STATE_INVALID')
        return value['state']
    return await asyncio.to_thread(invoke)


async def prepare_audio(question='state'):
    import edge_tts
    native=ROOT/'.tools/voice-native/bin'
    target=PRIVATE/('synthetic-'+question+'-question.mp3')
    phrase={'state':'请查一下宠物工具，告诉我现在的真实饱食度是多少。',
        'name':'你记得我叫什么吗？请先查宠物状态和已确认资料，不要猜。',
        'remember':'请记住，以后叫我小明。你需要调用记忆工具，并等我按键确认。'}[question]
    await edge_tts.Communicate(phrase,
        voice='zh-CN-XiaoxiaoNeural').save(str(target))
    def encode():
        os.environ['PATH']=str(native)+os.pathsep+os.environ['PATH']
        with os.add_dll_directory(str(native)):
            import opuslib_next
            pcm=subprocess.run([str(native/'ffmpeg.exe'),'-hide_banner','-loglevel','error',
                '-i',str(target),'-f','s16le','-ac','1','-ar','16000','pipe:1'],
                check=True,capture_output=True,timeout=15,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)).stdout
            if not 32000<=len(pcm)<=32000*15: raise RuntimeError('SYNTHETIC_AUDIO_LENGTH_INVALID')
            encoder=opuslib_next.Encoder(16000,1,opuslib_next.APPLICATION_VOIP)
            decoder=opuslib_next.Decoder(16000,1)
            encoder.bitrate=16000
            packets=[encoder.encode(pcm[i:i+1920].ljust(1920,b'\0'),960) for i in range(0,len(pcm),1920)]
            if not packets or not all(len(decoder.decode(packet,960))==1920 for packet in packets):
                raise RuntimeError('SYNTHETIC_OPUS_INVALID')
            return packets
    return await asyncio.to_thread(encode)


async def exercise(audio=False,bridge=False,question='state',fixture_memory_endpoint=None,expected_fixture_name=None,forbidden_fixture_names=(),fixture_consent=None):
    import websockets
    discovery=json.loads((PRIVATE/'discovery.json').read_text())
    ws=discovery['websocket'];endpoint=urlsplit(ws['url'])
    if endpoint.scheme!='wss' or endpoint.hostname!='api.tenclass.net' or endpoint.username or endpoint.password:
        raise ValueError('OFFICIAL_TLS_ENDPOINT_REQUIRED')
    config=json.loads((ROOT/'.tools/upstream/xiaozhi-esp32-server/main/xiaozhi-server/data/.config.yaml').read_text(encoding='utf-8'))
    device=config['Memory']['PetMemory']['expected_device_id']
    identity=json.loads((PRIVATE/'device-identity.json').read_text())['uuid']
    bearer=ws['token']
    if not isinstance(bearer,str) or not bearer or '\r' in bearer or '\n' in bearer: raise ValueError('TOKEN_INVALID')
    headers={'Device-Id':device,'Client-Id':identity,'Protocol-Version':'1',
        'Authorization':bearer if ' ' in bearer else 'Bearer '+bearer}
    tools=ReadOnlyTools(read_device)
    if fixture_consent is not None:
        if not bridge or fixture_memory_endpoint!='http://127.0.0.1:8767' or question!='remember':
            raise ValueError('ISOLATED_CONSENT_FIXTURE_REQUIRED')
        tools=FixtureConsentTools(read_device,fixture_consent)
    frames=[]
    result={'ok':False,'source':'official_AI_PC_protocol_session_with_fresh_physical_USB_tool',
        'physical_device_backend_changed':False,'device_write_commands_sent':False,
        'hardware_ASR_verified':False,'acoustic_playback_verified':False,
        'hello_received':False,'tools_discovered':False,'query_sent':False,'tool_called':False,
        'input_mode':'synthetic_opus' if audio else 'diagnostic_detect_text',
        'synthetic_audio_frames_sent':0}
    trace=[];session='';sent=False;texts=[];binary_count=0;stopped=False
    try:
        if audio: frames=await prepare_audio(question)
        async with AsyncExitStack() as stack:
            if bridge:
                from copy import deepcopy
                from unittest.mock import patch
                native=ROOT/'.tools/voice-native/bin'
                os.environ['PATH']=str(native)+os.pathsep+os.environ['PATH']
                stack.enter_context(os.add_dll_directory(str(native)))
                source=ROOT/'.tools/upstream/xiaozhi-esp32-server/main/xiaozhi-server'
                sys.path.insert(0,str(source))
                import importlib
                # Upstream's first logger import calls asyncio.run(load_config).
                # Bootstrap it in a worker, outside this probe's running loop.
                server_module=await asyncio.to_thread(importlib.import_module,'core.websocket_server')
                WebSocketServer=server_module.WebSocketServer
                from core.auth import AuthManager
                probe_config=deepcopy(config)
                if fixture_memory_endpoint is not None:
                    if fixture_memory_endpoint!='http://127.0.0.1:8767':raise ValueError('ISOLATED_MEMORY_FIXTURE_REQUIRED')
                    probe_config['Memory']['PetMemory']['endpoint']=fixture_memory_endpoint
                    result['isolated_memory_fixture_used']=True
                mode=PRIVATE/'probe-backend.json'
                mode.write_text('{"mode":"official"}\n',encoding='utf-8')
                probe_config['pet_official']['mode_file']=str(mode)
                # Actual routing/auth code, isolated loopback listener; no need to
                # initialize the unused local speech/model providers in this probe.
                with patch('core.websocket_server.initialize_modules',return_value={}):
                    server=WebSocketServer(probe_config)
                listener=await stack.enter_async_context(websockets.serve(server._handle_connection,'127.0.0.1',0))
                ws={'url':'ws://127.0.0.1:'+str(listener.sockets[0].getsockname()[1])}
                headers=dict(headers,Authorization='Bearer '+AuthManager(config['server']['auth_key']).generate_token(identity,device))
                result.update(source='official_AI_via_existing_authenticated_router_isolated_PC_listener_and_fresh_USB_tool',
                    live_backend_mode_changed=False,local_binding_and_authentication_used=True)
            class DirectConnect(websockets.connect):
                def process_redirect(self,error):return error
            socket=await stack.enter_async_context(DirectConnect(ws['url'],additional_headers=headers,open_timeout=15,
                close_timeout=3,max_size=65536))
            await socket.send(json.dumps({'type':'hello','version':1,'transport':'websocket',
                'features':{'mcp':True},'audio_params':{'format':'opus','sample_rate':16000,'channels':1,'frame_duration':60}}))
            deadline=time.monotonic()+50
            while time.monotonic()<deadline:
                try: raw=await asyncio.wait_for(socket.recv(),min(5,max(.1,deadline-time.monotonic())))
                except asyncio.TimeoutError: continue
                if isinstance(raw,bytes): binary_count+=1;continue
                value=json.loads(raw)
                if not isinstance(value,dict): continue
                trace.append(value)
                if value.get('type')=='hello':
                    result['hello_received']=True;session=value.get('session_id','')
                elif value.get('type')=='mcp':
                    reply=await tools.handle(value.get('payload'))
                    if reply is not None:
                        await socket.send(json.dumps({'session_id':session,'type':'mcp','payload':reply}))
                elif value.get('type')=='tts':
                    if isinstance(value.get('text'),str): texts.append(value['text'])
                    if value.get('state')=='stop': stopped=True
                elif value.get('type')=='stt' and bridge:
                    result['adapter_audio_provenance_received']=value.get('pet_audio') is True and type(value.get('pet_turn')) is int and value['pet_turn']>0
                elif value.get('type')=='alert':
                    result['server_alert_received']=True
                    if value.get('message')=='Detect is only for wake words, do not send long texts.':
                        result['detect_long_text_rejected']=True
                    break
                if result['hello_received'] and tools.listed and not sent:
                    if audio:
                        await socket.send(json.dumps({'session_id':session,'type':'listen','state':'start','mode':'manual'}))
                        for packet in frames:
                            await socket.send(packet)
                            result['synthetic_audio_frames_sent']+=1
                            await asyncio.sleep(.06)
                        await socket.send(json.dumps({'session_id':session,'type':'listen','state':'stop'}))
                    else:
                        await socket.send(json.dumps({'session_id':session,'type':'listen','state':'detect',
                            'text':'请调用宠物状态工具，告诉我现在的真实饱食度，只说这个数值。'},ensure_ascii=False))
                    sent=True;result['query_sent']=True
                if sent and stopped: break
            if session:
                await socket.send(json.dumps({'type':'abort','session_id':session}))
    except Exception as error:
        result['error_type']=type(error).__name__
        import traceback
        (PRIVATE/'last-probe-error.json').write_text(json.dumps({
            'type':type(error).__name__,'message':str(error),
            'frames':[{'file':Path(frame.filename).name,'line':frame.lineno,'function':frame.name}
                for frame in traceback.extract_tb(error.__traceback__)]},ensure_ascii=False),encoding='utf-8')
    PRIVATE.mkdir(parents=True,exist_ok=True)
    name={'name':'proxy-read-name','remember':'proxy-remember'}.get(question,'proxy-read-state') if bridge else 'read-state'
    (PRIVATE/(name+'-session.json')).write_text(json.dumps(trace,ensure_ascii=False)+'\n',encoding='utf-8')
    reply_text=''.join(texts)
    matching=bool(tools.states and mentions_satiety(reply_text,tools.states[-1].get('satiety')))
    result.update(tools_discovered=tools.listed,tool_called=bool(tools.states),
        actual_device_states_read=len(tools.states),reply_text_received=bool(texts),
        reply_ended=stopped,audio_packets_received=binary_count,reply_mentions_actual_satiety=matching)
    if tools.states:
        result['tool_result_snapshot']=tools.states[-1]
        result['last_verified_firmware_sha256']=json.loads(
            (ROOT/'evaluation/device-flash.json').read_text(encoding='utf-8'))['app_sha256']
    result['ok']=result['hello_received'] and tools.listed and bool(tools.states) and matching and stopped
    if question=='name':
        matched=(expected_fixture_name in reply_text if isinstance(expected_fixture_name,str) else
            bool(re.search(r'不确定|不知道|没有|没记|还没|未记|未存',reply_text)))
        result['reply_mentions_expected_fixture_name']=matched
        omitted=all(name not in reply_text for name in forbidden_fixture_names)
        result['reply_omits_old_fixture_names']=omitted
        result['ok']=result['hello_received'] and tools.listed and bool(tools.states) and matched and omitted and stopped
    if question=='remember':
        result.update(software_consent_fixture=True,physical_memory_confirmation_verified=False,
            fixture_memory_offer_count=tools.offers,fixture_memory_status_count=tools.status_reads)
        result['ok']=result['hello_received'] and tools.listed and bool(tools.states) and tools.offers>0 and tools.status_reads>0 and stopped
    if bridge:result['ok']=result['ok'] and result.get('adapter_audio_provenance_received',False)
    (ROOT/('evaluation/official-ai-'+name+'-check.json')).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))
    return 0 if result['ok'] else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audio',action='store_true',help='Use the standard Opus speech-input path.')
    parser.add_argument('--bridge',action='store_true',help='Use an isolated copy of the authenticated local router; retain live backend mode.')
    args=parser.parse_args()
    raise SystemExit(asyncio.run(exercise(args.audio,args.bridge)))
