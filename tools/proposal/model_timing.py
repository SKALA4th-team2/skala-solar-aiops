"""모델을 불러오는 시간과 한 건을 계산하는 시간을 잰다. 코드의 빈칸은 건드리지 않는다.

/predict 가 빈칸 때문에 응답하지 못해 엔드포인트의 응답 시간을 잴 수 없을 때,
응답 시간 목표의 참고값으로 쓰려는 것이다. 여기서 잰 값은 "모델 계산만"의 시간이고
엔드포인트의 응답 시간이 아니다(요청 검증, 스케일링, 직렬화, 네트워크가 빠져 있다).

실행 (서빙 앱의 작업 디렉터리, 곧 project/ 에서. MLflow 에 Production 모델이 등록돼 있어야 한다):
    python ../tools/proposal/model_timing.py --out ../docs/proposal/evidence/latency_model.json
"""
import argparse
import datetime as dt
import json
import os
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, os.getcwd())

p = argparse.ArgumentParser()
p.add_argument("--out", type=Path, required=True)
p.add_argument("--n", type=int, default=50)
a = p.parse_args()

import numpy as np  # noqa: E402

t0 = time.perf_counter()
import mlflow.tensorflow  # noqa: E402
import_s = time.perf_counter() - t0

from data.features import SEQ_LEN  # noqa: E402
from serving_app.lstm_model import N_FEATURES  # noqa: E402
from serving_app.model_loader import MLFLOW_MODEL_URI  # noqa: E402

t0 = time.perf_counter()
model = mlflow.tensorflow.load_model(MLFLOW_MODEL_URI)
load_s = time.perf_counter() - t0

x = np.random.default_rng(0).random((1, SEQ_LEN, N_FEATURES), dtype="float32")   # 0 ~ 1 로 스케일된 입력과 같은 모양

t0 = time.perf_counter()
model.predict(x, verbose=0)
first_ms = (time.perf_counter() - t0) * 1000

times = []
for _ in range(a.n):
    t0 = time.perf_counter()
    model.predict(x, verbose=0)
    times.append((time.perf_counter() - t0) * 1000)
times.sort()


def pct(q):
    return times[min(len(times) - 1, int(round(q * (len(times) - 1))))]


result = {
    "measured_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
    "what": "모델을 불러오는 시간과 한 건 계산 시간. 엔드포인트 응답 시간이 아니다",
    "model_uri": MLFLOW_MODEL_URI,
    "input_shape": list(x.shape),
    "import_mlflow_tensorflow_s": round(import_s, 3),
    "load_model_s": round(load_s, 3),
    "first_predict_ms": round(first_ms, 1),
    "repeat": {
        "n": a.n,
        "median_ms": round(statistics.median(times), 1),
        "p95_ms": round(pct(0.95), 1),
        "min_ms": round(times[0], 1),
        "max_ms": round(times[-1], 1),
    },
}
a.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=2))
