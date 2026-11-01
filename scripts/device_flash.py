"""Target-specific app-only deployment. Default is offline inspection, not writing.

Never writes bootloader, partition table, NVS, OTA selection, PHY or assets.
Private readbacks and esptool output stay in ignored .runtime/flash.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import zlib

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT/'.runtime/flash'
ORIGINAL_SHA = 'ac6e284176e0429ad8ab5d2e5655cc7c7212386de91e8314219a0f458f490d90'
LAYOUT = [(1,2,0x9000,0x4000,'nvs',0),(1,0,0xd000,0x2000,'otadata',0),
          (1,1,0xf000,0x1000,'phy_init',0),(0,16,0x20000,0x3f0000,'ota_0',0),
          (0,17,0x410000,0x3f0000,'ota_1',0),(1,130,0x800000,0x800000,'assets',0)]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def verify_backup(data, manifest):
    if len(data)!=manifest.get('bytes') or sha(data)!=manifest.get('sha256'):
        raise ValueError('Backup length or hash mismatch')
    if manifest.get('read_exit_code')==0:
        return
    if not all(manifest.get(key) for key in ('read_log','read_error_log','read_log_sha256')):
        raise ValueError('Backup transport completion not verified')
    paths = [(PRIVATE/manifest[key]).resolve() for key in ('read_log','read_error_log')]
    for path in paths:
        path.relative_to(PRIVATE.resolve())
    log = paths[0].read_bytes()
    text = log.decode('utf-8',errors='replace')
    if (sha(log)!=manifest['read_log_sha256'] or paths[1].read_bytes()
            or f'Read {len(data)} bytes at 0x00000000 ' not in text
            or 'Hard resetting via RTS pin' not in text):
        raise ValueError('Backup transport completion not verified')


def inspect_layout(data):
    if len(data)!=0x1000000:
        raise ValueError('Expected complete 16MB device backup')
    entries = []
    for offset in range(0x8000,0x9000,32):
        magic = struct.unpack_from('<H',data,offset)[0]
        if magic in (0xffff,0xebeb):
            break
        if magic!=0x50aa:
            raise ValueError('Unexpected partition table magic')
        _,kind,sub,start,size,label,flags = struct.unpack_from('<HBBII16sI',data,offset)
        entries.append((kind,sub,start,size,label.split(b'\0')[0].decode('ascii'),flags))
    if entries!=LAYOUT:
        raise ValueError('Partition table does not match this verified board')
    valid = []
    for offset in (0xd000,0xe000):
        seq = struct.unpack_from('<I',data,offset)[0]
        state,crc = struct.unpack_from('<II',data,offset+24)
        if seq in (0,0xffffffff) or state in (3,4):
            continue
        if crc==zlib.crc32(data[offset:offset+4],0xffffffff):
            valid.append((seq,state))
    if not valid:
        raise ValueError('No verified OTA boot selection; refusing to guess')
    seq,state = max(valid,key=lambda item:item[0])
    if state not in (2,0xffffffff):
        raise ValueError('OTA image is pending confirmation; refusing overwrite')
    entry = LAYOUT[3+(seq-1)%2]
    return {'slot':entry[4],'offset':entry[2],'size':entry[3],'ota_sequence':seq}


def run_tool(name,arguments,after='no_reset'):
    command = [sys.executable,'-m','esptool','--chip','esp32s3','--port','COM4',
               '--baud','460800','--before','usb_reset','--after',after,
               '--connect-attempts','3']+arguments
    with (PRIVATE/(name+'.log')).open('wb') as log:
        result = subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError('Esptool stage failed: '+name+'; inspect private log')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write',action='store_true',help='Execute bounded app write after live preservation checks')
    parser.add_argument('--backup',type=Path,default=ROOT/'device/backups/pre-pet-2026-10-31-16mb.bin')
    parser.add_argument('--manifest',type=Path,default=PRIVATE/'pre-pet-manifest.json')
    args = parser.parse_args()
    PRIVATE.mkdir(parents=True,exist_ok=True)
    original = (ROOT/'device/backups/original-2026-10-30-16mb.bin').read_bytes()
    if sha(original)!=ORIGINAL_SHA:
        raise ValueError('Original recovery backup hash mismatch')
    backup = args.backup.resolve()
    backup.relative_to((ROOT/'device/backups').resolve())
    manifest_path = args.manifest.resolve()
    manifest_path.relative_to(PRIVATE.resolve())
    before = backup.read_bytes()
    manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    verify_backup(before,manifest)
    if before[0x8000:0x9000]!=original[0x8000:0x9000]:
        raise ValueError('Device partition table changed since original backup')
    target = inspect_layout(before)
    image = ROOT/'.tools/firmware-artifacts/xiaozhi.bin'
    app = image.read_bytes()
    build = json.loads((ROOT/'evaluation/firmware-build.json').read_text(encoding='utf-8'))
    if not build['build_passed'] or len(app)!=build['app_bytes'] or sha(app)!=build['app_sha256']:
        raise ValueError('Application does not match recorded successful build')
    if not app or app[0]!=0xe9 or len(app)>target['size']:
        raise ValueError('Invalid or oversized application image')
    security = (PRIVATE/'security.log').read_text(encoding='utf-8',errors='replace')
    if 'Secure Boot: Disabled' not in security or 'Flash Encryption: Disabled' not in security:
        raise ValueError('Device security mode was not verified for this unencrypted image')
    rollback = PRIVATE/('rollback-'+backup.stem+'-app.bin')
    rollback.write_bytes(before[target['offset']:target['offset']+target['size']])
    result = dict(target,app_bytes=len(app),app_sha256=sha(app),backup_sha256=sha(before),
                  rollback_app_sha256=sha(rollback.read_bytes()),rollback_app_path=rollback.relative_to(ROOT).as_posix(),write_started=False,written=False,
                  protected_before_verified=False,protected_after_verified=False)
    if not args.write:
        (ROOT/'evaluation/device-flash-plan.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(result))
        return
    # Hold the chip in the loader after reading live control data. No original
    # app runs between this snapshot, preservation checks and the bounded write.
    control = PRIVATE/'live-control.bin'
    run_tool('live-control',['read_flash','--no-progress','0x8000','0x8000',str(control)])
    live = bytearray(before)
    live[0x8000:0x10000] = control.read_bytes()
    if len(control.read_bytes())!=0x8000 or live[0x8000:0x9000]!=before[0x8000:0x9000]:
        raise ValueError('Live control data is incomplete or partition table changed')
    if live[0xd000:0xf000]!=before[0xd000:0xf000] or inspect_layout(live)!=target:
        raise ValueError('OTA selection changed since backup; refusing write')
    prefix,suffix = PRIVATE/'protected-prefix.bin',PRIVATE/'protected-suffix.bin'
    prefix.write_bytes(live[:target['offset']])
    suffix_offset = target['offset']+target['size']
    suffix.write_bytes(live[suffix_offset:])
    protected = ['verify_flash','--diff','no','0',str(prefix),hex(suffix_offset),str(suffix)]
    run_tool('protected-before',protected)
    result['protected_before_verified'] = True
    try:
        result['write_started'] = True
        run_tool('write-app',['write_flash','--no-progress','--flash_mode','keep',
                             '--flash_freq','keep','--flash_size','keep',hex(target['offset']),str(image)])
        result['written'] = True
        run_tool('app-readback',['verify_flash','--diff','no',hex(target['offset']),str(image)])
        result['app_readback_verified'] = True
        run_tool('protected-after',protected,after='hard_reset')
        result['protected_after_verified'] = True
    finally:
        (ROOT/'evaluation/device-flash.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))


if __name__=='__main__':
    main()
