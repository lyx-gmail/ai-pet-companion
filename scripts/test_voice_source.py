import asyncio
import ast
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from pet_voice_source import voice_source, transcript_metadata

class SourceChecks(unittest.IsolatedAsyncioTestCase):
    async def test_real_sender_serializes_adapter_provenance(self):
        server=Path(__file__).resolve().parents[1]/'.tools/upstream/xiaozhi-esp32-server/main/xiaozhi-server'
        tree=ast.parse((server/'core/handle/sendAudioHandle.py').read_text(encoding='utf-8'))
        node=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='send_stt_message')
        sent=[]
        async def send(value): sent.append(json.loads(value))
        async def tts(*args): pass
        namespace={'json':json,'transcript_metadata':transcript_metadata,'textUtils':SimpleNamespace(get_string_no_punctuation_or_emoji=lambda t:t.strip()),'send_tts_message':tts}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'<real-upstream-stt>','exec'),namespace)
        conn=SimpleNamespace(config={},session_id='fixture',websocket=SimpleNamespace(send=send))
        @voice_source
        async def chat(conn,text): await namespace['send_stt_message'](conn,text)
        await chat(conn,'真实转写',pet_audio=True)
        await chat(conn,'调试文本')
        self.assertTrue(sent[0]['pet_audio']); self.assertFalse(sent[1]['pet_audio'])
        self.assertGreater(sent[1]['pet_turn'],sent[0]['pet_turn'])
        asr=ast.parse((server/'core/providers/asr/base.py').read_text(encoding='utf-8'))
        calls=[n for n in ast.walk(asr) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='startToChat']
        self.assertEqual(len(calls),1)
        self.assertTrue(any(k.arg=='pet_audio' and isinstance(k.value,ast.Constant) and k.value.value is True for k in calls[0].keywords))

    async def test_only_asr_and_contexts_are_isolated(self):
        first,second=SimpleNamespace(),SimpleNamespace()
        @voice_source
        async def chat(conn,text):
            before=transcript_metadata(conn)
            await asyncio.sleep(0)
            self.assertEqual(before,transcript_metadata(conn))
            self.assertFalse(transcript_metadata(second if conn is first else first)['pet_audio'])
            return before
        a,b=await asyncio.gather(chat(first,'audio',pet_audio=True),chat(second,'debug'))
        self.assertTrue(a['pet_audio']); self.assertFalse(b['pet_audio'])
        self.assertGreater(a['pet_turn'],0)
        again=await chat(first,'new audio',pet_audio=True)
        self.assertGreater(again['pet_turn'],a['pet_turn'])
        self.assertEqual(transcript_metadata(first),{'pet_audio':False,'pet_turn':0})

    async def test_failure_resets_provenance(self):
        conn=SimpleNamespace()
        @voice_source
        async def bad(conn,text): raise ValueError('failed')
        with self.assertRaises(ValueError): await bad(conn,'audio',pet_audio=True)
        self.assertFalse(transcript_metadata(conn)['pet_audio'])

if __name__=='__main__': unittest.main()
