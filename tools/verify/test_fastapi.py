"""project/에서 실행: .venv/bin/python ../tools/verify/test_fastapi.py

모델 계산과 AIOps는 대체 객체로 격리한다. 실제 품질·학습·승격 검증이 아니다.
"""
import csv
from datetime import date, timedelta
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'project'))
from fastapi.testclient import TestClient
from serving_app.main import app
from serving_app import model_loader, aiops_adapter
from serving_app.routers import data, predict, logs


def csv_text(count=41):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Date', 'Close', 'Volume'])
    for i in range(count):
        writer.writerow([(date(2025, 1, 1) + timedelta(days=i)).isoformat(), 100 + i, 10.25])
    return output.getvalue()


class FastAPIContractTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.state_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.state_directory.cleanup)
        self.enterContext(patch.dict(os.environ, {'SOLAR_STATE_DIR': self.state_directory.name, 'AIOPS_ENABLED': '0'}))
        self.enterContext(patch.object(data, 'UPLOAD_DIR', self.directory.name))
        self.enterContext(patch.object(logs, 'LOG_DIR', self.directory.name))
        self.enterContext(patch.object(model_loader, '_model_cache', None))
        self.enterContext(patch.object(aiops_adapter, '_evaluator', None))
        self.enterContext(patch.dict(os.environ, {'LOADING_MODE': 'lazy'}))
        self.client = self.enterContext(TestClient(app))

    def upload(self, content):
        if isinstance(content, str):
            content = content.encode('utf-8')
        return self.client.post('/data/upload', files={'file': ('input.csv', content, 'text/csv')})

    def sequence(self):
        return [{'date': (date(2025, 1, 1) + timedelta(days=i)).isoformat(), 'close': 100 + i, 'volume': 10.25} for i in range(20)]

    def batch(self, count=41):
        return {
            'dates': [(date(2025, 1, 1) + timedelta(days=i)).isoformat() for i in range(count)],
            'prices': list(range(100, 100 + count)),
            'volumes': [10 + i / 100 for i in range(count)],
            'expected': [120.0] * count,
        }

    def test_health_does_not_load_model(self):
        with patch.object(model_loader, '_load_model') as load:
            response = self.client.get('/health')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['model_loaded'])
        self.assertIsNone(response.json()['model_version'])
        load.assert_not_called()

    def test_health_reports_loaded_version(self):
        with patch.object(model_loader, '_model_cache', Mock(version='fixture-v2', source='local')):
            response = self.client.get('/health')
        self.assertEqual(response.json()['model_version'], 'fixture-v2')

    def test_predict_passes_sequence_and_version(self):
        model = Mock(version='fixture-v2', source='local')
        model.predict_one.return_value = 123.456
        with patch.object(model_loader, 'get_model', return_value=model):
            response = self.client.post('/predict', json={'sequence': self.sequence()})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['predicted_close'], 123.46)
        self.assertEqual(response.json()['model_version'], 'fixture-v2')
        self.assertEqual(len(model.predict_one.call_args.args[0]), 20)
        self.assertEqual(response.json()['target_date'], '2025-01-21')
        self.assertEqual(set(model.predict_one.call_args.args[0][0]), {'close', 'volume'})

    def test_invalid_sequence_rejected_before_loading(self):
        with patch.object(model_loader, 'get_model') as load:
            for length in (19, 21):
                sequence = (self.sequence() * 2)[:length]
                self.assertEqual(self.client.post('/predict', json={'sequence': sequence}).status_code, 422)
        load.assert_not_called()

    def test_missing_model_returns_503(self):
        with patch.object(model_loader, 'get_model', side_effect=FileNotFoundError('/private/model')):
            for path, body in [('/predict', {'sequence': self.sequence()}), ('/predict/batch-test', self.batch())]:
                response = self.client.post(path, json=body)
                self.assertEqual(response.status_code, 503)
                self.assertNotIn('/private/model', response.text)

    def test_real_local_loader_missing_files_returns_503(self):
        with patch.dict(os.environ, {'MODEL_SOURCE': 'local'}), patch.object(model_loader, 'LOCAL_MODEL_PATH', str(Path(self.directory.name) / 'missing.keras')):
            response = self.client.post('/predict', json={'sequence': self.sequence()})
        self.assertEqual(response.status_code, 503)
        self.assertFalse(self.client.get('/health').json()['model_loaded'])

    def test_batch_windows_and_aiops_boundary(self):
        model = Mock(version='fixture')
        model.predict_one.side_effect = lambda sequence: sequence[-1]['close'] + 1
        with patch.object(model_loader, 'get_model', return_value=model), patch.object(predict, 'evaluate_batch', return_value={'status': 'ok', 'model_version': 'fixture'}) as check:
            response = self.client.post('/predict/batch-test', json=self.batch())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['predictions'], list(range(120, 141)))
        self.assertEqual(response.json()['drift_check'], {'status': 'ok', 'model_version': 'fixture'})
        self.assertEqual(len(check.call_args.kwargs['predictions']), 21)
        for i, call in enumerate(model.predict_one.call_args_list):
            self.assertEqual([p['close'] for p in call.args[0]], list(range(100+i, 120+i)))
        self.assertTrue(all(p['actual'] == p['predicted'] for p in check.call_args.kwargs['predictions']))
        self.assertEqual(check.call_args.kwargs['rows'][0], {'date': '2025-01-01', 'close': 100, 'volume': 10, 'expected': 120})
        self.assertEqual(len(check.call_args.kwargs['rows']), 41)
        self.assertEqual(check.call_args.kwargs['predictions'][0]['date'], '2025-01-21')
        self.assertEqual(model.predict_one.call_args_list[0].args[0][-1]['volume'], 10.19)
        self.assertEqual(set(model.predict_one.call_args_list[0].args[0][0]), {'close', 'volume'})

    def test_upload_roundtrip_and_unique_names(self):
        first = self.upload(csv_text())
        second = self.upload(csv_text())
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertNotEqual(first.json()['filename'], second.json()['filename'])
        self.assertEqual(len(list(Path(self.directory.name,'hadong-sewage').glob('*.csv'))), 2)
        self.assertEqual(list(Path(self.directory.name).glob('*.tmp')), [])
        response = self.client.get('/data/status')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['rows'], 41)
        self.assertEqual(response.json()['start_date'], '2025-01-01')
        self.assertEqual(response.json()['end_date'], '2025-02-10')

    def test_bad_values_never_saved(self):
        for value in ('abc', '', '-1', 'NaN', 'inf', '-inf'):
            with self.subTest(value=value):
                for column in ('Close', 'Volume'):
                    text = csv_text()
                    text = text.replace('100,10.25', f'{value},10.25' if column == 'Close' else f'100,{value}', 1)
                    self.assertEqual(self.upload(text).status_code, 400)
        self.assertEqual(list(Path(self.directory.name).iterdir()), [])

    def test_bad_dates_never_saved(self):
        for replacement in ('2025-01-01', '2024-12-31', '2025-02-30', '20250102', ''):
            with self.subTest(date=replacement):
                response = self.upload(csv_text().replace('2025-01-02', replacement, 1))
                self.assertEqual(response.status_code, 400)
        self.assertEqual(list(Path(self.directory.name).iterdir()), [])

    def test_csv_shape_and_encoding(self):
        cases = [csv_text(40), csv_text().replace('Volume', 'Missing'), csv_text().replace('Volume', 'Close'), csv_text().replace('100,10.25', '100,10.25,extra', 1), csv_text().replace('100,10.25', '100', 1), '날짜,값'.encode('cp949')]
        for body in cases:
            self.assertEqual(self.upload(body).status_code, 400)
        self.assertEqual(self.client.post('/data/upload').status_code, 422)
        self.assertEqual(self.upload('\ufeff' + csv_text()).status_code, 200)

    def test_no_upload_and_corrupt_existing_upload(self):
        self.assertEqual(self.client.get('/data/status').json(), {'exists': False})
        Path(self.directory.name, 'hadong-sewage').mkdir()
        Path(self.directory.name, 'hadong-sewage', 'invalid.csv').write_text('Date,Close,Volume\n2025-01-01,abc,1\n')
        response = self.client.get('/data/status')
        self.assertEqual(response.status_code, 409)
        self.assertIn('다시 업로드', response.json()['detail'])

    def test_invalid_upload_preserves_latest_valid_file(self):
        filename = self.upload(csv_text()).json()['filename']
        self.assertEqual(self.upload(csv_text().replace('100,10.25', 'abc,10.25', 1)).status_code, 400)
        self.assertEqual(self.client.get('/data/status').json()['filename'], filename)

    def test_logs_and_missing_log(self):
        Path(self.directory.name, 'test.log').write_text('test fixture\n')
        self.assertEqual(self.client.get('/logs/test.log').json()['content'], 'test fixture\n')
        self.assertEqual(self.client.get('/logs/missing.log').status_code, 404)
        self.assertEqual(self.client.get('/logs').json()[0]['name'], 'test.log')

    def test_solar_numeric_boundaries(self):
        model = Mock(version='fixture', source='local')
        model.predict_one.return_value = -2.5
        with patch.object(model_loader, 'get_model', return_value=model):
            for close, volume in [(0, 0), (1320, 45), (120.5, 10.25)]:
                sequence = self.sequence()
                sequence[0].update(close=close, volume=volume)
                response = self.client.post('/predict', json={'sequence': sequence})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()['predicted_close'], 0)
        with patch.object(model_loader, 'get_model') as load:
            for field, value in [('close', -1), ('close', 1320.1), ('volume', -1), ('volume', 45.1), ('close', True), ('volume', '10.5')]:
                sequence = self.sequence()
                sequence[0][field] = value
                self.assertEqual(self.client.post('/predict', json={'sequence': sequence}).status_code, 422)
            load.assert_not_called()

    def test_solar_dates_and_extra_fields(self):
        with patch.object(model_loader, 'get_model') as load:
            for value in ['2025-01-01', '2025-01-03', '2025-02-30', '20250102', 1735776000, '2025-01-02T00:00:00Z']:
                sequence = self.sequence()
                sequence[1]['date'] = value
                self.assertEqual(self.client.post('/predict', json={'sequence': sequence}).status_code, 422)
            sequence = self.sequence()
            del sequence[0]['date']
            self.assertEqual(self.client.post('/predict', json={'sequence': sequence}).status_code, 422)
            sequence = self.sequence()
            sequence[0]['expected'] = 150
            self.assertEqual(self.client.post('/predict', json={'sequence': sequence}).status_code, 422)
            load.assert_not_called()

    def test_leap_day_target_and_max_date(self):
        model = Mock(version='fixture', source='local')
        model.predict_one.return_value = 1
        for last, target in [(date(2024, 2, 28), '2024-02-29'), (date(2025, 12, 31), '2026-01-01')]:
            sequence = self.sequence()
            for i, point in enumerate(sequence):
                point['date'] = (last - timedelta(days=19-i)).isoformat()
            with patch.object(model_loader, 'get_model', return_value=model):
                response = self.client.post('/predict', json={'sequence': sequence})
            self.assertEqual(response.json()['target_date'], target)
        sequence = self.sequence()
        for i, point in enumerate(sequence):
            point['date'] = (date.max - timedelta(days=19-i)).isoformat()
        self.assertEqual(self.client.post('/predict', json={'sequence': sequence}).status_code, 422)

    def test_nonfinite_model_output_returns_503(self):
        for output in [float('nan'), float('inf'), float('-inf')]:
            model = Mock(version='fixture', source='local')
            model.predict_one.return_value = output
            with patch.object(model_loader, 'get_model', return_value=model):
                response = self.client.post('/predict', json={'sequence': self.sequence()})
            self.assertEqual(response.status_code, 503)

    def test_nonfinite_json_input_returns_422(self):
        import json
        body = json.dumps({'sequence': self.sequence()}).replace('100,', '1e309,', 1)
        response = self.client.post('/predict', content=body, headers={'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 422)

    def test_solar_upload_range_and_continuity(self):
        for text in [csv_text().replace('100,10.25', '1320.1,10.25', 1), csv_text().replace('100,10.25', '100,45.1', 1), csv_text().replace('2025-02-10', '2025-02-11')]:
            self.assertEqual(self.upload(text).status_code, 400)
        self.assertEqual(self.upload(csv_text().replace('100,10.25', '0,0', 1)).status_code, 200)
        self.assertEqual(self.upload(csv_text().replace('100,10.25', '1320,45', 1)).status_code, 200)
        dataset = Path(__file__).resolve().parents[2] / 'datasets/hadong_upload_forecast_jma.csv'
        self.assertEqual(self.upload(dataset.read_bytes()).status_code, 200)

    def test_batch_rejects_misalignment_and_bad_values(self):
        with patch.object(model_loader, 'get_model') as load:
            for key in ['dates', 'prices', 'volumes', 'expected']:
                payload = self.batch()
                payload[key].pop()
                self.assertEqual(self.client.post('/predict/batch-test', json=payload).status_code, 422)
                del payload[key]
                self.assertEqual(self.client.post('/predict/batch-test', json=payload).status_code, 422)
            for key, value in [('dates', '2025-01-03'), ('prices', -1), ('prices', 1321), ('volumes', 45.01), ('volumes', True), ('expected', -1)]:
                payload = self.batch()
                payload[key][1] = value
                self.assertEqual(self.client.post('/predict/batch-test', json=payload).status_code, 422)
            self.assertEqual(self.client.post('/predict/batch-test', json=self.batch(20)).status_code, 422)
            load.assert_not_called()

    def test_batch_unconfigured_aiops_is_skipped_and_no_history(self):
        model = Mock(version='fixture', source='local')
        model.predict_one.return_value = 10
        payload = self.batch(21)
        payload['expected'] = [None] * 21
        with patch.object(model_loader, 'get_model', return_value=model):
            for _ in range(2):
                response = self.client.post('/predict/batch-test', json=payload)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()['predictions'], [10])
                self.assertEqual(response.json()['drift_check'], {'status': 'skipped', 'model_version': 'fixture', 'reason': 'aiops_not_configured'})

    def test_aiops_adapter_receives_full_rows_and_preserves_null(self):
        model = Mock(version='fixture', source='local')
        model.predict_one.return_value = 10
        evaluator = Mock(return_value={'status': 'facility_check', 'model_version': 'fixture', 'pi': None, 'outage_days': 1})
        aiops_adapter.configure_evaluator(evaluator)
        with patch.object(model_loader, 'get_model', return_value=model):
            response = self.client.post('/predict/batch-test', json=self.batch())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['drift_check']['status'], 'facility_check')
        self.assertIsNone(response.json()['drift_check']['pi'])
        self.assertEqual(len(evaluator.call_args.kwargs['rows']), 41)
        self.assertEqual(len(evaluator.call_args.kwargs['predictions']), 21)
        aiops_adapter.configure_evaluator(None)

    def test_expected_does_not_change_model_inputs(self):
        model = Mock(version='fixture', source='local')
        model.predict_one.return_value = 10
        with patch.object(model_loader, 'get_model', return_value=model):
            payload = self.batch(21)
            self.client.post('/predict/batch-test', json=payload)
            first = model.predict_one.call_args.args[0]
            payload['expected'] = [9999] * 21
            self.client.post('/predict/batch-test', json=payload)
            self.assertEqual(model.predict_one.call_args.args[0], first)

    def test_bad_model_output_does_not_trigger_aiops(self):
        model = Mock(version='fixture', source='local')
        with patch.object(model_loader, 'get_model', return_value=model), patch.object(predict, 'evaluate_batch') as check:
            model.predict_one.return_value = float('nan')
            self.assertEqual(self.client.post('/predict/batch-test', json=self.batch()).status_code, 503)
            check.assert_not_called()

    def test_csv_batch_builder_and_export(self):
        from scripts.simulate_drift import build_batch, make_bundle
        import json
        import subprocess
        root = Path(__file__).resolve().parents[2]
        dataset = root / 'datasets/hadong_upload_forecast_jma.csv'
        expected = root / 'datasets/hadong_daily_full.csv'
        normal = build_batch(dataset, expected, '2025-07-31')
        bundle = make_bundle(normal)
        self.assertEqual(normal['dates'][0], '2025-06-21')
        self.assertEqual(len(normal['prices']), 41)
        self.assertTrue(all(v is not None for v in normal['expected']))
        for key in ['dates', 'volumes', 'expected']:
            self.assertEqual(bundle['normal'][key], bundle['drift'][key])
        self.assertEqual(bundle['drift']['prices'], [v * 0.86 for v in normal['prices']])
        self.assertEqual(build_batch(dataset, None)['expected'], [None] * 41)
        with self.assertRaises(ValueError):
            build_batch(dataset, expected, '1900-01-01')
        output = Path(self.directory.name) / 'bundle.json'
        result = subprocess.run([sys.executable, 'scripts/simulate_drift.py', '--csv', str(dataset), '--end-date', '2025-07-31', '--export-json', str(output)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(output.read_text()), bundle)

    def test_openapi_and_dashboard(self):
        response = self.client.get('/openapi.json')
        self.assertEqual(response.status_code, 200)
        self.assertIn('503', response.json()['paths']['/predict']['post']['responses'])
        self.assertEqual(self.client.get('/').status_code, 200)
        self.assertEqual(self.client.get('/docs').status_code, 200)


if __name__ == '__main__':
    unittest.main(verbosity=2)
