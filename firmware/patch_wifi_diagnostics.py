"""Nonfatal Wi-Fi status snapshots and optional numeric disconnect telemetry."""

def apply(source,replace):
    board=source/'main/boards/common/wifi_board.cc'
    replace(board,'#include "wifi_board.h"',
        '#include "wifi_board.h"\n#include "pet_endpoint.h"\n#include <esp_event.h>\n#include <esp_wifi.h>')
    # WifiStation's RSSI/channel helpers abort if the link drops between reads.
    # Take one nonfatal driver snapshot in each shared status path instead.
    replace(board,'''    auto& wifi_station = WifiStation::GetInstance();
    if (!wifi_station.IsConnected()) {
        return FONT_AWESOME_WIFI_SLASH;
    }
    int8_t rssi = wifi_station.GetRssi();''', '''    wifi_ap_record_t ap{};
    if (esp_wifi_sta_get_ap_info(&ap)!=ESP_OK) return FONT_AWESOME_WIFI_SLASH;
    int8_t rssi = ap.rssi;''')
    replace(board,'''    if (!wifi_config_mode_) {
        board_json += R"("ssid":")" + wifi_station.GetSsid() + R"(",)";
        board_json += R"("rssi":)" + std::to_string(wifi_station.GetRssi()) + R"(,)";
        board_json += R"("channel":)" + std::to_string(wifi_station.GetChannel()) + R"(,)";
        board_json += R"("ip":")" + wifi_station.GetIpAddress() + R"(",)";
    }''', '''    wifi_ap_record_t ap{};
    const bool connected=!wifi_config_mode_ && esp_wifi_sta_get_ap_info(&ap)==ESP_OK;
    board_json += connected ? R"("connected":true,)" : R"("connected":false,)";
    if (connected) {
        board_json += R"("ssid":")" + wifi_station.GetSsid() + R"(",)";
        board_json += R"("rssi":)" + std::to_string(ap.rssi) + R"(,)";
        board_json += R"("channel":)" + std::to_string(ap.primary) + R"(,)";
        board_json += R"("ip":")" + wifi_station.GetIpAddress() + R"(",)";
    }''')
    replace(board,'''    int rssi = wifi_station.GetRssi();
    if (rssi >= -60) {''', '''    wifi_ap_record_t ap{};
    const bool connected=esp_wifi_sta_get_ap_info(&ap)==ESP_OK;
    cJSON_AddBoolToObject(network, "connected", connected);
    int rssi = ap.rssi;
    if (!connected) {
        cJSON_AddStringToObject(network, "signal", "disconnected");
    } else if (rssi >= -60) {''')
    anchor='    wifi_station.OnScanBegin([this]() {'
    replace(board,anchor,anchor+'''
        if constexpr (kPetUsbDiagnostics) {
            // STA_START has created the event loop before this callback.
            static bool pet_wifi_diag_registered = false;
            if (!pet_wifi_diag_registered) {
                const auto error = esp_event_handler_register(WIFI_EVENT, WIFI_EVENT_STA_DISCONNECTED,
                    [](void*, esp_event_base_t, int32_t, void* data) {
                        const auto* event = static_cast<const wifi_event_sta_disconnected_t*>(data);
                        if (event) ESP_LOGW("PetWifiDiag", "disconnect_reason=%u", unsigned(event->reason));
                    }, nullptr);
                pet_wifi_diag_registered = error == ESP_OK;
                if (error != ESP_OK) ESP_LOGW("PetWifiDiag", "attach_error=%d", int(error));
            }
        }''')
