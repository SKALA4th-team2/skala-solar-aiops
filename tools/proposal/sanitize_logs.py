"""검증 실행에서 받은 원본 로그를 증빙으로 둘 수 있게 정리한다.

결과와 오류 문장은 그대로 두고, 읽는 데 방해가 되거나 개인 PC 의 경로가 드러나는 부분만 바꾼다.
무엇을 바꿨는지는 정리본 맨 위에 적는다.

  1. 검증용 사본의 절대 경로, 가상환경 경로, 파이썬 설치 경로를 짧은 표기로 바꾼다.
  2. 오류 추적(traceback)에서 프레임워크 내부 호출은 한 줄로 접는다. 우리 코드의 줄과 마지막 오류 문장은 남긴다.
  3. 학습 진행 막대의 제어 문자를 지운다.
  4. MLflow 라이브러리가 결과와 무관하게 찍는 안내 줄(mlflow.agent.hint)을 지운다.

실행 (저장소 루트에서):
    python tools/proposal/sanitize_logs.py --src <원본 로그 폴더> --out docs/proposal/evidence/logs [--copy-root <검증용 사본의 project 폴더>]
    python tools/proposal/sanitize_logs.py --registry docs/proposal/evidence/registry
    python tools/proposal/sanitize_logs.py --docker <빌드 원본 로그> --out docs/proposal/evidence/logs

--src 는 아래 NAMES 에 적힌 이름의 파일만 옮긴다. 이름은 2026-10-07 의 검증에서 표준 출력을 받아 둔 파일의 것이다.
검증용 사본의 경로는 이름이 verify_run 인 폴더 아래의 project/ 를 알아서 찾는다. 다른 곳에 사본을 두었으면 --copy-root 로 알려 준다.
"""
import argparse
import json
import re
from pathlib import Path

NAMES = {
    "server_lazy_local.log": "01_server_local_lazy.log",
    "train_baseline_haic.log": "02_train_baseline_haic.log",
    "train_register_haic.raw.log": "03_train_register_haic.log",
    "train_baseline_hadong.raw.log": "04_train_baseline_hadong.log",
    "train_register_hadong.raw.log": "05_train_register_hadong.log",
    "simulate_drift.raw.log": "06_simulate_drift.log",
    "server_eager_mlflow.raw.log": "07_server_mlflow_eager.log",
    "server_lazy_mlflow.raw.log": "08_server_mlflow_lazy.log",
    "server_upload_gaps.raw.log": "10_server_upload_gaps.log",
    "server_capture.raw.log": "11_server_capture.log",
    "server_lazy_mlflow_recheck.raw.log": "12_server_mlflow_lazy_recheck.log",
}
EXTRA_ROOTS: list[str] = []      # --copy-root 로 받은 경로

COPY_ROOT = re.compile(r"/[^\s\"']*?/verify_run/project/")
VENV = re.compile(r"/[^\s\"']*?/\.venv/lib/python3\.\d+/site-packages/")
PYLIB = re.compile(r"/[^\s\"']*?/Python\.framework/Versions/3\.\d+/lib/python3\.\d+/")
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
FRAME = re.compile(r'^\s+File "(?P<path>[^"]+)", line \d+, in ')

HEADER = (
    "# 정리본: 경로를 짧은 표기로 바꾸고, 프레임워크 내부 호출을 한 줄로 접고, 진행 막대와 MLflow 안내 줄을 지웠다.\n"
    "# 결과와 오류 문장은 원본 그대로다. 정리 규칙은 tools/proposal/sanitize_logs.py 에 있다.\n"
)


def shorten(line: str) -> str:
    for root in EXTRA_ROOTS:
        line = line.replace(root.rstrip("/") + "/", "(검증용 사본)/project/")
    line = COPY_ROOT.sub("(검증용 사본)/project/", line)
    line = VENV.sub("(가상환경)/site-packages/", line)
    line = PYLIB.sub("(python3.11)/", line)
    return line


def clean(text: str) -> str:
    lines = []
    for raw in text.replace("\r\n", "\n").split("\n"):
        if "\r" in raw or "\x08" in raw:          # 진행 막대는 캐리지 리턴과 백스페이스로 같은 줄을 덮어쓴다
            continue
        raw = ANSI.sub("", raw)
        if "mlflow.agent.hint" in raw:
            continue
        lines.append(shorten(raw))

    out, skipped, i = [], 0, 0
    while i < len(lines):
        m = FRAME.match(lines[i])
        if m and (m["path"].startswith("(가상환경)") or m["path"].startswith("(python3.11)")):
            skipped += 1
            i += 1
            while i < len(lines) and lines[i].startswith("    "):   # 그 프레임의 코드 줄과 밑줄 표시
                i += 1
            continue
        if skipped:
            out.append(f"  ... (프레임워크 내부 호출 {skipped}개 생략)")
            skipped = 0
        out.append(lines[i])
        i += 1
    if skipped:
        out.append(f"  ... (프레임워크 내부 호출 {skipped}개 생략)")
    return "\n".join(out).rstrip("\n") + "\n"


DOCKER_HEADER = (
    "# 정리본: 패키지 내려받기와 설치 진행 줄(단계 #8 의 본문)을 지우고 단계의 시작·끝과 오류만 남겼다.\n"
    "# 남긴 줄은 원본 그대로다. 정리 규칙은 tools/proposal/sanitize_logs.py 에 있다.\n"
)


def clean_docker(text: str) -> str:
    """docker build --progress=plain 의 출력에서 단계의 시작·끝과 오류 단계의 본문만 남긴다."""
    keep = []
    for line in text.split("\n"):
        if line.startswith("#8 ") and not re.match(r"#8 (\[|DONE|ERROR|CACHED)", line):
            continue                                  # pip 의 내려받기·설치 진행
        if line.startswith("View build details"):
            continue                                  # 이 PC 의 Docker Desktop 화면 주소
        keep.append(line[:400])
    out, blank = [], False
    for line in keep:                                 # 빈 줄이 이어지면 하나로 줄인다
        if not line.strip():
            if not blank:
                out.append("")
            blank = True
        else:
            out.append(line)
            blank = False
    return "\n".join(out).rstrip("\n") + "\n"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--src", type=Path)
    p.add_argument("--out", type=Path)
    p.add_argument("--registry", type=Path, help="레지스트리 기록(JSON)의 tracking_uri 에서 절대 경로를 가린다")
    p.add_argument("--docker", type=Path, help="docker build 의 원본 로그")
    p.add_argument("--copy-root", action="append", default=[], help="검증용 사본의 project 폴더의 절대 경로. 여러 번 줄 수 있다")
    a = p.parse_args()
    EXTRA_ROOTS.extend(a.copy_root)

    if a.docker and a.out:
        a.out.mkdir(parents=True, exist_ok=True)
        body = clean_docker(a.docker.read_bytes().decode("utf-8", errors="replace"))
        (a.out / "09_docker_build.log").write_text(DOCKER_HEADER + body, encoding="utf-8")
        print(f"{a.docker.name} -> 09_docker_build.log ({body.count(chr(10))}줄)")

    if a.src and a.out:
        a.out.mkdir(parents=True, exist_ok=True)
        for src_name, dst_name in NAMES.items():
            src = a.src / src_name
            if not src.exists():
                print(f"없음: {src_name}")
                continue
            # 바이트로 읽어야 진행 막대의 캐리지 리턴이 줄바꿈으로 바뀌지 않는다
            body = clean(src.read_bytes().decode("utf-8", errors="replace"))
            (a.out / dst_name).write_text(HEADER + body, encoding="utf-8")
            print(f"{src_name} -> {dst_name} ({body.count(chr(10))}줄)")

    if a.registry:
        for path in sorted(a.registry.glob("registry_*.json")):
            state = json.loads(path.read_text(encoding="utf-8"))
            uri = state.get("tracking_uri")
            if uri:
                state["tracking_uri"] = "sqlite:///" + shorten(uri.removeprefix("sqlite:///"))
                path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                print(f"{path.name}: {state['tracking_uri']}")


if __name__ == "__main__":
    main()
