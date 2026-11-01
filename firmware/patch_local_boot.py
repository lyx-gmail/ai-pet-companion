"""Local pet boot never waits for a PC service or enters vendor activation."""


def apply(source,replace):
    app=source/'main/application.cc'
    replace(app,'#include "application.h"',
        '#include "application.h"\n#include "pet_endpoint.h"')
    replace(app,'void Application::CheckNewVersion(Ota& ota) {',
        '''void Application::CheckNewVersion(Ota& ota) {
    if (kPetLocalOtaUrl[0]) {
        ota.MarkCurrentVersionValid();
        xEventGroupSetBits(event_group_, MAIN_EVENT_CHECK_NEW_VERSION_DONE);
        ESP_LOGI(TAG, "Pet local boot: activation wait skipped");
        return;
    }''')
    replace(app,'    if (ota.HasMqttConfig()) {',
        '''    if (kPetLocalOtaUrl[0]) {
        protocol_ = std::make_unique<WebsocketProtocol>();
    } else if (ota.HasMqttConfig()) {''')
    replace(app,'    has_server_time_ = ota.HasServerTime();',
        '''    has_server_time_ = ota.HasServerTime();
    if (kPetLocalOtaUrl[0]) {
        // The pet is already idle: PC availability cannot hold up its face/keys.
        const auto created = xTaskCreate([](void* context) {
            auto* app = static_cast<Application*>(context);
            Ota discovery;
            const bool synced = discovery.CheckVersion() && discovery.HasServerTime();
            app->Schedule([app, synced]() { app->has_server_time_ = synced; });
            vTaskDelete(nullptr);
        }, "pet_discovery", 8192, this, 1, nullptr);
        if (created != pdPASS) ESP_LOGW(TAG, "Pet discovery deferred until voice request");
    }''')
    ota=source/'main/ota.cc'
    text=ota.read_text(encoding='utf-8')
    text=text.replace('    if (kPetLocalOtaUrl[0]) pet_discovery_lock.lock();',
        '    if (kPetLocalOtaUrl[0] && !pet_discovery_lock.try_lock()) return false;')
    text=text.replace('int64_t deadline; } response', 'int64_t deadline; bool rejected = false; } response')
    text=text.replace('if (esp_timer_get_time() > response->deadline) return ESP_FAIL;',
        'if (esp_timer_get_time() > response->deadline) response->rejected = true;')
    text=text.replace('if (event->data_len < 0 || response->body.size() + event->data_len > 32768) return ESP_FAIL;',
        'if (event->data_len < 0 || response->body.size() + event->data_len > 32768) response->rejected = true;\n                if (response->rejected) return ESP_FAIL;')
    text=text.replace('status != 200 || esp_timer_get_time() > response.deadline',
        'status != 200 || response.rejected || esp_timer_get_time() > response.deadline')
    if '#include <esp_http_client.h>' not in text:
        text=text.replace('#include <mutex>\n#include "ota.h"', '#include "ota.h"')
    ota.write_text(text,encoding='utf-8',newline='\n')
    replace(ota,'#include "ota.h"', '#include <mutex>\n#include <esp_http_client.h>\n#include <esp_timer.h>\n#include "ota.h"')
    replace(ota,'bool Ota::CheckVersion() {',
        '''bool Ota::CheckVersion() {
    // Boot refresh and a user voice request may overlap. Keep NVS credentials
    // and the existing HTTP channel consistent, without locking the UI thread.
    static std::mutex pet_discovery_mutex;
    std::unique_lock<std::mutex> pet_discovery_lock(pet_discovery_mutex, std::defer_lock);
    if (kPetLocalOtaUrl[0] && !pet_discovery_lock.try_lock()) return false;''')
    # The upstream Http timeout covers response reads, not EspTcp::connect().
    # Use IDF's bounded transport for private numeric-IP discovery only.
    replace(ota, '''    auto http = SetupHttp();

    std::string data = board.GetSystemInfoJson();
    std::string method = data.length() > 0 ? "POST" : "GET";
    http->SetContent(std::move(data));

    if (!http->Open(method, url)) {
        ESP_LOGE(TAG, "Failed to open HTTP connection");
        return false;
    }

    auto status_code = http->GetStatusCode();
    if (status_code != 200) {
        ESP_LOGE(TAG, "Failed to check version, status code: %d", status_code);
        return false;
    }

    data = http->ReadAll();
    http->Close();''', '''    std::string data = board.GetSystemInfoJson();
    if (kPetLocalOtaUrl[0]) {
        struct Response { std::string body; int64_t deadline; bool rejected = false; } response{{}, esp_timer_get_time() + 3000000};
        esp_http_client_config_t config{};
        config.url = url.c_str();
        config.timeout_ms = 2000;
        config.disable_auto_redirect = true;
        config.user_data = &response;
        config.event_handler = [](esp_http_client_event_t* event) -> esp_err_t {
            auto* response = static_cast<Response*>(event->user_data);
            if (esp_timer_get_time() > response->deadline) response->rejected = true;
            if (event->event_id == HTTP_EVENT_ON_DATA) {
                if (event->data_len < 0 || response->body.size() + event->data_len > 32768) response->rejected = true;
                if (response->rejected) return ESP_FAIL;
                response->body.append(static_cast<const char*>(event->data), event->data_len);
            }
            return ESP_OK;
        };
        auto client = esp_http_client_init(&config);
        if (!client) return false;
        esp_http_client_set_method(client, data.empty() ? HTTP_METHOD_GET : HTTP_METHOD_POST);
        const auto device = SystemInfo::GetMacAddress();
        const auto uuid = board.GetUuid();
        esp_http_client_set_header(client, "Device-Id", device.c_str());
        esp_http_client_set_header(client, "Client-Id", uuid.c_str());
        esp_http_client_set_header(client, "Content-Type", "application/json");
        esp_http_client_set_post_field(client, data.data(), data.size());
        const auto error = esp_http_client_perform(client);
        const int status = esp_http_client_get_status_code(client);
        esp_http_client_cleanup(client);
        if (error != ESP_OK || status != 200 || response.rejected || esp_timer_get_time() > response.deadline) {
            ESP_LOGW(TAG, "Pet discovery unavailable: error=%d status=%d", error, status);
            return false;
        }
        data = std::move(response.body);
    } else {
        auto http = SetupHttp();
        std::string method = data.length() > 0 ? "POST" : "GET";
        http->SetContent(std::move(data));
        if (!http->Open(method, url)) return false;
        if (http->GetStatusCode() != 200) return false;
        data = http->ReadAll();
        http->Close();
    }''')
    replace(ota,'    auto http = network->CreateHttp(0);\n    auto user_agent = SystemInfo::GetUserAgent();',
        '    auto http = network->CreateHttp(0);\n    if (kPetLocalOtaUrl[0]) http->SetTimeout(3000);\n    auto user_agent = SystemInfo::GetUserAgent();')
    websocket=source/'main/protocols/websocket_protocol.cc'
    text=websocket.read_text(encoding='utf-8')
    text=text.replace('#include "ota.h"\n','')
    websocket.write_text(text,encoding='utf-8',newline='\n')
    replace(websocket,'#include "websocket_protocol.h"',
        '#include "ota.h"\n#include "websocket_protocol.h"')
    replace(websocket,'bool WebsocketProtocol::OpenAudioChannel() {',
        '''bool WebsocketProtocol::OpenAudioChannel() {
    if (kPetLocalOtaUrl[0]) {
        Ota discovery;
        if (!discovery.CheckVersion()) {
            SetError("电脑语音服务暂不可用，请在控制面板连接后重试");
            return false;
        }
    }''')
