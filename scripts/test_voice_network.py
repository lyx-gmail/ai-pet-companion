import unittest
from unittest.mock import patch

from voice_network import device_allowed, network_config


class VoiceNetworkTests(unittest.TestCase):
    def test_discovery_and_websocket_require_bound_device_without_auth_bypass(self):
        config = {'server': {'auth': {'enabled': True, 'allowed_devices': []}},
                  'Memory': {'PetMemory': {'expected_device_id': 'aa:bb:cc:dd:ee:02'}}}
        self.assertTrue(device_allowed({'Device-ID':'AA:BB:CC:DD:EE:02', 'Client-ID':'fixture'}, config))
        for headers in ({}, {'device-id':'aa:bb:cc:dd:ee:03','client-id':'fixture'},
                        {'device-id':'aa:bb:cc:dd:ee:02'},
                        {'device-id':'aa:bb:cc:dd:ee:02','client-id':' '}):
            self.assertFalse(device_allowed(headers, config))
        config['server']['auth']['allowed_devices'] = ['aa:bb:cc:dd:ee:02']
        self.assertFalse(device_allowed({'device-id':'aa:bb:cc:dd:ee:02','client-id':'fixture'}, config))
        config['server']['auth']['allowed_devices'] = []
        config['server']['auth']['enabled'] = False
        self.assertFalse(device_allowed({'device-id':'aa:bb:cc:dd:ee:02','client-id':'fixture'}, config))

    def test_default_stays_loopback(self):
        result = network_config()
        self.assertEqual(result['ip'], '127.0.0.1')
        self.assertEqual(result['websocket'], 'ws://127.0.0.1:8000/xiaozhi/v1/')
        self.assertEqual(result['expected_device_id'], '')

    def test_lan_requires_bound_local_address_and_device(self):
        with patch('voice_network.socket.socket') as factory:
            result = network_config('192.168.31.84', 'AA:BB:CC:DD:EE:02')
            factory.return_value.__enter__.return_value.bind.assert_called_once_with(('192.168.31.84', 0))
        self.assertEqual(result['expected_device_id'], 'aa:bb:cc:dd:ee:02')
        self.assertEqual(result['websocket'], 'ws://192.168.31.84:8000/xiaozhi/v1/')
        for address, device in [('0.0.0.0','aa:bb:cc:dd:ee:02'),
                                ('198.18.0.1','aa:bb:cc:dd:ee:02'),
                                ('8.8.8.8','aa:bb:cc:dd:ee:02'),
                                ('192.168.31.84',''),
                                ('192.168.31.84','not-a-device'),
                                ('::1','aa:bb:cc:dd:ee:02')]:
            with self.subTest(address=address, device=device), self.assertRaises(ValueError):
                network_config(address, device)

    def test_nonlocal_lan_is_rejected_without_leaking_os_error(self):
        with patch('voice_network.socket.socket') as factory:
            factory.return_value.__enter__.return_value.bind.side_effect = OSError('private host detail')
            with self.assertRaisesRegex(ValueError, '^Bind address is not available locally$'):
                network_config('192.168.31.200', 'aa:bb:cc:dd:ee:02')


if __name__ == '__main__':
    unittest.main()
