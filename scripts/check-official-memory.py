"""Official AI reads/corrects/forgets fictional names in an isolated RAM store."""
import asyncio
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import argparse

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend/xiaozhi_memory'))
from mem_pet.client import PetMemoryClient
from official_ai_probe import exercise


def main(write_only=False):
    config=json.loads((ROOT/'.tools/upstream/xiaozhi-esp32-server/main/xiaozhi-server/data/.config.yaml').read_text(encoding='utf-8'))
    memory=config['Memory']['PetMemory']
    formal=PetMemoryClient(memory['endpoint'],memory['token'])
    fixture=PetMemoryClient('http://127.0.0.1:8767',memory['token'])
    before=formal.profile()
    result={'ok':False,'source':'official_AI_authenticated_router_real_USB_state_and_isolated_RAM_memory',
        'fixture_only':True,'formal_memory_unchanged':False,'physical_device_backend_changed':False,
        'physical_memory_confirmation_verified':False,'hardware_ASR_verified':False,'steps':[]}
    process=None
    folder=ROOT/'.runtime/official-ai';folder.mkdir(parents=True,exist_ok=True)
    try:
        with socket.socket() as probe:probe.bind(('127.0.0.1',8767))
        with (folder/'memory-fixture.log').open('wb') as log:
            process=subprocess.Popen([str(ROOT/'.tools/node22/node-v22.23.4-win-x64/node.exe'),
                str(ROOT/'scripts/start-memory-fixture.cjs')],cwd=ROOT,stdout=log,stderr=log,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            deadline=time.monotonic()+10
            while True:
                try:
                    empty=fixture.profile()
                    if empty!={'revision':0,'name':None,'preferences':[]}:raise ValueError('NONEMPTY_FIXTURE')
                    break
                except Exception:
                    if process.poll() is not None or time.monotonic()>deadline:raise
                    time.sleep(.1)
            old='星河小柚';new='回声小桥'
            cases=() if write_only else (
                ('initial',old,0,()),('corrected',new,1,(old,)),('deleted',None,2,(old,new)))
            for label,value,revision,forbidden in cases:
                source='测试夹具：以后叫我'+(value or new)
                draft=fixture.request('propose',{'kind':'profile','op':'set' if value else 'delete',
                    'field':'name','value':value or new,'source':source,'quote':value or new,'expectedRevision':revision})
                committed=fixture.request('confirm',{'id':draft['id'],'requestId':'fixture-'+draft['id']})
                if committed.get('revision')!=revision+1:raise ValueError('FIXTURE_REVISION_INVALID')
                print('Official memory check: '+label,flush=True)
                code=asyncio.run(exercise(audio=True,bridge=True,question='name',
                    fixture_memory_endpoint='http://127.0.0.1:8767',expected_fixture_name=value,
                    forbidden_fixture_names=forbidden))
                evidence=json.loads((ROOT/'evaluation/official-ai-proxy-read-name-check.json').read_text(encoding='utf-8'))
                result['steps'].append({'stage':label,'fixture_revision':revision+1,**evidence})
                shutil.copyfile(folder/'proxy-read-name-session.json',folder/('memory-'+label+'-session.json'))
                if code:raise ValueError('OFFICIAL_MEMORY_REPLY_NOT_VERIFIED')
            if write_only:
                code=asyncio.run(exercise(audio=True,bridge=True,question='remember',
                    fixture_memory_endpoint='http://127.0.0.1:8767',fixture_consent='confirmed'))
                evidence=json.loads((ROOT/'evaluation/official-ai-proxy-remember-check.json').read_text(encoding='utf-8'))
                after=fixture.profile()
                verified=after.get('revision')==1 and after.get('name')=='小明'
                result['steps'].append({'stage':'software_confirmed_write','fixture_profile_write_verified':verified,**evidence})
                if code or not verified:raise ValueError('OFFICIAL_MEMORY_WRITE_NOT_VERIFIED')
        result['ok']=True
    except Exception as error:
        result['error_type']=type(error).__name__
        if str(error).isupper() and '_' in str(error):result['error_code']=str(error)
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
        try:result['formal_memory_unchanged']=formal.profile()==before
        except Exception:pass
        result['ok']=result['ok'] and result['formal_memory_unchanged']
        name='official-memory-write-check.json' if write_only else 'official-memory-check.json'
        (ROOT/'evaluation'/name).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'ok':result['ok'],'steps_completed':len(result['steps']),
        'formal_memory_unchanged':result['formal_memory_unchanged'],'error_code':result.get('error_code')}))
    return 0 if result['ok'] else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write-only',action='store_true',help='One fictional-name write using software consent, never physical acceptance.')
    raise SystemExit(main(parser.parse_args().write_only))
