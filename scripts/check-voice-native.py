"""Run the actual local codec; does not call speech/cloud APIs or open a port."""
from pathlib import Path
from datetime import date
import json
import math
import os
import struct
import subprocess


def main():
    root = Path(__file__).resolve().parents[1]
    binaries = root/'.tools/voice-native/bin'
    os.environ['PATH'] = str(binaries)+os.pathsep+os.environ['PATH']
    with os.add_dll_directory(str(binaries)):
        import opuslib_next
        encoder = opuslib_next.Encoder(16000,1,opuslib_next.APPLICATION_AUDIO)
        decoder = opuslib_next.Decoder(16000,1)
        pcm = struct.pack('<960h',*[int(3000*math.sin(2*math.pi*440*i/16000)) for i in range(960)])
        packet = encoder.encode(pcm,960)
        restored = decoder.decode(packet,960)
        if len(restored)!=len(pcm) or not any(restored):
            raise RuntimeError('Opus did not produce the expected non-silent PCM frame')
    version = subprocess.run([str(binaries/'ffmpeg.exe'),'-version'],check=True,
                             capture_output=True,text=True).stdout.splitlines()[0]
    result = {'date':date.today().isoformat(),'sample_rate':16000,'frame_duration_ms':60,'opus_pcm_bytes':len(pcm),'opus_packet_bytes':len(packet),
              'decoded_pcm_bytes':len(restored),'ffmpeg_version':version,'hardware_voice_verified':False}
    (root/'evaluation/voice-native-check.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))


if __name__=='__main__':
    main()
