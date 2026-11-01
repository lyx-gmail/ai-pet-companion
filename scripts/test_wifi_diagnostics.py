import unittest
from capture_wifi_diagnostics import analyze

class WifiDiagnosticsChecks(unittest.TestCase):
    def test_numeric_only_and_no_false_recovery(self):
        sample='W (100) PetWifiDiag: disconnect_reason=4\nW (200) PetWifiDiag: disconnect_reason=4\nW (300) PetWifiDiag: disconnect_reason=204\nI WifiStation: Found AP: secret-network, BSSID: private-address, password: sk-private\nSTATE: configuring'
        result=analyze(sample)
        self.assertEqual(result['disconnect_reasons'],[4,4,204])
        self.assertFalse(result['station_got_ip'])
        self.assertTrue(result['diagnostic_observed'])
        self.assertNotIn('secret',str(result));self.assertNotIn('private',str(result))
        self.assertFalse(analyze('PetWifiDiag: disconnect_reason=999')['diagnostic_observed'])
        self.assertTrue(analyze('I (400) WifiStation: Got IP: 192.168.1.2')['station_got_ip'])
        self.assertFalse(analyze('Found AP: Got IP: private')['station_got_ip'])

if __name__=='__main__':unittest.main()
