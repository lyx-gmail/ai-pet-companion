"""Inspect the actual prepared startup path, including offline and retry boundaries."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'.tools/upstream/xiaozhi-esp32/main'


class LocalBootChecks(unittest.TestCase):
    def test_local_boot_returns_before_remote_activation_loop(self):
        app=(SOURCE/'application.cc').read_text(encoding='utf-8')
        self.assertIn('#include "pet_endpoint.h"',app)
        method=app[app.index('void Application::CheckNewVersion('):app.index('void Application::ShowActivationCode(')]
        early=method[:method.index('const int MAX_RETRY')]
        self.assertIn('if (kPetLocalOtaUrl[0])',early)
        self.assertIn('ota.MarkCurrentVersionValid();',early)
        self.assertIn('MAIN_EVENT_CHECK_NEW_VERSION_DONE',early)
        self.assertIn('return;',early)
        self.assertNotIn('CheckVersion()',early)
        self.assertNotIn('Activate()',early)

    def test_local_protocol_and_background_discovery_are_separate_from_ui(self):
        app=(SOURCE/'application.cc').read_text(encoding='utf-8')
        start=app[app.index('void Application::Start()'):app.index('// Add a async task')]
        self.assertIn('if (kPetLocalOtaUrl[0]) {\n        protocol_ = std::make_unique<WebsocketProtocol>();',start)
        self.assertGreater(start.index('"pet_discovery"'),start.index('SetDeviceState(kDeviceStateIdle);'))
        protocol=(SOURCE/'protocols/websocket_protocol.cc').read_text(encoding='utf-8')
        method=protocol[protocol.index('bool WebsocketProtocol::OpenAudioChannel()'):]
        self.assertLess(method.index('discovery.CheckVersion()'),method.index('Settings settings('))
        ota=(SOURCE/'ota.cc').read_text(encoding='utf-8')
        self.assertIn('if (kPetLocalOtaUrl[0]) http->SetTimeout(3000);',ota)
        self.assertIn('pet_discovery_lock.try_lock()',ota)
        self.assertIn('config.timeout_ms = 2000;',ota)
        self.assertIn('esp_http_client_perform(client)',ota)
        self.assertIn('config.disable_auto_redirect = true;',ota)


if __name__=='__main__':unittest.main()
