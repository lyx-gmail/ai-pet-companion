"""Real CPU ASR/VAD inference on official public test audio, not microphone input."""
from pathlib import Path
from datetime import date
import json
import time
import wave
import numpy as np
import onnxruntime
import sherpa_onnx

ROOT = Path(__file__).resolve().parents[1]


def main():
    directory = ROOT/'.tools/voice-models/sense-voice-int8'
    recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
        model=str(directory/'model.int8.onnx'),tokens=str(directory/'tokens.txt'),
        num_threads=2,sample_rate=16000,feature_dim=80,decoding_method='greedy_search',
        debug=False,use_itn=True)
    with wave.open(str(directory/'test_wavs/zh.wav'),'rb') as source:
        if source.getsampwidth()!=2 or source.getnchannels()!=1 or source.getframerate()!=16000:
            raise RuntimeError('Unexpected public speech fixture format')
        audio = np.frombuffer(source.readframes(source.getnframes()),dtype='<i2').astype(np.float32)/32768
    stream = recognizer.create_stream()
    stream.accept_waveform(16000,audio)
    start = time.perf_counter()
    recognizer.decode_stream(stream)
    elapsed = time.perf_counter()-start
    text = stream.result.text.strip()
    if not text:
        raise RuntimeError('Public speech fixture produced no ASR text')
    lock = json.loads((ROOT/'backend/locks/speech-models.json').read_text(encoding='utf-8'))
    vad_path = ROOT/'.tools/upstream/xiaozhi-esp32-server'/lock['silero_vad']['file']
    options = onnxruntime.SessionOptions()
    options.inter_op_num_threads = options.intra_op_num_threads = 1
    vad = onnxruntime.InferenceSession(str(vad_path),sess_options=options,providers=['CPUExecutionProvider'])
    state = np.zeros((2,1,128),dtype=np.float32)
    context = np.zeros((1,64),dtype=np.float32)
    silent,_ = vad.run(None,{'input':np.zeros((1,576),dtype=np.float32),'state':state,'sr':np.array(16000,dtype=np.int64)})
    probabilities = []
    for offset in range(0,len(audio)-511,512):
        samples = np.concatenate([context,audio[offset:offset+512].reshape(1,-1)],axis=1)
        output,state = vad.run(None,{'input':samples,'state':state,'sr':np.array(16000,dtype=np.int64)})
        probabilities.append(float(output.item()))
        context = samples[:,-64:]
    if not probabilities or not np.isfinite(probabilities).all() or max(probabilities)<0.5 or silent.item()>=0.5:
        raise RuntimeError('VAD smoke check failed on silence/public speech')
    result = {'date':date.today().isoformat(),'fixture':'official archive test_wavs/zh.wav',
              'fixture_is_user_recording':False,'asr_text':text,'audio_seconds':len(audio)/16000,
              'decode_seconds':round(elapsed,3),'vad_silence_probability':float(silent.item()),
              'vad_max_speech_probability':max(probabilities),'vad_frames':len(probabilities),
              'hardware_voice_verified':False,'accuracy_evaluation':False}
    (ROOT/'evaluation/speech-model-check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    main()
