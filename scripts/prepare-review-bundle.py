"""Audit an explicit public-source allowlist; optionally produce a local draft ZIP.

Never publishes or changes Git state. Finding output contains paths/categories only,
never matched credentials. License choice and clean installation remain separate gates.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import re
import tempfile
import zipfile
from urllib.parse import unquote,urlsplit

ROOT=Path(__file__).resolve().parents[1]
DIRECTORIES=('backend','firmware','scripts','tests','docs','demo','evaluation','web','device','licenses')
ROOT_FILES=('README.md','THIRD_PARTY_NOTICES.md','.env.example','.gitignore','打开服务监控.vbs','LICENSE')
EXCLUDED={'.git','.runtime','.tools','node_modules','__pycache__','backups','private-logs','build','dist'}
SUFFIXES={'.md','.txt','.py','.ps1','.vbs','.cjs','.js','.json','.yaml','.yml','.jinja',
          '.cc','.cpp','.c','.h','.html','.css','.gif','.png','.jpg','.jpeg','.svg','.pet','.lock'}
PATTERNS={
    'api_key_literal':re.compile(rb'\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}'),
    'private_key':re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'credential_in_url':re.compile(rb'[?&](?:token|api_key|secret)=[A-Za-z0-9_.%+-]{16,}',re.I),
}


def private_values(root):
    values=[]
    env=root/'.env'
    if env.exists():
        for line in env.read_text(encoding='utf-8-sig').splitlines():
            key,sep,value=line.partition('=')
            if sep and re.search(r'TOKEN|SECRET|PASSWORD|API_KEY|ENCRYPTION_KEY',key,re.I):
                value=value.strip().strip('\"\'')
                if len(value)>=12:values.append(value.encode('utf-8'))
    return values


def linked(path):
    return path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction())


def collect(root):
    files=[];findings=[]
    def add(path):
        relative=path.relative_to(root).as_posix()
        if linked(path) or not path.resolve().is_relative_to(root.resolve()):
            findings.append({'path':relative,'kind':'unsafe_link'});return
        if path.is_file():files.append(path)
    for name in ROOT_FILES:
        if linked(root/name) or (root/name).exists():add(root/name)
    for name in DIRECTORIES:
        base=root/name
        if linked(base):findings.append({'path':name,'kind':'unsafe_link'});continue
        if not base.exists():continue
        for directory,children,names in os.walk(base,followlinks=False):
            for child in list(children):
                path=Path(directory)/child
                if child in EXCLUDED or child.startswith('.'):
                    children.remove(child)
                elif linked(path):
                    findings.append({'path':path.relative_to(root).as_posix(),'kind':'unsafe_link'})
                    children.remove(child)
            for name in names:
                path=Path(directory)/name
                if (name.startswith('.') or path.suffix.lower() not in SUFFIXES
                        or name=='release-preflight.json'):continue
                add(path)
    return sorted(set(files)),findings


def inspect(root):
    files,findings=collect(root);secrets=private_values(root);entries=[]
    for path in files:
        data=path.read_bytes();relative=path.relative_to(root).as_posix()
        path_bytes=relative.encode('utf-8')
        if any(pattern.search(path_bytes) for pattern in PATTERNS.values()) or any(value in path_bytes for value in secrets):
            relative='[credential-bearing-path]'
            findings.append({'path':relative,'kind':'credential_in_path'})
        for kind,pattern in PATTERNS.items():
            for match in pattern.finditer(data):
                findings.append({'path':relative,'kind':kind,'line':data[:match.start()].count(b'\n')+1})
        if any(value in data for value in secrets):
            findings.append({'path':relative,'kind':'matches_private_configuration'})
        entries.append({'path':relative,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
    return files,dict(source_audit_passed=not findings,release_ready=False,
        private_configuration_compared=bool(secrets),credentials_compared_count=len(secrets),
        root_license_present=(root/'LICENSE').is_file(),clean_install_verified=False,
        human_media_review_verified=False,findings=findings,files=entries,
        excluded_scopes=['private configuration','databases','Flash backups','SDKs and build outputs','private logs'],
        scope='Local draft only; credential checks are bounded, not a guarantee against all sensitive content.')


def verify_archive(path,report):
    broken=[]
    with zipfile.ZipFile(path) as archive:
        names=set(archive.namelist())
        if len(names)!=len(archive.namelist()) or len(names)!=len(report['files'])+1:
            raise ValueError('BUNDLE_MEMBER_MISMATCH')
        if json.loads(archive.read('REVIEW_MANIFEST.json'))!=report:raise ValueError('BUNDLE_MANIFEST_MISMATCH')
        for entry in report['files']:
            data=archive.read(entry['path'])
            if hashlib.sha256(data).hexdigest()!=entry['sha256']:raise ValueError('BUNDLE_HASH_MISMATCH')
            if not entry['path'].endswith('.md'):continue
            text=re.sub(r'(?ms)^```.*?^```[^\n]*(?:\n|$)','',data.decode('utf-8'))
            for reference in re.findall(r'!?\[[^\]]*\]\(([^)]+)\)',text):
                url=urlsplit(reference.strip('<>'))
                if url.scheme or url.netloc or not url.path:continue
                parts=[]
                for part in (PurePosixPath(entry['path']).parent/unquote(url.path)).parts:
                    if part=='..':
                        if parts:parts.pop()
                    elif part!='.':parts.append(part)
                if '/'.join(parts) not in names:broken.append(entry['path'])
    if broken:raise ValueError('BUNDLE_BROKEN_LOCAL_LINK')
    return {'ok':True,'source_files':len(report['files']),'bytes':path.stat().st_size,
        'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'member_hashes_verified':True,'markdown_local_links_verified':True,'release_ready':False}


def bundle(root,files,report,destination):
    if not report['source_audit_passed']:raise ValueError('SOURCE_AUDIT_FAILED')
    destination=destination.resolve()
    if (not destination.is_relative_to((root/'.runtime/release').resolve())
            or not destination.is_relative_to(root.resolve())
            or linked(root/'.runtime') or linked(root/'.runtime/release')):
        raise ValueError('BUNDLE_MUST_STAY_IN_PRIVATE_RELEASE_DIRECTORY')
    destination.parent.mkdir(parents=True,exist_ok=True)
    handle,name=tempfile.mkstemp(prefix='review-',suffix='.partial',dir=destination.parent)
    os.close(handle);partial=Path(name)
    try:
        with zipfile.ZipFile(partial,'w',compression=zipfile.ZIP_DEFLATED) as archive:
            for path,entry in zip(files,report['files']):
                data=path.read_bytes()
                if linked(path) or not path.resolve().is_relative_to(root.resolve()):raise ValueError('SOURCE_LINK_CHANGED')
                if hashlib.sha256(data).hexdigest()!=entry['sha256']:raise ValueError('SOURCE_CHANGED_DURING_BUNDLE')
                archive.writestr(entry['path'],data)
            archive.writestr('REVIEW_MANIFEST.json',json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        verification=verify_archive(partial,report)
        partial.replace(destination)
        return verification
    finally:
        partial.unlink(missing_ok=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',action='store_true',help='Create a draft ZIP only if the source scan passes')
    args=parser.parse_args();files,report=inspect(ROOT)
    (ROOT/'evaluation/release-preflight.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if args.bundle:
        verification=bundle(ROOT,files,report,ROOT/'.runtime/release/ai-pet-review.zip')
        (ROOT/'.runtime/release/bundle-verification.json').write_text(json.dumps(verification,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'source_audit_passed':report['source_audit_passed'],'files':len(files),
        'finding_count':len(report['findings']),'first_findings':report['findings'][:15],'release_ready':False},ensure_ascii=False))
    return 0 if report['source_audit_passed'] else 1


if __name__=='__main__':raise SystemExit(main())
