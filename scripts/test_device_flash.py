import hashlib
import importlib.util
from pathlib import Path
import struct
import unittest
import zlib
import tempfile
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('device_flash',Path(__file__).with_name('device_flash.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture():
    data = bytearray(b'\xff'*0x1000000)
    entries = [(1,2,0x9000,0x4000,b'nvs'),(1,0,0xd000,0x2000,b'otadata'),
               (1,1,0xf000,0x1000,b'phy_init'),(0,16,0x20000,0x3f0000,b'ota_0'),
               (0,17,0x410000,0x3f0000,b'ota_1'),(1,130,0x800000,0x800000,b'assets')]
    for index,(kind,sub,offset,size,label) in enumerate(entries):
        struct.pack_into('<HBBII16sI',data,0x8000+32*index,0x50aa,kind,sub,offset,size,label,0)
    struct.pack_into('<I',data,0xd000,1)
    struct.pack_into('<II',data,0xd018,2,zlib.crc32(data[0xd000:0xd004],0xffffffff))
    return data


class FlashGuardTests(unittest.TestCase):
    def test_backup_requires_exit_success_or_verified_complete_transport_log(self):
        data = b'backup-fixture'
        manifest = {'bytes':len(data),'sha256':module.sha(data),'read_exit_code':None}
        with self.assertRaises(ValueError): module.verify_backup(data, manifest)
        with tempfile.TemporaryDirectory() as directory, patch.object(module,'PRIVATE',Path(directory)):
            log = Path(directory)/'read.log'
            error = Path(directory)/'error.log'
            log.write_bytes(f'Read {len(data)} bytes at 0x00000000 in 206.0 seconds\nHard resetting via RTS pin...\n'.encode())
            error.write_bytes(b'')
            manifest.update(read_log='read.log',read_error_log='error.log',read_log_sha256=module.sha(log.read_bytes()))
            module.verify_backup(data,manifest)
            error.write_bytes(b'transfer failed')
            with self.assertRaises(ValueError): module.verify_backup(data,manifest)
        manifest['read_exit_code'] = 0
        with self.assertRaises(ValueError): module.verify_backup(data+b'changed',manifest)

    def test_native_usb_target_uses_explicit_reset_and_bounded_connect_attempts(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(module,'PRIVATE',Path(directory)), patch.object(module.subprocess,'run') as run:
            run.return_value.returncode = 0
            module.run_tool('diagnostic',['chip_id'])
            command = run.call_args.args[0]
        self.assertEqual(command[command.index('--before')+1], 'usb_reset')
        self.assertEqual(command[command.index('--connect-attempts')+1], '3')
        self.assertEqual(command[command.index('--after')+1], 'no_reset')

    def test_active_slot_and_crc(self):
        data = fixture()
        self.assertEqual(module.inspect_layout(data)['offset'],0x20000)
        struct.pack_into('<I',data,0xe000,2)
        struct.pack_into('<II',data,0xe018,2,zlib.crc32(data[0xe000:0xe004],0xffffffff))
        self.assertEqual(module.inspect_layout(data)['offset'],0x410000)
        data[0xe01c] ^= 1
        self.assertEqual(module.inspect_layout(data)['offset'],0x20000)

    def test_invalid_layout_and_unconfirmed_boot_are_rejected(self):
        for offset,value in ((0x8008,0),(0xd018,1),(0xd01c,0)):
            data = fixture()
            struct.pack_into('<I',data,offset,value)
            with self.assertRaises(ValueError):
                module.inspect_layout(data)
        with self.assertRaises(ValueError):
            module.inspect_layout(fixture()[:-1])


if __name__=='__main__':
    unittest.main()
