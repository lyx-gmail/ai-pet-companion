"""Check pet tool patches on pristine pinned server files and repeat application."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from voice_pet_patch import apply

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT/'.tools/upstream/xiaozhi-esp32-server'
PIN = '1a095d5bed23e49a17f817c7f378e2a86f298dfc'
FILES = ['core/providers/tts/base.py','core/providers/tts/edge.py','core/connection.py','core/utils/dialogue.py','core/providers/tools/unified_tool_handler.py',
         'core/providers/tools/device_mcp/mcp_handler.py',
         'core/websocket_server.py','core/api/ota_handler.py',
         'plugins_func/loadplugins.py','core/utils/util.py','core/providers/tools/device_mcp/mcp_executor.py',
         'core/handle/receiveAudioHandle.py','core/handle/sendAudioHandle.py','core/providers/asr/base.py','core/http_server.py']


def replace(path,old,new):
    text = path.read_text(encoding='utf-8')
    if new in text:
        return
    if text.count(old)!=1:
        raise RuntimeError('Voice tool patch context changed: '+path.name)
    path.write_text(text.replace(old,new),encoding='utf-8',newline='\n')


(ROOT/'.runtime/checks').mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(prefix='pet-voice-overlay-',dir=ROOT/'.runtime/checks') as directory:
    server = Path(directory)
    for name in FILES:
        data = subprocess.run(['git','-c',f'safe.directory={UPSTREAM.as_posix()}',
                               '-C',str(UPSTREAM),'show',f'{PIN}:main/xiaozhi-server/{name}'],
                              check=True,capture_output=True).stdout
        path = server/name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(data)
    apply(ROOT,server,replace)
    names = FILES+['core/providers/tools/pet_identity.py','core/pet_network.py','core/pet_voice_source.py','core/api/pet_memory_handler.py','core/pet_official_proxy.py','core/pet_official_memory.py']
    first = {name:hashlib.sha256((server/name).read_bytes()).hexdigest() for name in names}
    apply(ROOT,server,replace)
    second = {name:hashlib.sha256((server/name).read_bytes()).hexdigest() for name in names}
    if first!=second:
        raise RuntimeError('Voice tool overlay is not idempotent')
    routing=(server/'core/websocket_server.py').read_text(encoding='utf-8')
    if not (routing.index('if not device_allowed') < routing.index('await self._handle_auth(websocket)') <
            routing.index('if await proxy_if_selected') < routing.index('handler = ConnectionHandler(')):
        raise RuntimeError('Official proxy must run after binding/authentication and before local providers')
result = {'ok':True,'server_commit':PIN,'pristine_patch':True,'idempotent':True,'files':second}
(ROOT/'evaluation/voice-overlay-check.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print('Pristine pinned voice tool overlay and repeated application passed.')
