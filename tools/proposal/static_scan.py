"""project/ 의 코드를 읽기만 해서, 기획서가 "현재 구현"이라고 적는 내용의 근거를 뽑는다.

  1. 남아 있는 빈칸(`___`)의 위치
  2. 정책을 정하는 상수와 그 값
  3. 주가 예측(HAIC) 표현이 남아 있는 곳의 수
  4. 승격 뒤 서빙 모델을 바꾸는 코드가 있는지

실행 (저장소 루트에서):
    python tools/proposal/static_scan.py
결과: docs/proposal/evidence/static_scan.json, static_scan.txt
"""
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "project"
OUT = ROOT / "docs" / "proposal" / "evidence"

CODE_FILES = sorted(
    p for p in PROJECT.rglob("*")
    if p.is_file() and p.suffix in {".py", ".html", ".yml"} or p.name == "Dockerfile"
)

BLANK = re.compile(r"(?<![A-Za-z0-9_])___(?![A-Za-z0-9_])")
CONSTANTS = {
    "serving_app/train_and_register.py": ["RMSE_GATE", "MODEL_NAME", "BASE_EPOCHS", "FINE_TUNE_EPOCHS", "FINE_TUNE_LR", "SEED"],
    "serving_app/monitoring/drift_detector.py": ["RMSE_THRESHOLD", "WINDOW_SIZE"],
    "data/features.py": ["SEQ_LEN"],
    "serving_app/lstm_model.py": ["N_FEATURES"],
    "serving_app/routers/predict.py": ["SIMULATED_VOLUME"],
    "serving_app/routers/data.py": ["REQUIRED_COLUMNS", "MIN_ROWS"],
    "serving_app/model_loader.py": ["MLFLOW_MODEL_URI", "LOCAL_MODEL_PATH", "SCALER_PATH"],
    "scripts/simulate_drift.py": ["BATCH_N", "NORMAL_SIGMA", "DRIFT_SIGMA"],
}
HAIC_WORDS = ["HAIC", "종가", "거래일", "거래량", "달러", "$4", "주가"]


def rel(p: Path) -> str:
    return p.relative_to(PROJECT).as_posix()


def code_lines(path: Path):
    """주석과 문서 문자열을 뺀, 실제로 실행되는 줄만 (줄 번호, 내용)."""
    text = path.read_text(encoding="utf-8")
    if path.suffix != ".py":
        return [(i, l) for i, l in enumerate(text.split("\n"), 1)]
    out, in_doc = [], False
    for i, line in enumerate(text.split("\n"), 1):
        s = line.strip()
        quotes = s.count('"""')
        if in_doc:
            if quotes:
                in_doc = False
            continue
        if s.startswith('"""'):
            if quotes == 1:
                in_doc = True
            continue
        if s.startswith("#") or not s:
            continue
        out.append((i, line.split("  #")[0].rstrip()))
    return out


result = {"commit": subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()}
dirty = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--", "project"], capture_output=True, text=True).stdout.strip()
result["project_dir_modified"] = bool(dirty)

# 1. 빈칸
blanks = []
for p in CODE_FILES:
    if p.suffix != ".py":
        continue
    for i, line in code_lines(p):
        n = len(BLANK.findall(line))
        if n:
            blanks.append({"file": rel(p), "line": i, "count": n, "code": line.strip()})
result["blanks"] = blanks
result["blank_lines"] = len(blanks)
result["blank_marks"] = sum(b["count"] for b in blanks)

# 2. 상수
consts = []
for f, names in CONSTANTS.items():
    lines = dict(code_lines(PROJECT / f))
    for name in names:
        hit = [(i, l) for i, l in lines.items() if re.match(rf"^{name}\s*=", l)]
        consts.append({"file": f, "name": name, "line": hit[0][0] if hit else None, "code": hit[0][1].strip() if hit else None})
html = (PROJECT / "serving_app/static/index.html").read_text(encoding="utf-8")
for name in ["WINDOW_SIZE", "RMSE_THRESHOLD", "DEFAULT_BASE_PRICE"]:
    m = re.search(rf"(?:const|let|var)\s+{name}\s*=\s*([^;]+);", html)
    line = html[: m.start()].count("\n") + 1 if m else None
    consts.append({"file": "serving_app/static/index.html", "name": name, "line": line, "code": m.group(0).strip() if m else None})
result["constants"] = consts

# 3. 주가 예측 표현
words = {}
for w in HAIC_WORDS:
    per_file = {}
    for p in CODE_FILES + [PROJECT / "README.md"]:
        n = p.read_text(encoding="utf-8").count(w)
        if n:
            per_file[rel(p)] = n
    words[w] = {"total": sum(per_file.values()), "files": per_file}
result["haic_wording"] = words

# 4. 승격 뒤 서빙 모델 갱신
cache_refs = []
for p in CODE_FILES:
    if p.suffix != ".py":
        continue
    for i, line in code_lines(p):
        if "_model_cache" in line:
            cache_refs.append({"file": rel(p), "line": i, "code": line.strip()})
result["model_cache_refs"] = cache_refs
result["model_cache_written_outside_loader"] = [
    r for r in cache_refs if r["file"] != "serving_app/model_loader.py" and re.search(r"_model_cache\s*=", r["code"])
]
loader = dict(code_lines(PROJECT / "serving_app/model_loader.py"))
result["version_strings"] = [{"line": i, "code": l.strip()} for i, l in loader.items() if "version=" in l and "LoadedModel(" in l]

OUT.mkdir(parents=True, exist_ok=True)
(OUT / "static_scan.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

t = [f"커밋 {result['commit']}, project/ 에 커밋되지 않은 변경: {'있음' if result['project_dir_modified'] else '없음'}", ""]
t.append(f"[1] 남아 있는 빈칸: {result['blank_lines']}줄, ___ {result['blank_marks']}개")
for b in blanks:
    t.append(f"  {b['file']}:{b['line']}  ({b['count']}개)  {b['code']}")
t += ["", "[2] 정책을 정하는 상수"]
for c in consts:
    t.append(f"  {c['file']}:{c['line']}  {c['code']}")
t += ["", "[3] 주가 예측 표현이 남은 곳 (낱말이 나온 횟수)"]
for w, v in words.items():
    t.append(f"  {w}: {v['total']}회, 파일 {len(v['files'])}개")
t += ["", "[4] 모델 캐시(_model_cache)를 건드리는 코드"]
for r in cache_refs:
    t.append(f"  {r['file']}:{r['line']}  {r['code']}")
t.append(f"  model_loader.py 밖에서 캐시를 바꾸는 줄: {len(result['model_cache_written_outside_loader'])}개")
t += ["", "[5] 응답의 model_version 이 되는 값"]
for v in result["version_strings"]:
    t.append(f"  serving_app/model_loader.py:{v['line']}  {v['code']}")
(OUT / "static_scan.txt").write_text("\n".join(t) + "\n", encoding="utf-8")
print("\n".join(t))
