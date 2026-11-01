"""Apply this project's target-specific overlay to the pinned upstream checkout."""
from pathlib import Path
import shutil
import subprocess
import re
import json
from patch_application import apply as patch_application
from patch_pet_tools import apply as patch_pet_tools
from patch_pet_sleep import apply as patch_pet_sleep
from patch_pet_conversation import apply as patch_pet_conversation
from patch_assets import apply as patch_assets
from patch_endpoint import apply as patch_endpoint
from patch_wifi_diagnostics import apply as patch_wifi_diagnostics
from patch_local_boot import apply as patch_local_boot

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / '.tools/upstream/xiaozhi-esp32'
PIN = '43ef2f4e7f0957dc62ec7d628ac2819d226127b8'


def replace_once(path, old, new):
    text = path.read_text(encoding='utf-8')
    if new in text:
        return
    if text.count(old) != 1:
        raise RuntimeError('PATCH_CONTEXT_CHANGED: ' + str(path.relative_to(SOURCE)))
    path.write_text(text.replace(old, new, 1), encoding='utf-8', newline='\n')


def main():
    head = subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip()
    if head != PIN:
        raise RuntimeError('FIRMWARE_PIN_MISMATCH')
    manifest = SOURCE / 'main/idf_component.yml'
    # These engines are not used by the selected ST7789/LVGL board. The old
    # image_player release is unavailable; do not upgrade unrelated board drivers.
    for line in ['  espressif2022/image_player: ==1.1.0~1\n',
                 '  espressif2022/esp_emote_gfx: ^1.1.2\n',
                 '  txp666/otto-emoji-gif-component:\n    version: 1.0.2\n    rules:\n    - if: target not in [esp32c5]\n']:
        text = manifest.read_text(encoding='utf-8')
        if line in text:
            manifest.write_text(text.replace(line, ''), encoding='utf-8', newline='\n')
    cmake = SOURCE / 'main/CMakeLists.txt'
    text = cmake.read_text(encoding='utf-8')
    updated = text.replace('            "display/emote_display.cc"\n', '')
    if updated != text:
        cmake.write_text(updated, encoding='utf-8', newline='\n')
    locked = ROOT / 'firmware/locks/dependencies.lock'
    if locked.exists():
        destination = SOURCE / 'dependencies.lock'
        if not destination.exists() or destination.read_bytes() != locked.read_bytes():
            shutil.copyfile(locked, destination)
    # Defaults do not override an existing generated sdkconfig. Keep this
    # board's 40ms debounce identical in fresh and incremental configurations.
    config = SOURCE / 'sdkconfig'
    if config.exists():
        text = config.read_text(encoding='utf-8')
        updated = text
        for key,value in [('CONFIG_BUTTON_PERIOD_TIME_MS','10'),('CONFIG_BUTTON_DEBOUNCE_TICKS','4')]:
            updated = re.sub(rf'^{key}=.*$',f'{key}={value}',updated,flags=re.MULTILINE)
        if updated!=text:
            config.write_text(updated,encoding='utf-8',newline='\n')
    board = SOURCE / 'main/boards/xingzhi-cube-1.54tft-wifi/xingzhi-cube-1.54tft-wifi.cc'
    replace_once(board, '#include "display/lcd_display.h"', '#include "pet_display.h"')
    replace_once(board, 'display_ = new SpiLcdDisplay(', 'display_ = new PetDisplay(')
    replace_once(board, '#include "pet_display.h"', '#include "pet_display.h"\n#include "pet_runtime.h"')
    replace_once(board, '    SpiLcdDisplay* display_;', '    PetDisplay* display_;\n    PetRuntime pet_;')
    replace_once(board, 'new PowerSaveTimer(-1, 60, 300)', 'new PowerSaveTimer(-1, -1, -1)')
    # Original GPIO0/40/39 handles remain; physical button positions need checking.
    text = board.read_text(encoding='utf-8')
    start = text.index('    void InitializeButtons() {')
    end = text.index('    void InitializeSt7789Display()',start)
    buttons = '''    void InitializeButtons() {
        boot_button_.OnClick([this]() {
            Application::GetInstance().Schedule([this]() { power_save_timer_->WakeUp(); pet_.HandleKey(PetMenu::Key::Main,false); });
        });
        boot_button_.OnLongPress([this]() {
            Application::GetInstance().Schedule([this]() { power_save_timer_->WakeUp(); pet_.HandleKey(PetMenu::Key::Main,true); });
        });
        volume_up_button_.OnClick([this]() {
            Application::GetInstance().Schedule([this]() { power_save_timer_->WakeUp(); pet_.HandleKey(PetMenu::Key::Feed,false); });
        });
        volume_up_button_.OnLongPress([this]() {
            Application::GetInstance().Schedule([this]() { power_save_timer_->WakeUp(); pet_.HandleKey(PetMenu::Key::Feed,true); });
        });
        volume_down_button_.OnClick([this]() {
            Application::GetInstance().Schedule([this]() { power_save_timer_->WakeUp(); pet_.HandleKey(PetMenu::Key::Pet,false); });
        });
        volume_down_button_.OnLongPress([this]() {
            Application::GetInstance().Schedule([this]() { power_save_timer_->WakeUp(); pet_.HandleKey(PetMenu::Key::Pet,true); });
        });
    }

'''
    updated = text[:start]+buttons+text[end:]
    if updated!=text:
        board.write_text(updated,encoding='utf-8',newline='\n')
    replace_once(board,
                 '        InitializeButtons();\n        InitializeSt7789Display();\n        GetBacklight()->RestoreBrightness();',
                 '        InitializeSt7789Display();\n        GetBacklight()->RestoreBrightness();\n        pet_.Begin(display_);\n        InitializeButtons();')
    for name in ['BOOT_BUTTON_GPIO','VOLUME_UP_BUTTON_GPIO','VOLUME_DOWN_BUTTON_GPIO']:
        replace_once(board, f'button_({name})', f'button_({name}, false, 1500, 40)')
    # A failed NVS initialization must never erase Wi-Fi binding and pet data.
    replace_once(SOURCE / 'main/main.cc',
                 '''        ESP_LOGW(TAG, "Erasing NVS flash to fix corruption");
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();''',
                 '''        ESP_LOGE(TAG, "NVS unavailable: preserving data; connect serial for recovery");
        return;''')
    replace_once(SOURCE / 'main/application.cc',
                 '''        if (ota.HasNewVersion()) {
            if (UpgradeFirmware(ota)) {
                return; // This line will never be reached after reboot
            }
            // If upgrade failed, continue to normal operation (don't break, just fall through)
        }''',
                 '''        if (ota.HasNewVersion()) {
            // Keep server discovery/time/activation, but do not overwrite this
            // custom pet firmware with the vendor's automatic boot-time update.
            ESP_LOGW(TAG, "Pet firmware: automatic vendor upgrade skipped");
        }''')
    vendor = ROOT / 'firmware/vendor/RoboEyes'
    patch_application(SOURCE,replace_once)
    patch_pet_tools(SOURCE,replace_once)
    patch_pet_sleep(SOURCE,replace_once)
    patch_pet_conversation(SOURCE,replace_once)
    patch_assets(SOURCE,replace_once)
    endpoint_file = ROOT/'.runtime/device-endpoint.json'
    endpoint = json.loads(endpoint_file.read_text(encoding='utf-8')) if endpoint_file.exists() else {}
    patch_endpoint(SOURCE,replace_once,endpoint.get('ota_url',''),endpoint.get('usb_diagnostics',False))
    patch_wifi_diagnostics(SOURCE,replace_once)
    patch_local_boot(SOURCE,replace_once)
    destination = board.parent / 'FluxGarage_RoboEyes.h'
    if not destination.exists() or destination.read_bytes() != (vendor / 'FluxGarage_RoboEyes.h').read_bytes():
        shutil.copyfile(vendor / 'FluxGarage_RoboEyes.h', destination)
    for source in (ROOT / 'firmware/overlay').rglob('*'):
        if source.is_file():
            dest = SOURCE / source.relative_to(ROOT / 'firmware/overlay')
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists() or dest.read_bytes() != source.read_bytes():
                shutil.copyfile(source, dest)
    print('Prepared pinned firmware for xingzhi-cube-1.54tft-wifi only; no flashing performed.')


if __name__ == '__main__':
    main()
