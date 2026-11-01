"""Pinned upstream bridge: carry provider call identity in MCP metadata."""
from pathlib import Path
import shutil


def apply(root,server,replace):
    tts=server/'core/providers/tts/base.py'
    text=tts.read_text(encoding='utf-8')
    if 'self.tts_timeout =' not in text:
        text=text.replace('        self.delete_audio_file = delete_audio_file',
                          '        self.tts_timeout = float(config.get("tts_timeout", 12))\n        self.delete_audio_file = delete_audio_file')
    text=text.replace('max_repeat_time = 5','max_repeat_time = 2').replace('5 - max_repeat_time','2 - max_repeat_time')
    for target in ('None','tmp_file'):
        text=text.replace(f'asyncio.run(self.text_to_speak(text, {target}))',
                          f'asyncio.run(asyncio.wait_for(self.text_to_speak(text, {target}), timeout=self.tts_timeout))')
    tts.write_text(text,encoding='utf-8',newline='\n')
    edge=server/'core/providers/tts/edge.py'
    replace(edge,'                pitch=self.edge_pitch,',
            '                pitch=self.edge_pitch,\n                connect_timeout=5, receive_timeout=10,')
    replace(server/'core/utils/dialogue.py',r'''                full_prompt = re.sub(
                    r"<memory>.*?</memory>",
                    f"<memory>\n{memory_str}\n</memory>",
                    full_prompt,
                    flags=re.DOTALL,
                )''',r'''                memory_block = f"<memory>\n{memory_str}\n</memory>"
                full_prompt, inserted = re.subn(
                    r"<memory>.*?</memory>",
                    lambda _: memory_block,
                    full_prompt,
                    flags=re.DOTALL,
                )
                if not inserted:
                    full_prompt += "\n" + memory_block''')
    replace(server/'core/connection.py','    async def close(self, ws=None):\n        """资源清理方法"""',
        '    async def close(self, ws=None):\n        """资源清理方法"""\n'
        '        if self.memory is not None and hasattr(self.memory, "stop_memory_watch"):\n'
        '            await self.memory.stop_memory_watch()')
    shutil.copyfile(root/'backend/pet_official_memory.py',server/'core/pet_official_memory.py')
    shutil.copyfile(root/'backend/pet_official_proxy.py',server/'core/pet_official_proxy.py')
    replace(server/'core/websocket_server.py','from core.connection import ConnectionHandler',
        'from core.connection import ConnectionHandler\nfrom core.pet_official_proxy import proxy_if_selected')
    replace(server/'core/websocket_server.py','        # 创建ConnectionHandler时传入当前server实例',
        '        if await proxy_if_selected(websocket, self.config):\n            return\n        # 创建ConnectionHandler时传入当前server实例')
    shutil.copyfile(root/'backend/pet_memory_admin.py',server/'core/api/pet_memory_handler.py')
    http=server/'core/http_server.py'
    replace(http,'from core.api.ota_handler import OTAHandler',
        'from core.api.ota_handler import OTAHandler\nfrom core.api.pet_memory_handler import PetMemoryHandler')
    replace(http,'        self.ota_handler = OTAHandler(config)',
        '        self.ota_handler = OTAHandler(config)\n        self.pet_memory_handler = PetMemoryHandler(config)')
    replace(http,'                app = web.Application()',
        '                app = web.Application()\n                app.router.add_post("/pet/memory", self.pet_memory_handler.handle)')
    shutil.copyfile(root/'backend/pet_voice_source.py',server/'core/pet_voice_source.py')
    receive=server/'core/handle/receiveAudioHandle.py'
    replace(receive,'async def startToChat(conn: "ConnectionHandler", text):',
        '@voice_source\nasync def startToChat(conn: "ConnectionHandler", text):')
    text=receive.read_text(encoding='utf-8')
    if 'from core.pet_voice_source import voice_source' not in text:
        receive.write_text('from core.pet_voice_source import voice_source\n'+text,encoding='utf-8',newline='\n')
    sender=server/'core/handle/sendAudioHandle.py'
    text=sender.read_text(encoding='utf-8')
    if 'from core.pet_voice_source import transcript_metadata' not in text:
        sender.write_text('from core.pet_voice_source import transcript_metadata\n'+text,encoding='utf-8',newline='\n')
    replace(sender,'{"type": "stt", "text": stt_text, "session_id": conn.session_id}',
        '{"type": "stt", "text": stt_text, "session_id": conn.session_id, **transcript_metadata(conn)}')
    replace(server/'core/providers/asr/base.py','await startToChat(conn, enhanced_text)',
        'await startToChat(conn, enhanced_text, pet_audio=True)')
    loader=server/'plugins_func/loadplugins.py'
    text=loader.read_text(encoding='utf-8')
    legacy='def auto_import_modules(package_name, module_names=None):'
    if legacy in text:
        loader.write_text(text.replace(legacy,'def auto_import_modules(package_name):'),encoding='utf-8',newline='\n')
    replace(loader,'def auto_import_modules(package_name):',
            'def auto_import_modules(package_name, module_names=("handle_exit_intent", "play_music")):')
    replace(loader,'        full_module_name = f"{package_name}.{module_name}"',
            '        if module_names is not None and module_name not in module_names:\n            continue\n        full_module_name = f"{package_name}.{module_name}"')
    # Known MP3 input already identifies its decoder; pydub need not invoke ffprobe.
    utility=server/'core/utils/util.py'
    text=utility.read_text(encoding='utf-8')
    old='format=file_type, parameters=["-nostdin"]'
    new='format=file_type, codec="mp3" if file_type=="mp3" else None, parameters=["-nostdin"]'
    if old in text:
        if text.count(old)!=4:
            raise RuntimeError('Audio conversion overlay context changed')
        utility.write_text(text.replace(old,new),encoding='utf-8',newline='\n')
    elif text.count(new)!=4:
        raise RuntimeError('Audio conversion overlay missing expected call sites')
    shutil.copyfile(root/'scripts/voice_network.py',server/'core/pet_network.py')
    replace(server/'core/websocket_server.py', 'from core.auth import AuthManager, AuthenticationError',
            'from core.pet_network import device_allowed\nfrom core.auth import AuthManager, AuthenticationError')
    replace(server/'core/websocket_server.py',
            '        headers = dict(websocket.request.headers)\n        if headers.get("device-id", None) is None:',
            '        headers = dict(websocket.request.headers)\n        if not device_allowed(headers, self.config):\n            await websocket.close(code=1008, reason="Device not bound")\n            return\n        if headers.get("device-id", None) is None:')
    replace(server/'core/api/ota_handler.py', 'from core.auth import AuthManager',
            'from core.pet_network import device_allowed\nfrom core.auth import AuthManager')
    replace(server/'core/api/ota_handler.py',
            '        try:\n            data = await request.text()',
            '        if not device_allowed(request.headers, self.config):\n            return web.json_response({"error": "DEVICE_NOT_BOUND"}, status=403)\n        try:\n            data = await request.text()')
    tools = server/'core/providers/tools'
    replace(tools/'device_mcp/mcp_executor.py','            if tool_name:\n',
            '            if tool_name in ("self_pet_memory_offer", "self_pet_memory_status"):\n                continue\n            if tool_name:\n')
    shutil.copyfile(root/'backend/pet_identity.py',tools/'pet_identity.py')
    replace(tools/'unified_tool_handler.py','from .base import ToolType',
            'from .pet_identity import bind_pet_call\nfrom .base import ToolType')
    replace(tools/'unified_tool_handler.py','    async def handle_llm_function_call(',
            '    @bind_pet_call\n    async def handle_llm_function_call(')
    replace(server/'core/connection.py','                            self, tool_call_data\n',
            '                            self, dict(tool_call_data, _pet_sentence_id=current_sentence_id)\n')
    replace(server/'core/connection.py','            role_id=self.device_id,\n            llm=self.llm,',
            '            role_id=self.device_id,\n            llm=self.llm,\n            pet_connection=self,')
    replace(server/'core/connection.py','        self.memory.init_memory(\n',
            '        if hasattr(self.memory, "for_connection"):\n'
            '            self.memory = self.memory.for_connection(self)\n'
            '        self.memory.init_memory(\n')
    replace(server/'core/connection.py','                    self.memory.query_memory(query), self.loop',
            '                    (self.memory.query_pet_memory(query, current_sentence_id)\n'
            '                     if hasattr(self.memory, "query_pet_memory") else self.memory.query_memory(query)), self.loop')
    replace(server/'core/connection.py','                memory_str = future.result()\n',
            '                memory_str = future.result()\n'
            '                if current_sentence_id != self.sentence_id or self.client_abort:\n'
            '                    return None\n')
    replace(server/'core/connection.py','                if self.client_abort:\n',
            '                if self.client_abort or current_sentence_id != self.sentence_id:\n')
    replace(server/'core/connection.py','        # 处理function call\n',
            '        if current_sentence_id != self.sentence_id or self.client_abort:\n            return None\n'
            '        # 处理function call\n')
    replace(server/'core/connection.py','                if tool_results:\n',
            '                if current_sentence_id != self.sentence_id or self.client_abort:\n                    return None\n'
            '                if tool_results:\n')
    replace(server/'core/connection.py','        # 存储对话内容\n',
            '        if current_sentence_id != self.sentence_id or self.client_abort:\n            return None\n'
            '        # 存储对话内容\n')
    replace(server/'core/connection.py','                            da_response = self._clean_response_garbage(da_response)',
            '                            if current_sentence_id != self.sentence_id or self.client_abort:\n                                return None\n'
            '                            da_response = self._clean_response_garbage(da_response)')
    handler = tools/'device_mcp/mcp_handler.py'
    text = handler.read_text(encoding='utf-8')
    text = text.replace('pet_request = await care_request_id(conn, mcp_client, actual_name)',
                        'pet_request = await care_request_id(conn, mcp_client, actual_name, arguments)')
    handler.write_text(text,encoding='utf-8',newline='\n')
    replace(handler,'    tool_call_id = await mcp_client.get_next_id()\n    result_future = asyncio.Future()\n    await mcp_client.register_call_result_future(tool_call_id, result_future)',
            '    # Register the result future only after arguments and pet context validate.')
    replace(handler,'    actual_name = mcp_client.name_mapping.get(tool_name, tool_name)\n    payload = {',
            '''    actual_name = mcp_client.name_mapping.get(tool_name, tool_name)
    from core.providers.tools.pet_identity import care_request_id
    pet_request = await care_request_id(conn, mcp_client, actual_name, arguments)
    tool_call_id = await mcp_client.get_next_id()
    result_future = asyncio.Future()
    await mcp_client.register_call_result_future(tool_call_id, result_future)
    payload = {''')
    replace(handler,'    logger.bind(tag=TAG).info(f"发送客户端mcp工具调用请求: {actual_name}，参数: {args}")',
            '''    if pet_request is not None:
        payload["params"]["_meta"] = {"pet_request_id": pet_request}
    logger.bind(tag=TAG).info(f"发送客户端mcp工具调用请求: {actual_name}，参数: {args}")''')
