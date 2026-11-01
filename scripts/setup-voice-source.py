"""Acquire the pinned voice source; preserve every existing checkout and its overlay."""
import json
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]


def git(folder,*arguments):
    return subprocess.check_output(['git','-c','safe.directory='+folder.resolve().as_posix(),
        '-c','core.hooksPath=','-c','http.sslBackend=openssl','-C',str(folder),*arguments],
        stderr=subprocess.PIPE,text=True,encoding='utf-8',errors='replace').strip()


def ensure_source(root,repository,commit):
    root=root.resolve()
    if root.is_relative_to(Path(tempfile.gettempdir()).resolve()):
        raise ValueError('SOURCE_ROOT_MUST_STAY_OUTSIDE_SYSTEM_TEMP')
    destination=root/'.tools/upstream/xiaozhi-esp32-server'
    for path in [root/'.tools',root/'.tools/upstream',destination]:
        if path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction()):
            raise ValueError('SOURCE_PATH_MUST_NOT_BE_A_LINK')
    if destination.exists():
        if not (destination/'.git').exists() or git(destination,'rev-parse','HEAD')!=commit:
            raise ValueError('EXISTING_SOURCE_VERSION_MISMATCH_PRESERVED')
        return {'ok':True,'reused_existing_checkout':True,'commit':commit}
    destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='voice-source-',dir=destination.parent) as folder:
        staging=Path(folder)/'checkout';staging.mkdir()
        git(staging,'init','--quiet')
        git(staging,'remote','add','origin',repository)
        git(staging,'fetch','--depth','1','origin',commit)
        git(staging,'checkout','--detach','FETCH_HEAD')
        if git(staging,'rev-parse','HEAD')!=commit:raise ValueError('FETCHED_SOURCE_PIN_MISMATCH')
        staging.rename(destination)
    return {'ok':True,'reused_existing_checkout':False,'commit':commit}


def main():
    spec=json.loads((ROOT/'backend/upstream-lock.json').read_text(encoding='utf-8'))['voice']
    print(json.dumps(ensure_source(ROOT,spec['repository'],spec['commit'])))


if __name__=='__main__':main()
