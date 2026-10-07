"""tools/verify/ 의 기존 검증 스크립트 셋을 다시 돌려, 저장소에 보관된 결과와 같은지 견준다.

기획서가 인용한 조사 수치의 재현 스크립트가 지금의 저장소에서도 같은 값을 내는지 확인하려는 것이다.
보관된 결과 파일은 덮어쓰지 않는다. 결과 JSON 을 스크립트 옆에 쓰는 t5_independent_audit.py 는 임시 폴더에 복사해 돌린다.

실행 (저장소 루트에서, numpy 와 pandas 가 있는 파이썬으로):
    python tools/proposal/rerun_existing_checks.py
결과: docs/proposal/evidence/existing_checks_rerun.txt
"""
import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERIFY = ROOT / "tools" / "verify"
OUT = ROOT / "docs" / "proposal" / "evidence" / "existing_checks_rerun.txt"
TOL = 1e-9
lines = []


def say(s=""):
    print(s)
    lines.append(s)


def leaves(obj, prefix=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from leaves(v, f"{prefix}/{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from leaves(v, f"{prefix}/{i}")
    else:
        yield prefix, obj


def same(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) and not isinstance(b, bool):
        if isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b):
            return True
        return abs(a - b) <= TOL * max(1.0, abs(a), abs(b))
    return a == b


def compare(old, new):
    lo, ln = dict(leaves(old)), dict(leaves(new))
    diff = [k for k in sorted(set(lo) | set(ln)) if k not in lo or k not in ln or not same(lo[k], ln[k])]
    return len(lo), diff


# 1. verify_t3t4.py: 표준 출력의 "이름 JSON" 줄을 보관된 로그와 견준다
r = subprocess.run([sys.executable, str(VERIFY / "verify_t3t4.py"), "--root", str(ROOT)], capture_output=True, text=True)
say(f"[1] verify_t3t4.py --root .  종료 코드 {r.returncode}")


def parse(text):
    out = {}
    for line in text.splitlines():
        i = line.find("{")
        if i > 0:
            try:
                out[line[:i].strip()] = json.loads(line[i:])
            except json.JSONDecodeError:
                out[line] = None
    return out


old, new = parse((VERIFY / "verify_t3t4.log").read_text(encoding="utf-8")), parse(r.stdout)
n, diff = compare(old, new)
say(f"    보관된 로그의 값 {n}개 가운데 다른 값 {len(diff)}개 (숫자는 상대 오차 {TOL:g} 안이면 같다고 봄)")
for d in diff[:10]:
    say(f"    다름: {d}")

# 2. t5_independent_audit.py: 임시 폴더에서 돌리고 결과 JSON 을 보관된 것과 견준다
with tempfile.TemporaryDirectory() as tmp:
    script = Path(tmp) / "t5_independent_audit.py"
    shutil.copy(VERIFY / "t5_independent_audit.py", script)
    r = subprocess.run([sys.executable, str(script), str(ROOT)], capture_output=True, text=True)
    say(f"[2] t5_independent_audit.py (임시 폴더에서)  종료 코드 {r.returncode}")
    if r.returncode == 0:
        new = json.loads((Path(tmp) / "t5_audit_results.json").read_text(encoding="utf-8"))
        old = json.loads((VERIFY / "t5_audit_results.json").read_text(encoding="utf-8"))
        n, diff = compare(old, new)
        say(f"    보관된 결과의 값 {n}개 가운데 다른 값 {len(diff)}개")
        for d in diff[:10]:
            say(f"    다름: {d}")
        inj = new["injection"]
        say(f"    기준선: 2021-04-01 까지 {new['baselines']['2021-04-01']['clipped'][0]:.6f}, 2025-02-28 까지 {new['baselines']['2025-02-28']['clipped'][0]:.6f}")
        say(f"    0.86 주입에서 -7.5% 아래인 배치: 주입 직전 기준선 {inj['0.86']['per_start_baseline_detect_pct']:.2f}%, 고정 기준선 {inj['0.86']['frozen_train_baseline_detect_pct']:.2f}%")
    else:
        say("    " + r.stderr.strip().splitlines()[-1])

# 3. validate_audit_artifacts.py: 읽기만 한다
r = subprocess.run([sys.executable, str(VERIFY / "validate_audit_artifacts.py"), "--repo", str(ROOT)], capture_output=True, text=True)
say(f"[3] validate_audit_artifacts.py --repo .  종료 코드 {r.returncode}")
try:
    res = json.loads(r.stdout)
    say(f"    문서 {res['documents']}개, 스크립트 {res['compiled_scripts']}개, JSON {res['parsed_json']}개, 오류 {len(res['errors'])}개")
    for e in res["errors"][:10]:
        say(f"    오류: {e}")
except json.JSONDecodeError:
    say("    " + r.stdout.strip()[:300])

OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
