"""Construct actual upstream modules; never call start(), listen, TTS or the LLM API."""
from pathlib import Path
from datetime import date
import asyncio
import contextlib
import io
import json
import os
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    source = ROOT/'.tools/upstream/xiaozhi-esp32-server/main/xiaozhi-server'
    binaries = ROOT/'.tools/voice-native/bin'
    os.environ['PATH'] = str(binaries)+os.pathsep+os.environ['PATH']
    sys.path.insert(0,str(source))
    os.chdir(source)
    result = {'date':date.today().isoformat(),'listening':False,'cloud_api_called':False,
              'hardware_voice_verified':False,'modules_constructed':False}
    try:
        with os.add_dll_directory(str(binaries)), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            import app
            from config.config_loader import load_config
            from core.websocket_server import WebSocketServer
            config = asyncio.run(load_config())
            if config['server']['ip']!='127.0.0.1' or config['server']['auth'].get('enabled') is not True:
                raise ValueError('VOICE_NOT_LOOPBACK_AUTHENTICATED')
            if config['server']['auth'].get('allowed_devices') or config.get('mcp_endpoint'):
                raise ValueError('VOICE_UNEXPECTED_AUTH_BYPASS_OR_MCP')
            server = WebSocketServer(config)
            result['modules_constructed'] = all(value is not None for value in
                (server._vad,server._asr,server._llm,server._intent,server._memory))
            if not result['modules_constructed']:
                raise RuntimeError('VOICE_MISSING_SELECTED_MODULE')
            result['device_binding_configured'] = bool(server._memory.expected_device_id)
            try:
                server._memory.init_memory('diagnostic-unbound-device',server._llm)
            except ValueError as error:
                result['unbound_device_rejected'] = str(error)=='PET_DEVICE_NOT_BOUND'
            else:
                result['unbound_device_rejected'] = False
            if not result['unbound_device_rejected']:
                raise RuntimeError('VOICE_MEMORY_BINDING_CHECK_FAILED')
            if server._memory.expected_device_id:
                server._memory.init_memory(server._memory.expected_device_id,server._llm)
                result['bound_device_initialization'] = server._memory.role_id==server._memory.expected_device_id
                if not result['bound_device_initialization']:
                    raise RuntimeError('VOICE_BOUND_MEMORY_INIT_FAILED')
            from loguru import logger
            logger.remove()
        result['ok'] = True
    except Exception as error:
        result['ok'] = False
        result['error_type'] = type(error).__name__
        if isinstance(error,ModuleNotFoundError):
            result['missing_module'] = error.name
        # Never print third-party exceptions/configs, which can contain credentials.
    (ROOT/'evaluation/voice-import-check.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))
    return 0 if result['ok'] else 1


if __name__=='__main__':
    raise SystemExit(main())
