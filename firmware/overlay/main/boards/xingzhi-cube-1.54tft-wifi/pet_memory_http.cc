#include "pet_memory_http.h"
#include "pet_endpoint.h"
#include "board.h"
#include "settings.h"
#include "system_info.h"
#include <esp_http_client.h>

PetMemoryHttpReply PetMemoryHttpPost(const std::string& body) {
    PetMemoryHttpReply reply;
    std::string url=kPetLocalOtaUrl;
    const std::string suffix="/xiaozhi/ota/";
    if (url.rfind("http://",0)!=0 || url.size()<=suffix.size() ||
        url.compare(url.size()-suffix.size(),suffix.size(),suffix)!=0 || body.size()>1024) return reply;
    url.replace(url.size()-suffix.size(),suffix.size(),"/pet/memory");
    Settings settings("pet_ws",false);
    auto token=settings.GetString("token");
    if (token.empty() || token.size()>2048 || token.find_first_of("\r\n")!=std::string::npos) return reply;
    if (token.find(' ')==std::string::npos) token="Bearer "+token;
    if (token.rfind("Bearer ",0)!=0) return reply;
    esp_http_client_config_t config{};
    config.url=url.c_str();config.method=HTTP_METHOD_POST;config.timeout_ms=3000;
    config.disable_auto_redirect=true;config.keep_alive_enable=false;
    auto client=esp_http_client_init(&config);
    if (!client) return reply;
    esp_http_client_set_header(client,"Content-Type","application/json");
    esp_http_client_set_header(client,"Authorization",token.c_str());
    esp_http_client_set_header(client,"Device-Id",SystemInfo::GetMacAddress().c_str());
    esp_http_client_set_header(client,"Client-Id",Board::GetInstance().GetUuid().c_str());
    bool ok=esp_http_client_open(client,body.size())==ESP_OK;
    size_t written=0;
    while (ok && written<body.size()) {
        const int count=esp_http_client_write(client,body.data()+written,body.size()-written);
        if (count<=0) ok=false;
        else written+=count;
    }
    if (ok) {
        const auto length=esp_http_client_fetch_headers(client);
        if (length<0 || length>8192) ok=false;
    }
    char buffer[512];
    while (ok) {
        const int count=esp_http_client_read(client,buffer,sizeof(buffer));
        if (count<0 || reply.body.size()+count>8192) { ok=false;break; }
        if (!count) { ok=esp_http_client_is_complete_data_received(client);break; }
        reply.body.append(buffer,count);
    }
    if (ok) reply.status=esp_http_client_get_status_code(client);
    else reply.body.clear();
    esp_http_client_close(client);esp_http_client_cleanup(client);
    return reply;
}
