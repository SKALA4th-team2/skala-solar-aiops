"""검증에 쓴 환경을 적는다: 저장소의 커밋, 운영체제, 파이썬과 패키지 버전, 컨테이너 도구.

서빙과 학습에 쓴 파이썬으로 돌린다. 그래야 그 파이썬의 패키지 버전이 project/requirements.txt 와 같은지 대조된다.
개인 PC 의 절대 경로는 적지 않는다.

실행 (저장소 루트에서):
    <서빙에 쓴 파이썬> tools/proposal/record_environment.py [--compose-dir <검증용 사본의 project 폴더>] [--image <확인할 이미지 이름>]
결과: docs/proposal/evidence/environment.txt
"""
import argparse
import datetime as dt
import importlib.metadata as md
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "proposal" / "evidence" / "environment.txt"

p = argparse.ArgumentParser()
p.add_argument("--compose-dir", type=Path, help="docker compose config 를 돌릴 project 폴더(검증용 사본)")
p.add_argument("--image", default="solar-aiops-verify:58d6ff8", help="빌드가 실패한 뒤 이미지가 없는지 확인할 이름")
a = p.parse_args()


def run(cmd, cwd=None):
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=60)
        return (r.stdout + r.stderr).strip()
    except Exception as e:      # 도구가 없으면 그 사실을 적는다
        return f"(실행하지 못함: {e})"


lines = ["# 검증 환경 기록", f"기록 시각: {dt.datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %z')}",
         "만든 방법: tools/proposal/record_environment.py", ""]

lines += ["[저장소]",
          f"커밋: {run(['git', '-C', str(ROOT), 'rev-parse', '--short', 'HEAD'])} ({run(['git', '-C', str(ROOT), 'log', '-1', '--format=%s'])})"]
dirty = run(["git", "-C", str(ROOT), "status", "--porcelain", "--", "project"])
lines += [f"project/ 에 커밋되지 않은 변경: {len([x for x in dirty.splitlines() if x.strip()])}개",
          f"project/.venv 존재 여부: {'있음' if (ROOT / 'project' / '.venv').is_dir() else '없음'}", ""]

mac = platform.mac_ver()[0]
lines += ["[운영체제]", f"{'macOS ' + mac if mac else platform.system()}, {platform.machine()}, {platform.system()} {platform.release()}", ""]

inside_repo = str(Path(sys.executable).resolve()).startswith(str(ROOT))
lines += ["[이 스크립트를 돌린 파이썬] " + ("저장소의 project/.venv" if inside_repo else "저장소 밖의 가상환경(개인 실습 폴더의 것)"),
          f"python {platform.python_version()}"]
req = {}
for line in (ROOT / "project" / "requirements.txt").read_text(encoding="utf-8").splitlines():
    if "==" in line:
        name, ver = line.strip().split("==")
        req[name.split("[")[0]] = ver
for name, want in req.items():
    try:
        got = md.version(name)
        lines.append(f"{name}=={got}  (requirements.txt: {want}, {'일치' if got == want else '불일치'})")
    except md.PackageNotFoundError:
        lines.append(f"{name}: 설치돼 있지 않음  (requirements.txt: {want})")
for extra in ("keras", "starlette", "httptools", "websockets", "pandas"):
    try:
        lines.append(f"{extra}=={md.version(extra)}  (requirements.txt 에 직접 적히지 않은 패키지)")
    except md.PackageNotFoundError:
        pass
lines.append("")

lines += ["[컨테이너 도구]", run(["docker", "version", "--format", "docker client {{.Client.Version}}, server {{.Server.Version}}"]),
          run(["docker", "compose", "version"]), ""]
found = run(["docker", "images", "--format", "{{.Repository}}:{{.Tag}}", a.image])
lines += [f"[docker images {a.image}] 빌드가 실패한 뒤 이미지가 남아 있는지", found if found else "(해당 이름의 이미지 없음)", ""]

if a.compose_dir:
    out = run(["docker", "compose", "-f", "serving_app/docker-compose.yml", "config"], cwd=a.compose_dir)
    out = out.replace(str(a.compose_dir.resolve().parent), "(검증용 사본)").replace(str(a.compose_dir.parent), "(검증용 사본)")
    lines += ["[docker compose -f serving_app/docker-compose.yml config] 검증용 사본의 project/ 에서 실행. 경로만 짧게 바꿨다", out, ""]

OUT.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")
print("\n".join(lines))
