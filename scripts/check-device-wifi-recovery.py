"""Real device radio pause, care and recovery. Changes care state; never erases Wi-Fi credentials.

Uses the explicitly enabled development USB interface and its 20-second auto-restore.
Raw logs stay private. This is software radio fault injection, not an AP outage or acoustic test.
"""
import json
from pathlib import Path
import re
import time

ROOT=Path(__file__).resolve().parents[1]


def main():
    import serial
    from device_command import analyze
    build=json.loads((ROOT/'evaluation/firmware-build.json').read_text(encoding='utf-8'))
    flash=json.loads((ROOT/'evaluation/device-flash.json').read_text(encoding='utf-8'))
    if not flash.get('app_readback_verified') or flash['app_sha256']!=build['app_sha256']:
        raise ValueError('CURRENT_VERIFIED_IMAGE_REQUIRED')
    folder=ROOT/'.runtime/wifi-recovery';folder.mkdir(parents=True,exist_ok=True)
    result=dict(ok=False,source='physical_USB_development_radio_stop_then_start',
        app_sha256=build['app_sha256'],physical_AP_outage=False,
        physical_switch_contact_verified=False,visual_or_acoustic_acceptance=False)
    port=serial.Serial(port=None,baudrate=115200,timeout=.05,write_timeout=2)
    port.dtr=False;port.rts=False;port.port='COM4';raw=bytearray();paused=None

    def drain(seconds):
        end=time.monotonic()+seconds
        while time.monotonic()<end:raw.extend(port.read(min(max(port.in_waiting,1),4096)))

    def send(command):port.write(('pet.'+command+'\n').encode('ascii'));port.flush()

    def ensure_no_crash():
        if re.search(rb'Guru Meditation|abort\(\) was called|ESP_ERROR_CHECK failed|Stack overflow|Task watchdog got triggered|assert failed:|ESP-ROM:',raw,re.I):
            raise ValueError('DEVICE_CRASH_OR_REBOOT_OBSERVED')

    def wait_for(marker,offset,seconds):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            drain(.05)
            ensure_no_crash()
            if marker in raw[offset:]:return True
        return False

    def state():
        offset=len(raw);send('state');drain(1.5)
        ensure_no_crash()
        response=analyze('state',raw[offset:].decode('utf-8',errors='replace'))
        if not response['ok']:raise ValueError('STATE_UNAVAILABLE')
        return response['state']

    try:
        port.open();port.reset_input_buffer();before=state();result['before']=before
        if (not before.get('wifi_connected') or before['sleeping'] or before['pet_cooldown_seconds']
                or before['memory_admin_phase']):
            raise ValueError('CARE_OR_NETWORK_PRECONDITION_NOT_MET')
        offset=len(raw);send('wifi_pause')
        if not wait_for(b'PetWifiFault: radio_stopped=0',offset,3):raise ValueError('RADIO_STOP_NOT_OBSERVED')
        paused=time.monotonic();offline=state();result['radio_off_state']=offline
        if offline['wifi_connected']:raise ValueError('DRIVER_STILL_CONNECTED')
        offset=len(raw);started=time.monotonic();send('main')
        connecting=wait_for(b'Application: STATE: connecting',offset,2)
        idle=wait_for(b'Application: STATE: idle',offset,max(.05,10-(time.monotonic()-started)))
        result['voice_wait_seconds']=round(time.monotonic()-started,3)
        if not connecting or not idle or result['voice_wait_seconds']>10:raise ValueError('VOICE_OFFLINE_DEADLINE_FAILED')
        send('pet');drain(3);petted=state();result['petted']=petted
        result['pet_was_eligible']=before['mood']<100
        if (petted['wifi_connected'] or petted['mood']!=min(100,before['mood']+8)
                or (result['pet_was_eligible'] and petted['persisted_revision']<=before['persisted_revision'])
                or (not result['pet_was_eligible'] and petted['pet_cooldown_seconds']!=0)):
            raise ValueError('RADIO_OFF_CARE_SAVE_FAILED')
        send('feed_hold');drain(.8);asleep=state();result['asleep']=asleep
        if not asleep['sleeping'] or asleep['wifi_connected']:raise ValueError('RADIO_OFF_SLEEP_FAILED')
        send('feed');drain(.8);awake=state();result['awake']=awake
        if (awake['sleeping'] or awake['wifi_connected'] or abs(awake['satiety']-petted['satiety'])>1
                or awake['persisted_revision']<=before['persisted_revision']
                or awake['feed_cooldown_seconds']>petted['feed_cooldown_seconds']):
            raise ValueError('RADIO_OFF_WAKE_OR_FEED_RULE_FAILED')
        if not wait_for(b'PetWifiFault: radio_restarted=0',offset,25):raise ValueError('RADIO_AUTO_RESTORE_FAILED')
        end=time.monotonic()+20
        while True:
            restored=state()
            if restored['wifi_connected']:break
            if time.monotonic()>=end:raise ValueError('WIFI_RECONNECT_FAILED')
            drain(.5)
        result['restored']=restored
        offset=len(raw);send('main')
        if not wait_for(b'Application: STATE: listening',offset,8):raise ValueError('VOICE_RECONNECT_FAILED')
        send('main')
        if not wait_for(b'Application: STATE: idle',offset,3):raise ValueError('VOICE_CANCEL_FAILED')
        text=raw.decode('utf-8',errors='replace')
        stopped=re.search(r'I \((\d+)\) PetWifiFault: radio_stopped=0',text)
        restarted=re.search(r'I \((\d+)\) PetWifiFault: radio_restarted=0',text)
        if not stopped or not restarted:raise ValueError('RADIO_TIMESTAMPS_MISSING')
        result['radio_paused_ms']=int(restarted[1])-int(stopped[1])
        if not 19500<=result['radio_paused_ms']<=22000:raise ValueError('RADIO_DURATION_MISMATCH')
        if re.search(r'Guru Meditation|Stack overflow|Task watchdog got triggered|assert failed:',text,re.I):
            raise ValueError('DEVICE_CRASH_OBSERVED')
        result.update(ok=True,radio_off_care_persisted=True,wake_did_not_feed=True,
            wifi_restored_without_reprovisioning=True,voice_reconnected_and_cancelled=True)
    except Exception as error:
        result['error_type']=type(error).__name__
        if re.fullmatch('[A-Z_0-9]+',str(error)):result['error_code']=str(error)
    finally:
        if port.is_open:
            if paused is not None:drain(max(0,22-(time.monotonic()-paused)))
            states=re.findall(rb'Application: STATE: (\w+)',raw)
            if states and states[-1]==b'listening':send('main');drain(1)
            port.close()
        (folder/'usb.log').write_bytes(raw)
        (ROOT/'evaluation/device-wifi-recovery-check.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:result[key] for key in ('ok','voice_wait_seconds','radio_paused_ms','error_code') if key in result}))
    return 0 if result['ok'] else 1


if __name__=='__main__':raise SystemExit(main())
