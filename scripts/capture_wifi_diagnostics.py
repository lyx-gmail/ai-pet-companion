"""Capture private USB logs; export numeric Wi-Fi evidence without credentials."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import time

ROOT = Path(__file__).resolve().parents[1]


def analyze(text):
    text = re.sub(r'\x1b\[[0-9;]*m', '', text)
    reasons = [int(value) for value in re.findall(
        r'PetWifiDiag: disconnect_reason=(\d+)\b', text) if 0 <= int(value) <= 255]
    return {
        'disconnect_reasons': reasons,
        'diagnostic_observed': bool(reasons),
        'station_got_ip': bool(re.search(
            r'^I (?:\(\d+\) )?WifiStation: Got IP: \d{1,3}(?:\.\d{1,3}){3}\s*$',
            text, re.M)),
        'observer_attach_failed': bool(re.search(r'PetWifiDiag: attach_error=-?\d+', text)),
        'crash_observed': bool(re.search(
            r'Guru Meditation Error|abort\(\) was called|assert failed:|Stack overflow|Task watchdog got triggered',
            text, re.I)),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=int, choices=range(20, 61), default=40)
    args = parser.parse_args()
    flash = json.loads((ROOT/'evaluation/device-flash.json').read_text(encoding='utf-8-sig'))
    if not all(flash.get(key) is True for key in
               ('written', 'app_readback_verified', 'protected_after_verified')):
        raise SystemExit('A verified app flash is required before this capture.')
    import serial
    reader = serial.Serial(port=None, baudrate=115200, timeout=0.2)
    reader.dtr = False
    reader.rts = False
    reader.port = 'COM4'
    raw = bytearray()
    try:
        reader.open()
        started = time.monotonic()
        while time.monotonic()-started < args.seconds:
            raw.extend(reader.read(min(max(reader.in_waiting, 1), 4096)))
    finally:
        reader.close()
    private = ROOT/'.runtime/flash'
    private.mkdir(parents=True, exist_ok=True)
    (private/'wifi-diagnostics-serial.log').write_bytes(raw)
    result = analyze(raw.decode('utf-8', errors='replace'))
    result.update(source='physical_COM4_serial', capture_seconds=args.seconds,
                  captured_at=datetime.now(timezone.utc).isoformat(),
                  app_sha256=flash['app_sha256'])
    (ROOT/'evaluation/wifi-diagnostics-check.json').write_text(
        json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result))
    return 0 if (result['diagnostic_observed'] or result['station_got_ip']) and not result['crash_observed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
