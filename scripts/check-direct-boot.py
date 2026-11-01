"""Analyze the real offline-backend boot capture; never infer visual acceptance."""
import json
from pathlib import Path
import re
from device_boot import analyze as health

ROOT=Path(__file__).resolve().parents[1]


def analyze(text):
    text=re.sub(r'\x1b\[[0-9;]*m','',text)
    ip=re.search(r'I \((\d+)\) WifiStation: Got IP:',text)
    idle=re.search(r'I \((\d+)\) Application: STATE: idle',text)
    elapsed=int(idle[1])-int(ip[1]) if ip and idle else None
    result=health(text)
    result.update(local_activation_wait_skipped='Pet local boot: activation wait skipped' in text,
        activating_observed=bool(re.search(r'Application: STATE: activating\b',text)),
        idle_after_ip_ms=elapsed,
        blocking_retry_observed='Check new version failed, retry in' in text)
    result['ok']=bool(result['ok'] and result['local_activation_wait_skipped'] and
        not result['activating_observed'] and not result['blocking_retry_observed'] and
        elapsed is not None and 0<=elapsed<=10000)
    return result


if __name__=='__main__':
    flash=json.loads((ROOT/'evaluation/device-flash.json').read_text())
    result=analyze((ROOT/'.runtime/flash/pet-boot-serial.log').read_text(encoding='utf-8',errors='replace'))
    result['app_sha256']=flash['app_sha256']
    result['official_cloud_tested']=False
    (ROOT/'evaluation/direct-boot-check.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))
    raise SystemExit(0 if result['ok'] else 1)
