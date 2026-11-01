"""Download the fixed official int8 model; validate before extracting allowlisted files."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import shutil
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with path.open('rb') as file:
        return hashlib.file_digest(file,'sha256').hexdigest()


def main():
    lock = json.loads((ROOT/'backend/locks/speech-models.json').read_text(encoding='utf-8'))
    spec = lock['sense_voice']
    archive = ROOT/'.tools/downloads'/spec['name']
    archive.parent.mkdir(parents=True,exist_ok=True)
    if not archive.exists():
        partial = archive.with_suffix(archive.suffix+'.part')
        request = urllib.request.Request(spec['url'],headers={'User-Agent':'ai-pet-reproduction'})
        print('Downloading fixed official SenseVoice int8 model (163 MB).',flush=True)
        received = 0
        with urllib.request.urlopen(request,timeout=60) as response,partial.open('wb') as output:
            while chunk := response.read(1024*1024):
                received += len(chunk)
                if received>spec['size']:
                    raise RuntimeError('Speech archive exceeded pinned size')
                output.write(chunk)
        if received!=spec['size'] or digest(partial)!=spec['sha256']:
            raise RuntimeError('Speech archive hash/size mismatch; partial retained for diagnosis')
        partial.replace(archive)
    if archive.stat().st_size!=spec['size'] or digest(archive)!=spec['sha256']:
        raise RuntimeError('Cached speech archive does not match lock; original retained')
    destination = ROOT/'.tools/voice-models/sense-voice-int8'
    destination.mkdir(parents=True,exist_ok=True)
    prefix = spec['name'].removesuffix('.tar.bz2')
    # Only our known relative destinations are written; no generic tar extraction.
    allowed = {'model.int8.onnx','tokens.txt','test_wavs/zh.wav','test_wavs/en.wav','LICENSE','LICENSE.txt','README.md'}
    extracted = []
    with tarfile.open(archive,'r:bz2') as package:
        for member in package:
            path = PurePosixPath(member.name)
            if not member.isfile() or not path.parts or path.parts[0]!=prefix:
                continue
            relative = PurePosixPath(*path.parts[1:]).as_posix()
            if relative not in allowed:
                continue
            if member.size>300*1024*1024:
                raise RuntimeError('Unexpected model file size')
            target = destination/relative
            target.parent.mkdir(parents=True,exist_ok=True)
            source = package.extractfile(member)
            if source is None:
                raise RuntimeError('Invalid speech archive entry')
            with source,target.open('wb') as output:
                shutil.copyfileobj(source,output)
            extracted.append(relative)
    if not {'model.int8.onnx','tokens.txt'}.issubset(extracted):
        raise RuntimeError('Fixed archive layout does not match selected provider')
    vad = ROOT/'.tools/upstream/xiaozhi-esp32-server'/lock['silero_vad']['file']
    if digest(vad)!=lock['silero_vad']['sha256']:
        raise RuntimeError('Existing upstream VAD model hash mismatch')
    result = {'archive_sha256':spec['sha256'],'files':{name:digest(destination/name) for name in extracted},
              'vad_sha256':digest(vad),'hardware_voice_verified':False}
    (ROOT/'evaluation/speech-model-files.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print('Model files and existing VAD verified; no speech server started.',flush=True)


if __name__=='__main__':
    main()
