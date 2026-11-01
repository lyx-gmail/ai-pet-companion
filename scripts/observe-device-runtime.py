"""Bounded 2h serial observation; optional radio fault check, not full SOAK01 acceptance."""
import json
import argparse
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
DURATION=7200


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--include-wifi-probe',action='store_true',
        help='First run the real 20-second radio fault/care/reconnect check within the observation window')
    args=parser.parse_args()
    import serial
    from device_boot import analyze
    build=json.loads((ROOT/'evaluation/firmware-build.json').read_text(encoding='utf-8'))
    flash=json.loads((ROOT/'evaluation/device-flash.json').read_text(encoding='utf-8'))
    if not flash.get('app_readback_verified') or build['app_sha256']!=flash['app_sha256']:
        raise ValueError('CURRENT_VERIFIED_IMAGE_REQUIRED')
    folder=ROOT/'.runtime/runtime-observation';folder.mkdir(parents=True,exist_ok=True)
    result={'ok':False,'app_sha256':build['app_sha256'],'requested_seconds':DURATION,
        'source':'physical_COM4_continuous_read_only_observation','full_SOAK01_verified':False,
        'wifi_interruption_tested':False,'physical_controls_tested':False,
        'acoustic_quality_verified':False}
    port=serial.Serial(port=None,baudrate=115200,timeout=.2)
    port.dtr=False;port.rts=False;port.port='COM4'
    raw=bytearray();started=time.monotonic();last_progress=0
    (folder/'progress.json').write_text(json.dumps({'elapsed_seconds':0,
        'app_sha256':build['app_sha256'],'phase':'starting'}),encoding='utf-8')
    try:
        if args.include_wifi_probe:
            print(json.dumps({'started':True,'phase':'radio_fault_probe','app_sha256':build['app_sha256']}),flush=True)
            with (folder/'wifi-probe-process.log').open('wb') as log:
                checked=subprocess.run([sys.executable,str(ROOT/'scripts/check-device-wifi-recovery.py')],
                    cwd=ROOT,stdout=log,stderr=log,timeout=65)
            probe=json.loads((ROOT/'evaluation/device-wifi-recovery-check.json').read_text(encoding='utf-8'))
            if checked.returncode or not probe.get('ok') or probe['app_sha256']!=build['app_sha256']:
                raise ValueError('WIFI_PROBE_FAILED')
            raw.extend((ROOT/'.runtime/wifi-recovery/usb.log').read_bytes())
            result['wifi_interruption_tested']=True
            result['wifi_fault_source']='development_radio_stop_start_not_physical_AP_outage'
            result['wifi_probe_evidence']='evaluation/device-wifi-recovery-check.json'
            result['settings_operability_verified']=False
        port.open();port.reset_input_buffer()
        print(json.dumps({'started':True,'seconds':DURATION,'app_sha256':build['app_sha256']}),flush=True)
        while time.monotonic()-started<DURATION:
            raw.extend(port.read(min(max(port.in_waiting,1),4096)))
            if len(raw)>8*1024*1024:raise ValueError('CAPTURE_LIMIT_EXCEEDED')
            elapsed=time.monotonic()-started
            if elapsed-last_progress>=60:
                (folder/'progress.json').write_text(json.dumps({'elapsed_seconds':int(elapsed),
                    'bytes':len(raw),'app_sha256':build['app_sha256']}),encoding='utf-8')
                last_progress=elapsed
        text=raw.decode('utf-8',errors='replace');health=analyze(text)
        samples=re.findall(r'PetRuntime: pet alive: rev=(\d+)',text)
        heap=[int(value) for value in re.findall(r'free sram: (\d+)',text)]
        reboot=bool(re.search(r'ESP-ROM:|rst:0x|Application: STATE: starting',text))
        result.update(elapsed_seconds=round(time.monotonic()-started,2),health=health,
            health_sample_count=len(samples),unexpected_boot_observed=reboot,
            minimum_observed_free_sram=min(heap) if heap else None,
            first_observed_free_sram=heap[0] if heap else None,
            last_observed_free_sram=heap[-1] if heap else None)
        result['ok']=health['ok'] and not reboot and len(samples)>=600
    except Exception as error:
        result['error_type']=type(error).__name__
        if re.fullmatch('[A-Z_]+',str(error)):result['error_code']=str(error)
        result['elapsed_seconds']=round(time.monotonic()-started,2)
    finally:
        port.close();(folder/'usb.log').write_bytes(raw)
        (ROOT/'evaluation/device-runtime-observation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'ok':result['ok'],'elapsed_seconds':result['elapsed_seconds'],
        'full_SOAK01_verified':False}),flush=True)
    return 0 if result['ok'] else 1


if __name__=='__main__':raise SystemExit(main())
