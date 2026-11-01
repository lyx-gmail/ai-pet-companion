"""Install hash-pinned Windows voice binaries inside the ignored project tools.

Run with .tools/voice-venv/Scripts/python.exe after requirements-voice.txt.
No system PATH, registry, model credentials or device settings are changed.
"""
from pathlib import Path
import hashlib
import json
import shutil
import tarfile
import urllib.request
import zipfile
import imageio_ffmpeg
import zstandard

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / '.tools'
NAME = 'libopus-1.6.1-h6a83c73_1.conda'
URL = 'https://conda.anaconda.org/conda-forge/win-64/' + NAME
SHA256 = '0ca8a5f9c6505344d3c57068b50d2cfffe497e3ce1aa697deb46d8ab502d3cfa'


def main():
    cache = TOOLS / 'downloads' / NAME
    cache.parent.mkdir(parents=True,exist_ok=True)
    if not cache.exists():
        with urllib.request.urlopen(URL,timeout=60) as response:
            data = response.read(8*1024*1024+1)
        if len(data)>8*1024*1024 or hashlib.sha256(data).hexdigest()!=SHA256:
            raise RuntimeError('Opus archive size/hash mismatch')
        cache.write_bytes(data)
    if hashlib.sha256(cache.read_bytes()).hexdigest()!=SHA256:
        raise RuntimeError('Cached Opus archive hash mismatch; original retained')
    destination = TOOLS / 'voice-native'
    binaries = destination / 'bin'
    licenses = destination / 'licenses'
    binaries.mkdir(parents=True,exist_ok=True)
    licenses.mkdir(parents=True,exist_ok=True)
    found = False
    with zipfile.ZipFile(cache) as package:
        for entry in package.namelist():
            if not entry.endswith('.tar.zst'):
                continue
            with package.open(entry) as packed:
                with zstandard.ZstdDecompressor().stream_reader(packed) as stream:
                    with tarfile.open(fileobj=stream,mode='r|') as archive:
                        for member in archive:
                            if not member.isfile():
                                continue
                            name = member.name.replace('\\','/')
                            target = None
                            if name=='Library/bin/opus.dll':
                                target = binaries / 'opus.dll'
                                found = True
                            elif name.startswith('info/licenses/'):
                                target = licenses / ('opus-'+Path(name).name)
                            if target is None:
                                continue
                            if member.size>20*1024*1024:
                                raise RuntimeError('Unexpected native file size')
                            source = archive.extractfile(member)
                            if source is None:
                                raise RuntimeError('Invalid native archive entry')
                            # No archive path is extracted: only fixed/flattened destinations.
                            with source,target.open('wb') as output:
                                shutil.copyfileobj(source,output)
    if not found:
        raise RuntimeError('Pinned package does not contain expected opus.dll')
    ffmpeg_source = Path(imageio_ffmpeg.get_ffmpeg_exe())
    shutil.copy2(ffmpeg_source,binaries/'ffmpeg.exe')
    record = {'opus':{'version':'1.6.1','archive_sha256':SHA256,'source':URL},
              'ffmpeg':{'provider':'imageio-ffmpeg==0.6.0','filename':ffmpeg_source.name},
              'system_changes':False}
    (destination/'sources.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    print('Portable Opus and FFmpeg prepared in .tools/voice-native/bin; system settings unchanged.')


if __name__=='__main__':
    main()
