import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('device_command',Path(__file__).with_name('device_command.py'))
command=importlib.util.module_from_spec(spec)
spec.loader.exec_module(command)


class DeviceCommandTests(unittest.TestCase):
    def test_ack_and_numeric_state_only(self):
        text=('WiFi password=private-example\nPetUsb: dispatch=1\n'
              'PetUsb: state={"ok":true,"satiety":76,"sleeping":false,"api_key":"private-example","mood":"secret"}\n')
        result=command.analyze('state',text)
        self.assertTrue(result['ok'])
        self.assertEqual(result['state'],{'ok':True,'satiety':76,'sleeping':False})
        self.assertNotIn('private-example',str(result))
        self.assertNotIn('secret',str(result))

    def test_missing_ack_wrong_command_and_bad_json_fail(self):
        self.assertFalse(command.analyze('main','PetUsb: dispatch=4\n')['ok'])
        self.assertFalse(command.analyze('state','PetUsb: dispatch=1\nPetUsb: state={bad}\n')['ok'])
        self.assertFalse(command.analyze('state','')['ok'])


if __name__=='__main__': unittest.main()
