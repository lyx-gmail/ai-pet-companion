"""Guard the real draft export boundary without reading actual credentials."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('review_bundle',ROOT/'scripts/prepare-review-bundle.py')
review=importlib.util.module_from_spec(spec);spec.loader.exec_module(review)


class ReviewBundleChecks(unittest.TestCase):
    def setUp(self):
        folder=ROOT/'.runtime/checks';folder.mkdir(parents=True,exist_ok=True)
        self.temporary=tempfile.TemporaryDirectory(prefix='release-',dir=folder)
        self.addCleanup(self.temporary.cleanup);self.root=Path(self.temporary.name)
        (self.root/'README.md').write_text('Fictional source only',encoding='utf-8')

    def test_private_scopes_excluded_but_draft_manifest_keeps_gaps(self):
        (self.root/'.env').write_text('PET_API_TOKEN=private-fixture-token-123')
        (self.root/'backend').mkdir();(self.root/'backend/fixture.db').write_bytes(b'private')
        (self.root/'firmware/locks').mkdir(parents=True)
        (self.root/'firmware/locks/dependencies.lock').write_text('Pinned fictional dependency')
        files,report=review.inspect(self.root)
        destination=self.root/'.runtime/release/draft.zip';review.bundle(self.root,files,report,destination)
        with zipfile.ZipFile(destination) as archive:
            self.assertEqual(set(archive.namelist()),{'README.md','firmware/locks/dependencies.lock','REVIEW_MANIFEST.json'})
            manifest=json.loads(archive.read('REVIEW_MANIFEST.json'))
            self.assertFalse(manifest['release_ready']);self.assertFalse(manifest['clean_install_verified'])
            self.assertFalse(manifest['root_license_present'])

    def test_leaked_private_value_and_key_block_export_without_echo(self):
        secret='fixture-private-token-123456'
        (self.root/'.env').write_text('PET_API_TOKEN='+secret)
        (self.root/'README.md').write_text(secret+'\n'+'sk-'+'a'*32)
        files,report=review.inspect(self.root)
        self.assertFalse(report['source_audit_passed']);self.assertNotIn(secret,json.dumps(report))
        self.assertEqual({x['kind'] for x in report['findings']},{'api_key_literal','matches_private_configuration'})
        with self.assertRaisesRegex(ValueError,'SOURCE_AUDIT_FAILED'):
            review.bundle(self.root,files,report,self.root/'.runtime/release/draft.zip')

    def test_changed_source_keeps_previous_archive_and_removes_partial(self):
        files,report=review.inspect(self.root)
        destination=self.root/'.runtime/release/draft.zip';destination.parent.mkdir(parents=True)
        destination.write_bytes(b'previous-draft');(self.root/'README.md').write_text('Changed')
        with self.assertRaisesRegex(ValueError,'SOURCE_CHANGED_DURING_BUNDLE'):
            review.bundle(self.root,files,report,destination)
        self.assertEqual(destination.read_bytes(),b'previous-draft')
        self.assertEqual(list(destination.parent.glob('*.partial')),[])

    def test_credential_filename_is_blocked_and_not_echoed_in_manifest(self):
        secret='sk-'+'b'*32
        (self.root/'docs').mkdir();(self.root/'docs'/f'{secret}.md').write_text('Fixture')
        _,report=review.inspect(self.root)
        self.assertFalse(report['source_audit_passed']);self.assertNotIn(secret,json.dumps(report))
        self.assertEqual(report['findings'][0]['kind'],'credential_in_path')

    def test_missing_packaged_link_blocks_then_existing_target_passes(self):
        (self.root/'README.md').write_text('[entry](docs/entry.md)')
        files,report=review.inspect(self.root);destination=self.root/'.runtime/release/draft.zip'
        with self.assertRaisesRegex(ValueError,'BUNDLE_BROKEN_LOCAL_LINK'):
            review.bundle(self.root,files,report,destination)
        self.assertFalse(destination.exists())
        (self.root/'docs').mkdir();(self.root/'docs/entry.md').write_text('Present')
        files,report=review.inspect(self.root)
        self.assertTrue(review.bundle(self.root,files,report,destination)['markdown_local_links_verified'])


if __name__=='__main__':unittest.main()
