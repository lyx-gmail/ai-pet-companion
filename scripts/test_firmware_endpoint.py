import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('patch_endpoint', Path(__file__).resolve().parents[1]/'firmware/patch_endpoint.py')
endpoint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(endpoint)


class FirmwareEndpointTests(unittest.TestCase):
    def test_usb_diagnostics_default_off_and_requires_explicit_local_backend(self):
        self.assertIn('kPetUsbDiagnostics = false;', endpoint.render_header(''))
        self.assertIn('kPetUsbDiagnostics = true;', endpoint.render_header('http://192.168.31.84:8003/xiaozhi/ota/', True))
        for url, flag in (('', True), ('http://192.168.31.84:8003/xiaozhi/ota/', 'true')):
            with self.assertRaises(ValueError): endpoint.render_header(url, flag)

    def test_empty_keeps_vendor_default_and_lan_url_is_escaped(self):
        self.assertIn('kPetLocalOtaUrl[] = "";', endpoint.render_header(''))
        self.assertIn('http://192.168.31.84:8003/xiaozhi/ota/',
                      endpoint.render_header('http://192.168.31.84:8003/xiaozhi/ota/'))

    def test_rejects_ambiguous_or_non_lan_discovery(self):
        for url in (None, False, 0, [], 'http://127.0.0.1:8003/xiaozhi/ota/',
                    'http://198.18.0.1:8003/xiaozhi/ota/',
                    'http://0.0.0.0:8003/xiaozhi/ota/',
                    'http://example.com:8003/xiaozhi/ota/',
                    'http://192.168.31.84:8003/other/',
                    'http://user:pass@192.168.31.84:8003/xiaozhi/ota/',
                    'http://192.168.31.84:8003/xiaozhi/ota/?token=secret',
                    'http://192.168.31.84:8003/xiaozhi/ota/#fragment',
                    'http://192.168.31.84:8003/xiaozhi/ota/\n'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                endpoint.render_header(url)


if __name__ == '__main__':
    unittest.main()
