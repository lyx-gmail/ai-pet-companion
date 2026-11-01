"""Capture actual COM4 logs privately; publish only bounded numeric health evidence."""
import argparse
from datetime import date
import json
from pathlib import Path
import re
import time

ROOT = Path(__file__).resolve().parents[1]


def analyze(text):
    clean = re.sub(r'\x1b\[[0-9;]*m','',text)
    pattern = (r'PetRuntime: pet alive: rev=(\d+) sat=(\d+) mood=(\d+) energy=(\d+) '
               r'closeness=(\d+) sleep=([01]) pending=([01]) storage=([01])')
    names = ('revision','satiety','mood','energy','closeness','sleeping','sleep_pending','storage_available')
    samples = [dict(zip(names,map(int,match.groups()))) for match in re.finditer(pattern,clean)]
    crash = bool(re.search(r'Guru Meditation Error|abort\(\) was called|assert failed:|Stack overflow|Task watchdog got triggered',clean,re.I))
    storage = bool(samples) and all(item['storage_available']==1 for item in samples)
    progressing = len(samples)>=2 and samples[-1]['revision']>samples[0]['revision']
    return {'date':date.today().isoformat(),'source':'physical_COM4_serial',
            'observed_pet_runtime':bool(samples),'health_samples':samples[:6],
            'state_ticks_progressing':progressing,'storage_available':storage,
            'crash_observed':crash,'hardware_animation_verified':False,
            'hardware_audio_verified':False,'ok':bool(samples) and storage and progressing and not crash}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds',type=int,default=30)
    args = parser.parse_args()
    if not 20<=args.seconds<=50:
        parser.error('Capture 20..50 seconds')
    import serial
    raw = bytearray()
    started = time.monotonic()
    reader = None
    reconnects = 0
    try:
        while time.monotonic()-started<args.seconds:
            try:
                if reader is None:
                    reader = serial.Serial(port=None,baudrate=115200,timeout=0.2)
                    reader.dtr = False
                    reader.rts = False
                    reader.port = 'COM4'
                    reader.open()
                raw.extend(reader.read(min(max(reader.in_waiting,1),4096)))
            except serial.SerialException:
                if reader is not None:
                    reader.close()
                    reader = None
                reconnects += 1
                time.sleep(0.1)
    finally:
        if reader is not None:
            reader.close()
    private = ROOT/'.runtime/flash'
    private.mkdir(parents=True,exist_ok=True)
    (private/'pet-boot-serial.log').write_bytes(raw)
    result = analyze(raw.decode('utf-8',errors='replace'))
    result.update(capture_seconds=args.seconds,serial_reconnects=reconnects)
    (ROOT/'evaluation/device-boot-check.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))
    return 0 if result['ok'] else 1


if __name__=='__main__':
    raise SystemExit(main())
