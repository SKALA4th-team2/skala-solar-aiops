"""project/에서 실행. TestClient 응답 증빙이며 실제 학습 모델의 성능 증빙이 아니다."""
import argparse
import csv
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'project'))
from fastapi.testclient import TestClient
from serving_app.main import app
from serving_app import model_loader
from serving_app.routers import data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    dataset = Path(__file__).resolve().parents[2] / 'datasets/hadong_upload_forecast_jma.csv'
    with dataset.open() as source:
        rows = list(csv.DictReader(source))
    sequence = [{'date': row['Date'], 'close': float(row['Close']), 'volume': float(row['Volume'])} for row in rows[-20:]]
    records = []
    with tempfile.TemporaryDirectory() as temp, patch.object(data, 'UPLOAD_DIR', temp), patch.object(model_loader, '_model_cache', None), patch.object(model_loader, 'LOCAL_MODEL_PATH', str(Path(temp) / 'missing.keras')), patch.dict(os.environ, {'MODEL_SOURCE': 'local', 'LOADING_MODE': 'lazy'}), TestClient(app) as client:
        def capture(name, method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            records.append({'case': name, 'method': method, 'path': path, 'status_code': response.status_code, 'body': response.json()})
            return response
        capture('health', 'GET', '/health')
        capture('predict_model_missing', 'POST', '/predict', json={'sequence': sequence})
        capture('predict_invalid_length', 'POST', '/predict', json={'sequence': sequence[:-1]})
        capture('upload_solar_dataset', 'POST', '/data/upload', files={'file': ('input.csv', dataset.read_bytes(), 'text/csv')})
        capture('data_status', 'GET', '/data/status')
        capture('upload_invalid_number', 'POST', '/data/upload', files={'file': ('bad.csv', 'Date,Close,Volume\n2025-01-01,abc,1\n', 'text/csv')})
        model = Mock(version='fixture-model', source='local')
        model.predict_one.return_value = 123.456
        with patch.object(model_loader, 'get_model', return_value=model):
            capture('predict_200_with_stub_model', 'POST', '/predict', json={'sequence': sequence})
        (output / 'http-results.json').write_text(json.dumps({'verification': 'FastAPI TestClient 내부 ASGI 호출. 200 예측값은 고정 대체 모델이다. 실제 네트워크·학습 품질 검증 아님.', 'results': records}, ensure_ascii=False, indent=2) + '\n')
        (output / 'openapi.json').write_text(json.dumps(client.get('/openapi.json').json(), ensure_ascii=False, indent=2) + '\n')
        assert [r['status_code'] for r in records] == [200, 503, 422, 200, 200, 400, 200]
        print([(r['case'], r['status_code']) for r in records])


if __name__ == '__main__':
    main()
