"""한 PC 에서 서빙과 학습을 함께 돌릴 때의 크기를 잰다: 학습 시간, 메모리, 모델 하나가 차지하는 메모리, 학습 중의 예측 시간.

docs/proposal/single-pc-operation.md 의 규모 산정식에 넣을 "이 PC 의 값"을 얻으려는 것이다.
백엔드를 실제로 돌릴 PC 에서 다시 돌려 그 PC 의 값으로 바꾼다. 다른 PC 의 값을 옮겨 적지 않는다.

재는 것:
    env       운영체제, CPU 수, 메모리, 디스크 여유, 파이썬과 패키지 버전
    baseline  scripts/train_baseline_v1.py 한 번의 시간과 최대 메모리 (스케일러와 로컬 모델이 생긴다)
    mlflow    serving_app/train_and_register.py 한 번의 시간과 최대 메모리, MLflow 기록이 차지한 디스크
    memory    로컬 모델을 1, 2, 4, 8개 메모리에 올렸을 때의 프로세스 메모리 (모델 하나의 증가분)
    latency   predict_one 한 건의 시간: 한가할 때 / 다른 프로세스가 학습할 때 / 같은 프로세스의 다른 스레드가 학습할 때
    finetune  재학습 한 번(최근 41행을 이어서 학습)의 시간과, 레지스트리에서 모델을 불러오는 시간
    sqlite    두 프로세스가 같은 mlflow.db 에 동시에 기록할 때의 실패 수

주의:
    - 저장소의 project/ 가 아니라 **검증용 사본**에서 돌린다. 모델 파일, MLflow 기록, 업로드 파일이 생긴다.
        mkdir -p <사본 폴더> && git archive HEAD project | tar -x -C <사본 폴더>
        mkdir -p <사본 폴더>/project/data/uploads && cp datasets/hadong_upload_forecast_jma.csv <사본 폴더>/project/data/uploads/
    - 지금의 게이트는 4.00 이라 태양광 자료에서는 통과하지 못한다. 여기서는 걸린 시간만 본다.
    - latency 는 HTTP 를 거치지 않은 모델 계산 시간이다. 엔드포인트의 응답 시간이 아니다.

실행 (저장소 루트에서. 서빙 앱의 패키지가 설치된 파이썬으로):
    python tools/multi_plant/single_pc_probe.py --project <사본 폴더>/project --out <결과를 둘 폴더> [--steps env,baseline,mlflow,memory,latency,finetune,sqlite]
"""
import argparse
import json
import os
import platform
import resource
import shutil
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

RSS_UNIT = 1 if sys.platform == "darwin" else 1024      # ru_maxrss: macOS 는 바이트, 리눅스는 킬로바이트
MB = 1024 * 1024


def current_rss_mb():
    out = subprocess.run(["ps", "-o", "rss=", "-p", str(os.getpid())], capture_output=True, text=True).stdout.strip()
    return int(out) / 1024 if out else None


def quantiles(ms):
    ms = sorted(ms)
    return {"n": len(ms), "p50_ms": round(statistics.median(ms), 2), "p95_ms": round(ms[int(len(ms) * 0.95) - 1], 2),
            "max_ms": round(ms[-1], 2), "mean_ms": round(sum(ms) / len(ms), 2)}


def sample_sequence():
    """업로드 파일의 마지막 20행으로 요청 하나를 만든다."""
    from data.features import SEQ_LEN, load_rows
    from data.storage import latest_upload
    rows = load_rows(latest_upload())[-SEQ_LEN:]
    return [{"close": r["Close"], "volume": r["Volume"]} for r in rows]


# ───────────────────────────── 사본의 project/ 안에서 도는 작업 ─────────────────────────────

def worker_run(command):
    """명령 하나를 돌려 시간과 최대 메모리를 잰다. 이 프로세스의 자식은 그 명령 하나뿐이다."""
    start = time.time()
    r = subprocess.run(command, capture_output=True, text=True)
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    tail = [l for l in (r.stdout + r.stderr).splitlines() if any(k in l for k in ("RMSE", "GATE", "saved", "scaler fit", "Error", "Traceback"))]
    print(json.dumps({"seconds": round(time.time() - start, 2), "peak_rss_mb": round(usage.ru_maxrss * RSS_UNIT / MB, 1),
                      "cpu_seconds": round(usage.ru_utime + usage.ru_stime, 2), "exit_code": r.returncode, "output": tail[-6:]}, ensure_ascii=False))


def worker_memory():
    points = [{"stage": "start", "rss_mb": round(current_rss_mb(), 1)}]
    from serving_app import model_loader
    import tensorflow  # noqa: F401
    points.append({"stage": "tensorflow imported", "rss_mb": round(current_rss_mb(), 1)})
    seq, held = sample_sequence(), []
    for target in (1, 2, 4, 8):
        while len(held) < target:
            m = model_loader._load_from_local()
            m.predict_one(seq)            # 첫 예측 때 그래프가 만들어진다. 그것까지 넣어 잰다
            held.append(m)
        points.append({"stage": f"{target} models loaded and used", "rss_mb": round(current_rss_mb(), 1)})
    first, last = points[2]["rss_mb"], points[-1]["rss_mb"]
    print(json.dumps({"points": points, "per_extra_model_mb": round((last - first) / 7, 1),
                      "first_model_mb": round(points[2]["rss_mb"] - points[1]["rss_mb"], 1)}, ensure_ascii=False))


def timed_predictions(model, seq, stop=None, count=None):
    out, failures = [], 0
    while (count is not None and len(out) + failures < count) or (stop is not None and not stop()):
        t = time.perf_counter()
        try:
            model.predict_one(seq)
            out.append((time.perf_counter() - t) * 1000)
        except Exception:
            failures += 1
    return out, failures


def worker_latency():
    from serving_app import model_loader
    model, seq = model_loader._load_from_local(), sample_sequence()
    timed_predictions(model, seq, count=10)                          # 첫 호출의 준비 시간은 버린다
    idle, idle_fail = timed_predictions(model, seq, count=200)
    result = {"idle": {**quantiles(idle), "failures": idle_fail}}

    proc = subprocess.Popen([sys.executable, "serving_app/train_and_register.py"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    start = time.time()
    busy, busy_fail = timed_predictions(model, seq, stop=lambda: proc.poll() is not None)
    result["other_process_training"] = {**quantiles(busy), "failures": busy_fail, "training_seconds": round(time.time() - start, 2),
                                        "training_exit_code": proc.returncode}

    # 지금의 서빙 코드는 재학습을 요청을 처리하는 프로세스 안에서 돌린다. 같은 프로세스의 다른 스레드가 학습할 때를 본다.
    state = {}

    def train():
        try:
            from serving_app.train_and_register import train_and_register
            state["result"] = train_and_register()
        except Exception as exc:
            state["error"] = f"{type(exc).__name__}: {exc}"

    thread = threading.Thread(target=train)
    start = time.time()
    thread.start()
    same, same_fail = timed_predictions(model, seq, stop=lambda: not thread.is_alive())
    thread.join()
    result["same_process_training"] = {**(quantiles(same) if same else {"n": 0}), "failures": same_fail,
                                       "training_seconds": round(time.time() - start, 2), "training_error": state.get("error")}
    print(json.dumps(result, ensure_ascii=False))


def worker_finetune():
    """재학습 한 번(최근 41행, 이어서 학습)과 레지스트리에서 모델을 불러오는 시간을 잰다.

    지금의 게이트(4.00)는 태양광 자료에서 통과하지 못해 Production 모델이 생기지 않는다.
    시간을 재려고 **이 프로세스 안에서만** 게이트 값을 열어 둔다. 코드는 고치지 않는다. 여기서 나온 통과는 품질의 근거가 아니다.
    """
    import serving_app.train_and_register as T
    from data.features import SEQ_LEN, load_rows
    from data.storage import latest_upload
    from serving_app import model_loader
    T.RMSE_GATE = float("inf")
    start = time.time()
    base = T.train_and_register()
    base_seconds = time.time() - start
    rows = load_rows(latest_upload())[-(21 + SEQ_LEN):]
    fine = []
    for _ in range(3):
        start = time.time()
        r = T.fine_tune(rows)
        fine.append(round(time.time() - start, 2))
    loads = []
    for _ in range(3):
        start = time.time()
        model_loader._load_from_mlflow()
        loads.append(round(time.time() - start, 2))
    print(json.dumps({"base_training_seconds": round(base_seconds, 2), "fine_tune_rows": len(rows), "fine_tune_seconds": fine,
                      "registry_load_seconds": loads, "last_version": r.get("version"), "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * RSS_UNIT / MB, 1),
                      "note": "게이트 값을 이 측정 프로세스 안에서만 열었다. 통과는 품질의 근거가 아니다"}, ensure_ascii=False))


def worker_sqlite_writer(tag, n):
    import mlflow
    ok, errors = 0, {}
    for i in range(n):
        try:
            with mlflow.start_run(run_name=f"probe-{tag}-{i}"):
                mlflow.log_param("probe", tag)
                mlflow.log_metric("value", float(i))
            ok += 1
        except Exception as exc:
            key = type(exc).__name__ + ": " + str(exc).splitlines()[0][:120]
            errors[key] = errors.get(key, 0) + 1
    print(json.dumps({"tag": tag, "ok": ok, "errors": errors}, ensure_ascii=False))


# ───────────────────────────── 저장소 쪽에서 도는 부분 ─────────────────────────────

def environment(project):
    def sh(*cmd):
        r = subprocess.run(cmd, capture_output=True, text=True)
        return r.stdout.strip() if r.returncode == 0 else None

    mem = None
    if sys.platform == "darwin":
        v = sh("sysctl", "-n", "hw.memsize")
        mem = int(v) / MB / 1024 if v else None
    else:
        mem = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / MB / 1024
    disk = shutil.disk_usage(project)
    versions = {}
    for name in ("tensorflow", "mlflow", "numpy", "fastapi", "uvicorn"):
        try:
            from importlib.metadata import version
            versions[name] = version(name)
        except Exception:
            versions[name] = None
    return {
        "measured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "os": f"{platform.system()} {platform.release()}", "machine": platform.machine(),
        "cpu_model": sh("sysctl", "-n", "machdep.cpu.brand_string") if sys.platform == "darwin" else platform.processor(),
        "cpu_logical": os.cpu_count(),
        "cpu_physical": int(sh("sysctl", "-n", "hw.physicalcpu")) if sys.platform == "darwin" else None,
        "memory_gb": round(mem, 1) if mem else None,
        "disk_total_gb": round(disk.total / MB / 1024, 1), "disk_free_gb": round(disk.free / MB / 1024, 1),
        "python": platform.python_version(), "packages": versions,
        "docker": sh("docker", "--version"),
    }


def tree_size_mb(path):
    path = Path(path)
    if path.is_file():
        return round(path.stat().st_size / MB, 2)
    return round(sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / MB, 2) if path.exists() else 0.0


def call_worker(project, *args):
    env = {**os.environ, "PYTHONPATH": str(project), "TF_CPP_MIN_LOG_LEVEL": "2"}
    r = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--worker", *args], cwd=project, env=env, capture_output=True, text=True)
    lines = [l for l in r.stdout.splitlines() if l.startswith("{")]
    if r.returncode != 0 or not lines:
        return {"error": (r.stderr.strip().splitlines() or ["출력이 없다"])[-1][:300], "exit_code": r.returncode}
    return json.loads(lines[-1])


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--project", type=Path, help="검증용 사본의 project/")
    p.add_argument("--out", type=Path)
    p.add_argument("--steps", default="env,baseline,mlflow,memory,latency,finetune,sqlite")
    p.add_argument("--worker", nargs="+", help=argparse.SUPPRESS)
    a = p.parse_args()

    if a.worker:
        kind, rest = a.worker[0], a.worker[1:]
        {"run": lambda: worker_run(rest), "memory": worker_memory, "latency": worker_latency, "finetune": worker_finetune,
         "sqlite": lambda: worker_sqlite_writer(rest[0], int(rest[1]))}[kind]()
        return

    project = a.project.resolve()
    if not (project / "serving_app").is_dir():
        raise SystemExit("--project 는 serving_app/ 이 있는 project/ 폴더여야 한다")
    uploads = sorted((project / "data" / "uploads").glob("*.csv"))
    if not uploads:
        raise SystemExit("사본의 data/uploads/ 에 업로드 파일이 없다. 문서 맨 위의 준비 명령을 먼저 돌린다")
    steps = a.steps.split(",")
    rows = sum(1 for _ in open(uploads[-1], encoding="utf-8-sig")) - 1
    result = {"input": {"upload_file": uploads[-1].name, "rows": rows}}
    if "env" in steps:
        result["env"] = environment(project)
    if "baseline" in steps:
        result["baseline_training"] = call_worker(project, "run", sys.executable, "scripts/train_baseline_v1.py")
        result["baseline_training"]["model_file_mb"] = tree_size_mb(project / "serving_app/models/haic_v1.keras")
    if "mlflow" in steps:
        before = tree_size_mb(project / "mlflow.db") + tree_size_mb(project / "mlruns") + tree_size_mb(project / "mlartifacts")
        result["mlflow_training"] = call_worker(project, "run", sys.executable, "serving_app/train_and_register.py")
        after = tree_size_mb(project / "mlflow.db") + tree_size_mb(project / "mlruns") + tree_size_mb(project / "mlartifacts")
        result["mlflow_training"]["disk_added_mb"] = round(after - before, 2)
    if "memory" in steps:
        result["model_memory"] = call_worker(project, "memory")
    if "latency" in steps:
        result["predict_latency"] = call_worker(project, "latency")
    if "finetune" in steps:
        result["fine_tune"] = call_worker(project, "finetune")
    if "sqlite" in steps:
        env = {**os.environ, "PYTHONPATH": str(project)}
        start = time.time()
        procs = [subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--worker", "sqlite", tag, "30"], cwd=project, env=env,
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True) for tag in ("a", "b")]
        outs = [json.loads([l for l in pr.communicate()[0].splitlines() if l.startswith("{")][-1]) for pr in procs]
        result["sqlite_two_writers"] = {"writers": outs, "seconds": round(time.time() - start, 2),
                                        "note": "두 프로세스가 같은 mlflow.db 에 실행 기록 30건씩을 동시에 쓴다"}

    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(text)
    if a.out:
        a.out.mkdir(parents=True, exist_ok=True)
        (a.out / "single_pc_probe.json").write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
