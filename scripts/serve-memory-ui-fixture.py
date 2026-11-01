"""Owned test-only HTTP bridge on the device's existing LAN port; RAM store only."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sys
from aiohttp import web

ROOT=Path(__file__).resolve().parents[1]
SERVER=ROOT/'.tools/upstream/xiaozhi-esp32-server/main/xiaozhi-server'
sys.path.insert(0,str(SERVER))
from core.api.pet_memory_handler import PetMemoryHandler


def main():
    config=json.loads((SERVER/'data/.config.yaml').read_text(encoding='utf-8'))
    config=deepcopy(config);config['Memory']['PetMemory']['endpoint']='http://127.0.0.1:8767'
    handler=PetMemoryHandler(config)
    folder=ROOT/'.runtime/memory-ui';folder.mkdir(parents=True,exist_ok=True)
    async def route(request):
        raw=await request.read()
        try:value=json.loads(raw)
        except ValueError:value={}
        with (folder/'requests.jsonl').open('a',encoding='utf-8') as trace:
            trace.write(json.dumps({key:value[key] for key in ('action','id','field') if key in value})+'\n')
        delay=folder/'delay-profile-once'
        if value.get('action')=='profile' and delay.exists():
            delay.unlink();await asyncio.sleep(1.5)
        response=await handler.handle(request)
        drop=folder/'drop-confirm-once'
        if value.get('action')=='confirm' and response.status==200 and drop.exists():
            drop.unlink()
            if request.transport:request.transport.abort()
        return response
    app=web.Application(client_max_size=1024)
    app.router.add_post('/pet/memory',route)
    web.run_app(app,host=config['server']['ip'],port=config['server']['http_port'],print=None)


if __name__=='__main__':main()
