"""Isolated bundle archive tests: no operational files or network access."""
import io
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'project'))
from serving_app import runtime as rt, model_store, registry


class BundleArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        env = patch.dict(os.environ, SOLAR_STATE_DIR=str(base / 'runtime'),
                         SOLAR_MODEL_STORE='local', SOLAR_MODEL_ARCHIVE_DIR=str(base / 'archive'))
        env.start(); self.addCleanup(env.stop)
        contract = patch.object(rt, 'CONTRACT', 'solar_hourly_24_jma_day2_v1')
        contract.start(); self.addCleanup(contract.stop)
        self.pid = 'hadong-sewage'
        rt.write(rt.root() / 'catalog.json', {'plants': {self.pid: {}}, 'portfolios': {}})
        self.bundle = rt.version_dir(self.pid, '2')
        self.bundle.mkdir(parents=True)
        (self.bundle / 'model.keras').write_bytes(b'model fixture')
        (self.bundle / 'scaler.pkl').write_bytes(b'fixed scaler fixture')
        self.manifest = dict(plant_id=self.pid, version='2', contract=rt.CONTRACT,
            model_name=rt.model_name(self.pid), gate={'passed': True},
            hashes={name: rt.sha(self.bundle / name) for name in model_store.FILES[:2]})
        rt.write(self.bundle / 'manifest.json', self.manifest)

    def test_publish_restore_and_idempotent_publish(self):
        receipt = model_store.publish(self.pid, '2')
        self.assertEqual(model_store.publish(self.pid, '2'), receipt)
        shutil.rmtree(self.bundle)
        model_store.ensure_local(self.pid, '2')
        self.assertEqual(model_store.validate(self.bundle, self.pid, '2'), self.manifest)

    def test_corrupt_download_never_installs_cache(self):
        receipt = model_store.publish(self.pid, '2')
        shutil.rmtree(self.bundle)
        (model_store.LocalStore().root / receipt['key'] / 'model.keras').write_bytes(b'corrupt')
        with self.assertRaises(ValueError): model_store.ensure_local(self.pid, '2')
        self.assertFalse(self.bundle.exists())

    def test_failed_upload_never_writes_receipt(self):
        backend = Mock()
        backend.put.side_effect = OSError('unavailable')
        with patch.object(model_store, 'store', return_value=backend):
            with self.assertRaises(OSError): model_store.publish(self.pid, '2')
        self.assertFalse(model_store.receipt_path(self.pid, '2').exists())

    def test_archive_failure_does_not_change_production(self):
        rt.write(rt.plant_dir(self.pid) / 'current.json', {'version': '1'})
        loader = Mock(load_bundle=Mock(return_value=SimpleNamespace(manifest=self.manifest)))
        with patch.dict(sys.modules, {'serving_app.model_loader': loader}), \
             patch.object(model_store, 'publish', side_effect=OSError('archive unavailable')), \
             patch.object(registry, 'client') as client:
            with self.assertRaises(OSError): registry.activate(self.pid, '2', expected_version='1')
            client.assert_not_called()
        self.assertEqual(rt.current(self.pid)['version'], '1')

    def test_rejected_or_mismatched_bundle_not_published(self):
        for change in ({'gate': {'passed': False}}, {'plant_id': 'another-plant'}):
            rt.write(self.bundle / 'manifest.json', dict(self.manifest, **change))
            with self.assertRaises(ValueError): model_store.publish(self.pid, '2')

    def test_existing_archive_cannot_be_overwritten(self):
        backend = model_store.LocalStore()
        backend.put('test/object', b'first')
        with self.assertRaises(ValueError): backend.put('test/object', b'second')
        self.assertEqual(backend.get('test/object'), b'first')

    def test_disabled_never_creates_client(self):
        with patch.dict(os.environ, SOLAR_MODEL_STORE='disabled'), \
             patch.object(model_store, 'R2Store') as remote:
            self.assertIsNone(model_store.publish(self.pid, '2'))
            model_store.ensure_local(self.pid, '2')
            remote.assert_not_called()

    def test_warm_cache_never_contacts_archive(self):
        with patch.object(model_store, 'store', side_effect=AssertionError('network access')):
            self.assertEqual(model_store.ensure_local(self.pid, '2'), self.bundle)

    def test_r2_uses_conditional_write_and_closes_download(self):
        from botocore.exceptions import ClientError
        backend = model_store.R2Store.__new__(model_store.R2Store)
        backend.bucket = 'test'; backend.client = Mock()
        backend.client.put_object.side_effect = ClientError(
            {'Error': {'Code': 'PreconditionFailed'}, 'ResponseMetadata': {'HTTPStatusCode': 412}}, 'PutObject')
        stream = io.BytesIO(b'first')
        backend.client.get_object.return_value = {'Body': stream}
        backend.put('test/object', b'first')
        self.assertTrue(stream.closed)
        backend.client.put_object.assert_called_once_with(Bucket='test', Key='test/object', Body=b'first', IfNoneMatch='*')

    def test_real_hourly_model_predictions_survive_restore(self):
        import numpy as np
        from serving_app.hourly.model import load_bundle
        seed = rt.PROJECT / 'serving_app/models/hourly-seed'
        if not (seed / 'models' / self.pid / 'model.keras').is_file():
            self.skipTest('Approved hourly seed is not available')
        rt.write(rt.root() / 'catalog.json', rt.read(seed / 'catalog.json'))
        for name in model_store.FILES:
            shutil.copy2(seed / 'models' / self.pid / name, self.bundle / name)
        manifest = rt.read(self.bundle / 'manifest.json')
        manifest.update(version='2', model_name=rt.model_name(self.pid))
        rt.write(self.bundle / 'manifest.json', manifest)
        x = np.zeros((1, 24, 9), dtype='float32')
        x[:, :, 0] = .2
        x[:, :, 1] = .5
        x[:, :, 2] = .5
        before = load_bundle(self.pid, '2').predict_x(x)
        self.assertGreater(float(before.sum()), 0)
        model_store.publish(self.pid, '2')
        shutil.rmtree(self.bundle)
        after = load_bundle(self.pid, '2').predict_x(x)
        np.testing.assert_allclose(before, after, rtol=0, atol=0)

    def test_launcher_reads_mode_and_honors_environment_override(self):
        from scripts.run_backend import configure_model_store
        with patch.dict(os.environ, {}, clear=True), \
             patch('dotenv.dotenv_values', return_value={'SOLAR_MODEL_STORE': 'r2'}):
            configure_model_store()
            self.assertEqual(os.environ['SOLAR_MODEL_STORE'], 'r2')
            os.environ['SOLAR_MODEL_STORE'] = 'disabled'
            configure_model_store()
            self.assertEqual(os.environ['SOLAR_MODEL_STORE'], 'disabled')

    def test_rollback_with_local_bundle_does_not_access_archive(self):
        rt.write(rt.plant_dir(self.pid) / 'current.json', {'version': '1'})
        loader = Mock(load_bundle=Mock(return_value=SimpleNamespace(manifest=self.manifest)))
        with patch.dict(sys.modules, {'serving_app.model_loader': loader}), \
             patch.object(registry, 'archive_bundle', side_effect=AssertionError('archive write')), \
             patch.object(registry, 'client', return_value=Mock()):
            result = registry.rollback(self.pid, '2')
        self.assertEqual(result['version'], '2')

    def test_seed_activation_skips_archive(self):
        loader = Mock(load_bundle=Mock(return_value=SimpleNamespace(manifest=self.manifest)))
        with patch.dict(sys.modules, {'serving_app.model_loader': loader}), \
             patch.object(model_store, 'store', side_effect=AssertionError('archive access')), \
             patch.object(registry, 'client', return_value=Mock()):
            result = registry.activate(self.pid, '2', archive=False)
        self.assertEqual(result['version'], '2')
        self.assertFalse(model_store.receipt_path(self.pid, '2').exists())

    def test_partial_local_bundle_rejected_before_download(self):
        model_store.publish(self.pid, '2')
        (self.bundle / 'model.keras').unlink()
        backend = Mock()
        with patch.object(model_store, 'store', return_value=backend):
            with self.assertRaises(ValueError): model_store.ensure_local(self.pid, '2')
        backend.get.assert_not_called()

    def test_local_store_names_missing_archive_dir(self):
        with patch.dict(os.environ):
            del os.environ['SOLAR_MODEL_ARCHIVE_DIR']
            with self.assertRaisesRegex(ValueError, 'SOLAR_MODEL_ARCHIVE_DIR'): model_store.LocalStore()

    def test_restore_without_receipt_uses_registry_reference(self):
        receipt = model_store.publish(self.pid, '2')
        model_store.receipt_path(self.pid, '2').unlink()
        shutil.rmtree(self.bundle)
        c = Mock()
        c.get_model_version.return_value.tags = {'archive_' + key: value for key, value in receipt.items()}
        with patch.object(registry, 'client', return_value=c):
            model_store.ensure_local(self.pid, '2')
        self.assertEqual(model_store.validate(self.bundle, self.pid, '2'), self.manifest)
        self.assertEqual(rt.read(model_store.receipt_path(self.pid, '2')), receipt)

    def test_new_archive_records_registry_reference(self):
        c = Mock()
        with patch.object(registry, 'client', return_value=c):
            receipt = registry.archive_bundle(self.pid, '2')
        for key, value in receipt.items():
            c.set_model_version_tag.assert_any_call(rt.model_name(self.pid), '2', 'archive_' + key, value)


if __name__ == '__main__': unittest.main()
