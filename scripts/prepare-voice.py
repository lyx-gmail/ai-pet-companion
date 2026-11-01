"""Prepare private voice config and owned provider overlay; never start the server."""
from pathlib import Path
import argparse
import json
import secrets
import shutil
import subprocess
from urllib.parse import urlsplit
from voice_network import network_config

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'.tools/upstream/xiaozhi-esp32-server'
PIN = '1a095d5bed23e49a17f817c7f378e2a86f298dfc'


def replace_once(path,old,new):
    text = path.read_text(encoding='utf-8')
    if new in text:
        return
    if text.count(old)!=1:
        raise RuntimeError('Voice overlay context changed: '+path.name)
    path.write_text(text.replace(old,new,1),encoding='utf-8',newline='\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bind-ip', default='127.0.0.1')
    parser.add_argument('--diagnostic-logging', action='store_true')
    args = parser.parse_args()
    head = subprocess.check_output(['git','-c','safe.directory='+SOURCE.as_posix(),
                                    '-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip()
    if head!=PIN:
        raise RuntimeError('Voice server pin mismatch')
    values = {}
    for line in (ROOT/'.env').read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        name,value = line.split('=',1)
        values[name.strip()] = value.strip().strip('"').strip("'")
    for key in ('PET_LLM_BASE_URL','PET_LLM_MODEL','PET_LLM_API_KEY','PET_API_TOKEN'):
        if not values.get(key):
            raise RuntimeError('Missing private setting: '+key)
    if urlsplit(values['PET_LLM_BASE_URL']).scheme!='https':
        raise RuntimeError('Voice LLM endpoint must use HTTPS')
    network = network_config(args.bind_ip, values.get('PET_DEVICE_ID',''))
    runtime = ROOT/'.runtime/voice'
    runtime.mkdir(parents=True,exist_ok=True)
    key_path = runtime/'auth.key'
    if not key_path.exists():
        key_path.write_text(secrets.token_hex(32),encoding='ascii')
    auth_key = key_path.read_text(encoding='ascii').strip()
    if len(auth_key)!=64 or any(c not in '0123456789abcdef' for c in auth_key):
        raise RuntimeError('Invalid private voice auth key; original retained')
    server = SOURCE/'main/xiaozhi-server'
    destination = server/'data/.config.yaml'
    if destination.exists():
        import yaml
        existing = yaml.safe_load(destination.read_text(encoding='utf-8'))
        if not isinstance(existing,dict) or existing.get('_pet_generated_version')!=1:
            raise RuntimeError('Unowned voice config exists; original retained')
    model_dir = ROOT/'.tools/voice-models/sense-voice-int8'
    if not (model_dir/'model.int8.onnx').is_file():
        raise RuntimeError('Run setup-speech-models.py first')
    config = {
        '_pet_generated_version':1,
        'pet_official':{'mode_file':str(runtime/'backend.json'),
                        'identity_file':str(ROOT/'.runtime/official-ai/device-identity.json')},
        'server':{'ip':network['ip'],'port':8000,'http_port':8003,
                  'websocket':network['websocket'],
                  'vision_explain':network['vision_explain'],
                  'auth_key':auth_key,'auth':{'enabled':True,'allowed_devices':[]}},
        'manager-api':{'url':'','secret':''},
        'log':{'log_level':'INFO' if args.diagnostic_logging else 'ERROR','log_dir':str(runtime/'logs'),'data_dir':str(runtime/'data')},
        'delete_audio':True,'enable_wakeup_words_response_cache':False,'enable_greeting':False,
        'mcp_endpoint':'',
        'prompt_template':str(ROOT/'backend/voice-pet-template.jinja'),
        # This board sends 16kHz/60ms in hello. Keep the encoder's configured
        # rate equal to the echoed reply, rather than the upstream 24kHz default.
        'xiaozhi':{'audio_params':{'format':'opus','sample_rate':16000,'channels':1,'frame_duration':60}},
        'selected_module':{'VAD':'SileroVAD','ASR':'SherpaASR','LLM':'PetLLM',
                           'TTS':'EdgeTTS','Memory':'PetMemory','Intent':'function_call'},
        'ASR':{'SherpaASR':{'type':'sherpa_onnx_local','model_type':'sense_voice',
                            'model_dir':str(model_dir),'output_dir':str(runtime/'audio')}},
        'VAD':{'SileroVAD':{'model_dir':str(server/'models/snakers4_silero-vad'),'min_silence_duration_ms':600}},
        'LLM':{'PetLLM':{'type':'openai','model_name':values['PET_LLM_MODEL'],
                         'base_url':values['PET_LLM_BASE_URL'],'api_key':values['PET_LLM_API_KEY'],
                         'thinking':'off','max_tokens':256,'timeout':30}},
        'TTS':{'EdgeTTS':{'output_dir':str(runtime/'audio'),'rate':25,'tts_timeout':12}},
        'Memory':{'PetMemory':{'type':'mem_pet','endpoint':'http://127.0.0.1:8766',
                               'token':values['PET_API_TOKEN'],'expected_device_id':network['expected_device_id']}},
        'Intent':{'function_call':{'functions':[]}},
        'prompt':'你是一位温和、简洁的实体宠物伙伴，通常用一句话回答，优先30字以内，避免重复铺垫。称呼与偏好只依据已确认记忆；记忆不可用时明确说明。询问宠物状态先调用self.pet.get_state，不编造数值；未收到动作工具成功结果，不能声称执行了喂食、抚摸或睡眠。没有摄像头或触摸传感器。记忆确认提示由程序单独播报；普通回复只报告实际结果，不得自行要求按中键保存或声称创建草稿。'
    }
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    package = server/'core/providers/memory/mem_pet'
    package.mkdir(parents=True,exist_ok=True)
    for source in (ROOT/'backend/xiaozhi_memory/mem_pet').glob('*.py'):
        shutil.copyfile(source,package/source.name)
    from voice_pet_patch import apply as patch_pet_tools
    patch_pet_tools(ROOT,server,replace_once)
    mode = 'loopback only' if network['ip']=='127.0.0.1' else 'explicit local LAN address'
    print('Private config prepared: '+mode+', authentication enabled, device binding '+
          ('configured' if network['expected_device_id'] else 'pending (memory fails closed)')+'. No server started.')


if __name__=='__main__':
    main()
