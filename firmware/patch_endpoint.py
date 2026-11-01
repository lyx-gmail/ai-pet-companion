"""Optional private LAN discovery, isolated from vendor WebSocket credentials."""
import ipaddress
import json
from urllib.parse import urlsplit


def render_header(url, usb_debug=False):
    if type(usb_debug) is not bool or (usb_debug and not url):
        raise ValueError('USB diagnostics require explicit local backend configuration')
    if not isinstance(url, str):
        raise ValueError('Local discovery URL must be a string')
    if url:
        if any(ord(c)<=32 for c in url):
            raise ValueError('Invalid local discovery URL')
        parsed = urlsplit(url)
        try:
            address = ipaddress.IPv4Address(parsed.hostname)
            valid = (parsed.scheme=='http' and parsed.port==8003
                     and parsed.path=='/xiaozhi/ota/' and not parsed.query
                     and not parsed.fragment and not parsed.username and not parsed.password
                     and any(address in ipaddress.IPv4Network(cidr)
                             for cidr in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')))
        except (ValueError, TypeError):
            valid = False
        if not valid:
            raise ValueError('Local discovery must use a private IPv4 address and port 8003')
    return ('#pragma once\n#include <atomic>\n// Generated locally; never contains a model API key.\n'
            '// Reset on every boot; retained RTC values alone are not trusted.\n'
            'inline std::atomic<bool> pet_utc_synced{false};\n'
            'inline constexpr char kPetLocalOtaUrl[] = '+json.dumps(url)+';\n'
            'inline constexpr bool kPetUsbDiagnostics = '+str(usb_debug).lower()+';\n')


def apply(source, replace, url='', usb_debug=False):
    header = render_header(url,usb_debug)
    path = source/'main/pet_endpoint.h'
    if not path.exists() or path.read_text(encoding='utf-8')!=header:
        path.write_text(header,encoding='utf-8',newline='\n')
    ota = source/'main/ota.cc'
    protocol = source/'main/protocols/websocket_protocol.cc'
    replace(ota, '#include "ota.h"', '#include "ota.h"\n#include "pet_endpoint.h"')
    replace(protocol, '#include "websocket_protocol.h"',
            '#include "websocket_protocol.h"\n#include "pet_endpoint.h"')
    replace(ota, 'std::string Ota::GetCheckVersionUrl() {',
            'std::string Ota::GetCheckVersionUrl() {\n    if (kPetLocalOtaUrl[0]) return kPetLocalOtaUrl;')
    # UNIX time is UTC. The local pet's saved anchors must not change when a
    # server timezone/display preference changes. Keep the vendor-mode branch.
    replace(ota, '            if (cJSON_IsNumber(timezone_offset)) {',
            '            if (cJSON_IsNumber(timezone_offset) && !kPetLocalOtaUrl[0]) {')
    replace(ota, '        if (cJSON_IsNumber(timestamp)) {',
            '        if (cJSON_IsNumber(timestamp) && timestamp->valuedouble >= 1704067200000.0\n'
            '            && timestamp->valuedouble <= 4102444800000.0) {')
    replace(ota, '            settimeofday(&tv, NULL);\n            has_server_time_ = true;',
            '            has_server_time_ = settimeofday(&tv, NULL) == 0;\n'
            '            if (has_server_time_ && kPetLocalOtaUrl[0]) pet_utc_synced.store(true);')
    replace(ota, 'Settings settings("websocket", true);',
            'Settings settings(kPetLocalOtaUrl[0] ? "pet_ws" : "websocket", true);')
    replace(protocol, 'Settings settings("websocket", false);',
            'Settings settings(kPetLocalOtaUrl[0] ? "pet_ws" : "websocket", false);')
