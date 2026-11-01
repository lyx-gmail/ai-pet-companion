import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('device_boot',Path(__file__).with_name('device_boot.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class BootLogTests(unittest.TestCase):
    def test_private_lines_not_copied_to_public_evidence(self):
        result = module.analyze('WiFi password=private-example\n'
            'I (10000) PetRuntime: pet alive: rev=9 sat=70 mood=70 energy=80 closeness=50 sleep=0 pending=0 storage=1\n'
            'I (20000) PetRuntime: pet alive: rev=19 sat=70 mood=70 energy=80 closeness=50 sleep=0 pending=0 storage=1\n')
        self.assertTrue(result['observed_pet_runtime'])
        self.assertTrue(result['state_ticks_progressing'])
        self.assertTrue(result['storage_available'])
        self.assertNotIn('private-example',str(result))
        self.assertFalse(result['hardware_animation_verified'])

    def test_crash_and_storage_fault_are_not_success(self):
        result = module.analyze('Guru Meditation Error\nPetRuntime: pet alive: rev=0 sat=70 mood=70 energy=80 closeness=50 sleep=0 pending=0 storage=0\n')
        self.assertTrue(result['crash_observed'])
        self.assertFalse(result['ok'])
        self.assertFalse(module.analyze('')['ok'])


if __name__=='__main__':
    unittest.main()
