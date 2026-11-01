"""Exercise real MP3 -> PCM -> Opus conversion offline, with ffprobe lookup forbidden."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]


def main():
    binaries=ROOT/'.tools/voice-native/bin'
    server=ROOT/'.tools/upstream/xiaozhi-esp32-server/main/xiaozhi-server'
    os.environ['PATH']=str(binaries)+os.pathsep+os.environ['PATH']
    sys.path.insert(0,str(server)); os.chdir(server)
    result={'source':'actual_upstream_audio_conversion_with_generated_tone','cloud_api_called':False,
            'hardware_microphone_verified':False,'hardware_playback_verified':False,'ffprobe_lookup_forbidden':True}
    try:
        with os.add_dll_directory(str(binaries)), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            import app
            from core.utils.util import audio_bytes_to_data_stream
            import opuslib_next
            fixture=subprocess.run([str(binaries/'ffmpeg.exe'),'-hide_banner','-loglevel','error','-f','lavfi','-i','sine=frequency=440:duration=0.3','-f','mp3','pipe:1'],check=True,capture_output=True).stdout
            packets=[]
            with patch('pydub.audio_segment.mediainfo_json',side_effect=RuntimeError('UNEXPECTED_FFPROBE_DEPENDENCY')):
                audio_bytes_to_data_stream(fixture,'mp3',True,packets.append,sample_rate=16000)
            decoder=opuslib_next.Decoder(16000,1)
            restored=[decoder.decode(packet,960) for packet in packets]
            if not restored or not all(len(frame)==1920 for frame in restored) or not any(any(frame) for frame in restored):
                raise RuntimeError('INVALID_OPUS_AUDIO_ROUNDTRIP')
            result.update(mp3_bytes=len(fixture),opus_frames=len(packets),pcm_bytes=sum(map(len,restored)),sample_rate=16000,frame_duration_ms=60,ok=True)
            from loguru import logger
            logger.remove()
    except Exception as error:
        result.update(ok=False,error_type=type(error).__name__)
        if str(error)=='UNEXPECTED_FFPROBE_DEPENDENCY': result['unexpected_ffprobe_lookup']=True
    (ROOT/'evaluation/voice-audio-conversion-check.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))
    return 0 if result['ok'] else 1


if __name__=='__main__': raise SystemExit(main())
