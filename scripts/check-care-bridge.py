"""Exercise actual upstream tool handler/executor/MCP code with a software device.

No model API, hardware, or network is used. The software device only returns
receipt data; firmware mutations are covered separately by target assertions.
"""
import asyncio
import contextlib
from datetime import date
import io
import ipaddress
import json
import os
from pathlib import Path
import sys
import traceback
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


async def exercise():
    from core.providers.tools.unified_tool_handler import UnifiedToolHandler
    from core.providers.tools.unified_tool_manager import ToolManager
    from core.providers.tools.base import ToolType
    from core.providers.tools.device_mcp.mcp_client import MCPClient
    from core.providers.tools.device_mcp.mcp_executor import DeviceMCPExecutor
    from core.providers.tools.device_mcp.mcp_handler import handle_mcp_message
    from plugins_func.register import Action
    from config.logger import setup_logging

    client = MCPClient()
    conn = SimpleNamespace(sentence_id='software-turn-1',session_id='software-session',
                           client_abort=False,features={'mcp':True},mcp_client=client)
    sent = []

    class Socket:
        async def send(self,raw):
            message = json.loads(raw)
            if message.get('type')!='mcp':
                return
            payload = message['payload']
            sent.append(payload)
            receipt = {'software_receipt':True,'request':payload['params']['_meta']['pet_request_id']}
            await handle_mcp_message(conn,client,{'id':payload['id'],'result':{
                'content':[{'type':'text','text':json.dumps(receipt)}],'isError':False}})

    conn.websocket = Socket()
    for name in ('self.pet.feed','self.pet.pet','self.pet.set_sleep'):
        await client.add_tool({'name':name,'description':'software test',
                               'inputSchema':{'type':'object','properties':{'sleeping':{'type':'boolean'}} if name.endswith('set_sleep') else {},
                                              'required':['sleeping'] if name.endswith('set_sleep') else []}})
    await client.set_ready(True)
    handler = UnifiedToolHandler.__new__(UnifiedToolHandler)
    handler.conn = conn
    handler.logger = setup_logging()
    handler.tool_manager = ToolManager(conn)
    handler.tool_manager.register_executor(ToolType.DEVICE_MCP,DeviceMCPExecutor(conn))
    handler.tool_manager.refresh_tools()
    feed = next(name for name in client.tools if client.name_mapping[name]=='self.pet.feed')
    pet = next(name for name in client.tools if client.name_mapping[name]=='self.pet.pet')
    data = {'name':feed,'arguments':{'_pet_request_id':999,'_meta':{'pet_request_id':999}},
            'id':'provider-call-1','_pet_sentence_id':conn.sentence_id}
    a = await handler.handle_llm_function_call(conn,data)
    b = await handler.handle_llm_function_call(conn,data)
    c = await handler.handle_llm_function_call(conn,dict(data,id='provider-call-2'))
    if any(item.action!=Action.REQLLM for item in (a,b,c)):
        raise RuntimeError('Actual handler did not return device receipts')
    if len(sent)!=3 or len({message['id'] for message in sent})!=3:
        raise RuntimeError('JSON-RPC request IDs must remain distinct')
    if [message['params']['_meta']['pet_request_id'] for message in sent]!=[1,1,1]:
        raise RuntimeError('Logical retry identity changed or model overrode metadata')
    for bad in (dict(data,name=pet),dict(data,_pet_sentence_id='stale'),dict(data,id='')):
        response = await handler.handle_llm_function_call(conn,bad)
        if response.action not in (Action.ERROR,Action.NOTFOUND) or len(sent)!=3:
            raise RuntimeError('Invalid logical action reached the device')
    conn.client_abort = True
    response = await handler.handle_llm_function_call(conn,dict(data,id='provider-call-3'))
    if response.action not in (Action.ERROR,Action.NOTFOUND) or len(sent)!=3 or client.call_results:
        raise RuntimeError('Cancelled call reached device or leaked a pending future')
    conn.client_abort = False
    sleep_name = next(name for name in client.tools if client.name_mapping[name]=='self.pet.set_sleep')
    sleep_data = dict(data,name=sleep_name,id='sleep-1',arguments={'sleeping':True})
    for call in (sleep_data,dict(sleep_data,id='sleep-2'),dict(sleep_data,id='wake-1',arguments={'sleeping':False})):
        response = await handler.handle_llm_function_call(conn,call)
        if response.action!=Action.REQLLM:
            raise RuntimeError('Valid sleep target did not reach MCP')
    if [message['params']['_meta']['pet_request_id'] for message in sent[3:]]!=[2,2,3]:
        raise RuntimeError('Sleep target retry identities are incorrect')
    for arguments in ({},{'sleeping':1},{'sleeping':'true'}):
        response = await handler.handle_llm_function_call(conn,dict(sleep_data,id='bad-sleep',arguments=arguments))
        if response.action not in (Action.ERROR,Action.NOTFOUND) or len(sent)!=6 or client.call_results:
            raise RuntimeError('Invalid sleep target reached device or leaked a pending future')
    return {'actual_handler_executor_mcp':True,'distinct_rpc_ids':True,
            'stable_logical_retry_id':True,'same_turn_action_deduplicated':True,'model_metadata_override_rejected':True,
            'stale_cancelled_and_cross_action_calls_rejected':True,
            'sleep_target_retry_and_boolean_validation':True,'pending_futures':0}


def main():
    def audit(event,args):
        if event=='socket.connect':
            address = args[1]
            # Windows asyncio creates a loopback self-pipe during loop setup.
            try:
                if isinstance(address,tuple) and ipaddress.ip_address(address[0]).is_loopback:
                    return
            except ValueError:
                pass
            raise RuntimeError('Care bridge check forbids external network connections')
    sys.addaudithook(audit)
    binaries = ROOT/'.tools/voice-native/bin'
    source = ROOT/'.tools/upstream/xiaozhi-esp32-server/main/xiaozhi-server'
    os.environ['PATH'] = str(binaries)+os.pathsep+os.environ['PATH']
    os.chdir(source)
    sys.path.insert(0,str(source))
    result = {'date':date.today().isoformat(),'software_device':True,
              'hardware_actions_verified':False,'cloud_api_called':False}
    try:
        with os.add_dll_directory(str(binaries)),contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            import app  # initialize upstream config outside the running event loop
            result.update(asyncio.run(exercise()))
            from loguru import logger
            logger.remove()
        result['ok'] = True
    except Exception as error:
        result.update(ok=False,error_type=type(error).__name__)
        frame = traceback.extract_tb(error.__traceback__)[-1]
        result['error_location'] = f'{Path(frame.filename).name}:{frame.lineno}'
    (ROOT/'evaluation/care-bridge-check.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))
    return 0 if result['ok'] else 1


if __name__=='__main__':
    raise SystemExit(main())
