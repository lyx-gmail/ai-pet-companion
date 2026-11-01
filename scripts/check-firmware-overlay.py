"""Check voice overlay against pinned pristine files, then check idempotence.

This checks patch reproducibility only, not runtime audio cancellation.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / '.tools/upstream/xiaozhi-esp32'
PIN = '43ef2f4e7f0957dc62ec7d628ac2819d226127b8'
FILES = ['main/application.h', 'main/application.cc',
         'main/audio/audio_service.h', 'main/audio/audio_service.cc','main/mcp_server.h','main/mcp_server.cc',
         'main/ota.cc','main/protocols/websocket_protocol.cc','main/protocols/protocol.h',
         'main/boards/common/wifi_board.cc']


def replace(path, old, new):
    text = path.read_text(encoding='utf-8')
    if new in text:
        return
    if text.count(old) != 1:
        raise RuntimeError(f'Unexpected overlay context: {path.name}')
    path.write_text(text.replace(old,new),encoding='utf-8',newline='\n')


spec = importlib.util.spec_from_file_location('pet_patch',ROOT/'firmware/patch_application.py')
patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patch)
spec_tools = importlib.util.spec_from_file_location('pet_tools_patch',ROOT/'firmware/patch_pet_tools.py')
patch_tools = importlib.util.module_from_spec(spec_tools)
spec_tools.loader.exec_module(patch_tools)
spec_sleep = importlib.util.spec_from_file_location('pet_sleep_patch',ROOT/'firmware/patch_pet_sleep.py')
patch_sleep = importlib.util.module_from_spec(spec_sleep)
spec_sleep.loader.exec_module(patch_sleep)
spec_chat = importlib.util.spec_from_file_location('pet_conversation_patch',ROOT/'firmware/patch_pet_conversation.py')
patch_chat = importlib.util.module_from_spec(spec_chat)
spec_chat.loader.exec_module(patch_chat)
spec_wifi = importlib.util.spec_from_file_location('pet_wifi_patch',ROOT/'firmware/patch_wifi_diagnostics.py')
patch_wifi = importlib.util.module_from_spec(spec_wifi)
spec_wifi.loader.exec_module(patch_wifi)
spec_local = importlib.util.spec_from_file_location('pet_local_boot',ROOT/'firmware/patch_local_boot.py')
patch_local = importlib.util.module_from_spec(spec_local)
spec_local.loader.exec_module(patch_local)
spec_assets = importlib.util.spec_from_file_location('pet_assets_patch',ROOT/'firmware/patch_assets.py')
patch_assets = importlib.util.module_from_spec(spec_assets)
spec_assets.loader.exec_module(patch_assets)
spec_endpoint = importlib.util.spec_from_file_location('pet_endpoint_patch',ROOT/'firmware/patch_endpoint.py')
patch_endpoint = importlib.util.module_from_spec(spec_endpoint)
spec_endpoint.loader.exec_module(patch_endpoint)
(ROOT/'.runtime/checks').mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(prefix='pet-overlay-',dir=ROOT/'.runtime/checks') as directory:
    target = Path(directory)
    for name in FILES:
        data = subprocess.run(['git','-c',f'safe.directory={UPSTREAM.as_posix()}',
                               '-C',str(UPSTREAM),'show',f'{PIN}:{name}'],
                              check=True,capture_output=True).stdout
        path = target/name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(data)
    patch.apply(target,replace)
    patch_tools.apply(target,replace)
    patch_sleep.apply(target,replace)
    patch_chat.apply(target,replace)
    patch_assets.apply(target,replace)
    patch_endpoint.apply(target,replace,'http://192.168.31.84:8003/xiaozhi/ota/')
    patch_wifi.apply(target,replace)
    patch_local.apply(target,replace)
    names = FILES+['main/pet_endpoint.h']
    first = {name:hashlib.sha256((target/name).read_bytes()).hexdigest() for name in names}
    patch.apply(target,replace)
    patch_tools.apply(target,replace)
    patch_sleep.apply(target,replace)
    patch_chat.apply(target,replace)
    patch_assets.apply(target,replace)
    patch_endpoint.apply(target,replace,'http://192.168.31.84:8003/xiaozhi/ota/')
    patch_wifi.apply(target,replace)
    patch_local.apply(target,replace)
    second = {name:hashlib.sha256((target/name).read_bytes()).hexdigest() for name in names}
    if first != second:
        raise RuntimeError('Overlay is not idempotent')
    app = (target/'main/application.cc').read_text(encoding='utf-8')
    asset_check = app[app.index('void Application::CheckAssetsVersion()'):app.index('void Application::CheckNewVersion(')]
    if 'assets.Download(' in asset_check or 'settings.EraseKey(' in asset_check or 'assets.Apply();' not in asset_check:
        raise RuntimeError('Boot must preserve assets and pending vendor update metadata')
    if app.count('if (pet_reply_blocked_ || pet_epoch != pet_voice_epoch_.load()) return;') != 5:
        raise RuntimeError('Missing scheduled reply guards')
    closed=app[app.index('    protocol_->OnAudioChannelClosed('):app.index('    protocol_->OnIncomingJson(')]
    if any(part not in closed for part in ('pet_reply_blocked_ = true;',
            'const auto closed_epoch = ++pet_voice_epoch_;','audio_service_.DiscardConversationAudio();')):
        raise RuntimeError('Closed audio channel must invalidate callbacks and discard queued conversation audio')
    network=(target/'main/boards/common/wifi_board.cc').read_text(encoding='utf-8')
    if 'wifi_station.GetRssi()' in network or 'wifi_station.GetChannel()' in network:
        raise RuntimeError('Wi-Fi status must tolerate disconnected driver snapshots without aborting')
    ota=(target/'main/ota.cc').read_text(encoding='utf-8')
    if ('config.timeout_ms = 2000;' not in ota or
            'esp_http_client_perform(client)' not in ota or
            'pet_discovery_lock.try_lock()' not in ota or
            'response->body.size() + event->data_len > 32768' not in ota):
        raise RuntimeError('Local discovery must bound connect, response and overlap without blocking the UI mutex')
    if 'if (cJSON_IsNumber(timezone_offset) && !kPetLocalOtaUrl[0])' not in ota:
        raise RuntimeError('Local pet UNIX time must stay UTC independently of display timezone')
    endpoint=(target/'main/pet_endpoint.h').read_text(encoding='utf-8')
    if ('inline std::atomic<bool> pet_utc_synced{false};' not in endpoint or
            'has_server_time_ = settimeofday(&tv, NULL) == 0;' not in ota or
            'if (has_server_time_ && kPetLocalOtaUrl[0]) pet_utc_synced.store(true);' not in ota or
            'timestamp->valuedouble <= 4102444800000.0' not in ota):
        raise RuntimeError('Only a successful bounded UTC sync in this boot may trust pet time')
    if 'if constexpr (kPetUsbDiagnostics)' not in network or 'disconnect_reason=%u' not in network:
        raise RuntimeError('Missing optional numeric Wi-Fi disconnect diagnostics')
result = {'ok':True,'firmware_commit':PIN,'pristine_patch':True,'idempotent':True,
          'files':second,'hardware_audio_verified':False}
(ROOT/'evaluation/firmware-overlay-check.json').write_text(
    json.dumps(result,indent=2)+'\n',encoding='utf-8')
print('Pristine pinned voice overlay and repeated application passed; no device runtime test.')
