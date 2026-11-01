"""Local Git fixtures only: no network downloads, model calls or service changes."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('voice_source',ROOT/'scripts/setup-voice-source.py')
source=importlib.util.module_from_spec(spec);spec.loader.exec_module(source)


class VoiceSourceChecks(unittest.TestCase):
    def setUp(self):
        checks=ROOT/'.runtime/checks';checks.mkdir(parents=True,exist_ok=True)
        self.temporary=tempfile.TemporaryDirectory(prefix='voice-source-check-',dir=checks)
        self.addCleanup(self.temporary.cleanup);self.folder=Path(self.temporary.name)
        self.repository=self.folder/'upstream';self.repository.mkdir()
        source.git(self.repository,'init','--quiet')
        self.first=self.commit('first');self.second=self.commit('second')
        self.root=self.folder/'clean-project';self.root.mkdir()

    def commit(self,text):
        (self.repository/'README.md').write_text(text)
        source.git(self.repository,'add','README.md')
        source.git(self.repository,'-c','user.name=Fixture','-c','user.email=fixture@example.invalid',
            'commit','--quiet','-m',text)
        return source.git(self.repository,'rev-parse','HEAD')

    def checkout(self,commit):
        return source.ensure_source(self.root,str(self.repository),commit)

    def test_exact_commit_not_remote_head_and_repeat_preserves_overlay(self):
        self.assertFalse(self.checkout(self.first)['reused_existing_checkout'])
        destination=self.root/'.tools/upstream/xiaozhi-esp32-server'
        self.assertEqual((destination/'README.md').read_text(),'first')
        (destination/'README.md').write_text('User overlay')
        self.assertTrue(self.checkout(self.first)['reused_existing_checkout'])
        self.assertEqual((destination/'README.md').read_text(),'User overlay')

    def test_existing_other_pin_is_preserved(self):
        self.checkout(self.second)
        with self.assertRaisesRegex(ValueError,'EXISTING_SOURCE_VERSION_MISMATCH_PRESERVED'):
            self.checkout(self.first)
        destination=self.root/'.tools/upstream/xiaozhi-esp32-server'
        self.assertEqual((destination/'README.md').read_text(),'second')

    def test_failed_fetch_leaves_no_half_checkout(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.checkout('f'*40)
        parent=self.root/'.tools/upstream'
        self.assertFalse((parent/'xiaozhi-esp32-server').exists())
        self.assertEqual(list(parent.glob('voice-source-*')),[])


if __name__=='__main__':unittest.main()
