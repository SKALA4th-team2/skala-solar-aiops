"""기획서와 결정 기록의 문서를 기계로 점검한다.

  1. 링크: 가리키는 파일이 있는가. `#` 뒤의 위치가 그 문서의 제목에 있는가
  2. 그림: 가리키는 그림 파일이 있는가
  3. 표: 줄마다 칸의 수가 머리 줄과 같은가
  4. JSON 예시: ```json 블록이 올바른 JSON 인가
  5. 증빙: docs/proposal/evidence/ 의 파일 가운데 어느 문서도 가리키지 않는 것이 있는가
  6. 검증 번호: 문서가 가리키는 검증 번호(V01 ...)가 검증 기록에 있는가
  7. 보관 문서: docs/research/ 에 커밋되지 않은 변경이 있는가

실행 (저장소 루트에서):
    python tools/proposal/check_docs.py
결과: docs/proposal/evidence/docs_check.txt. 문제가 있으면 종료 코드 1
"""
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs" / "proposal" / "evidence"
DOCS = (sorted((ROOT / "docs" / "proposal").glob("*.md")) + [EVIDENCE / "validation.md"]
        + sorted((ROOT / "docs" / "decisions").glob("*.md")) + [ROOT / "docs" / "followups.md", ROOT / "datasets" / "README.md",
                                                                 ROOT / "tools" / "proposal" / "README.md"])
DOCS = [d for d in DOCS if d.exists()]

LINK = re.compile(r"(!?)\[([^\]]*)\]\(([^)\s]+)\)")
FENCE = re.compile(r"^```(\w*)\s*$")
problems, notes = [], []


def slug(heading: str) -> str:
    """GitHub 가 제목에서 만드는 위치 이름. 소문자로 바꾸고, 글자·숫자·밑줄·붙임표·빈칸만 남기고, 빈칸을 붙임표로 바꾼다."""
    text = re.sub(r"`([^`]*)`", r"\1", heading.strip())
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    out = []
    for ch in text.lower():
        cat = unicodedata.category(ch)
        if ch in "-_ " or cat[0] in "LN" or cat in ("Mn", "Mc"):
            out.append(ch)
    return "".join(out).replace(" ", "-")


def parse(path: Path):
    """코드 블록 밖의 줄, 제목의 위치 이름, 코드 블록을 나눠 돌려준다."""
    plain, headings, blocks = [], [], []
    seen, lang, buf = {}, None, []
    for n, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
        m = FENCE.match(line)
        if m and lang is None:
            lang, buf, start = m.group(1) or "text", [], n
            continue
        if line.startswith("```") and lang is not None:
            blocks.append((lang, start, "\n".join(buf)))
            lang = None
            continue
        if lang is not None:
            buf.append(line)
            continue
        plain.append((n, line))
        h = re.match(r"^(#{1,6})\s+(.*)$", line)
        if h:
            s = slug(h.group(2))
            k = seen.get(s, 0)
            seen[s] = k + 1
            headings.append(s if k == 0 else f"{s}-{k}")
    return plain, headings, blocks


parsed = {d: parse(d) for d in DOCS}
referenced = set()
v_defined = set(parsed[EVIDENCE / "validation.md"][1]) if (EVIDENCE / "validation.md") in parsed else set()
counts = {"links": 0, "images": 0, "tables": 0, "json": 0, "mermaid": 0}

for doc, (plain, headings, blocks) in parsed.items():
    rel = doc.relative_to(ROOT)
    # 1, 2. 링크와 그림
    for n, line in plain:
        for bang, _, target in LINK.findall(line):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            counts["images" if bang else "links"] += 1
            path_part, _, anchor = target.partition("#")
            dest = (doc.parent / path_part).resolve() if path_part else doc
            if not dest.exists():
                problems.append(f"{rel}:{n}: 없는 파일을 가리킨다: {target}")
                continue
            if EVIDENCE in dest.parents or dest == EVIDENCE:
                referenced.add(dest)
            if anchor:
                if dest.suffix != ".md":
                    problems.append(f"{rel}:{n}: 문서가 아닌 파일에 위치를 붙였다: {target}")
                else:
                    hs = parsed[dest][1] if dest in parsed else parse(dest)[1]
                    if anchor not in hs:
                        problems.append(f"{rel}:{n}: 없는 위치를 가리킨다: {target}")
    # 3. 표
    table = []
    for n, line in plain + [(0, "")]:
        if line.startswith("|"):
            table.append((n, line))
            continue
        if len(table) > 1 and re.search(r"\|\s*:?-{3}", table[1][1]):
            counts["tables"] += 1
            width = len(re.split(r"(?<!\\)\|", table[0][1])) - 2
            for j, row in table[1:]:
                w = len(re.split(r"(?<!\\)\|", row)) - 2
                if w != width:
                    problems.append(f"{rel}:{j}: 표의 칸 수가 {w} 로 머리 줄({width})과 다르다")
        table = []
    # 4. JSON 예시
    for lang, start, body in blocks:
        if lang == "json":
            counts["json"] += 1
            try:
                json.loads(body)
            except json.JSONDecodeError as e:
                problems.append(f"{rel}:{start}: JSON 예시가 올바르지 않다: {e}")
        if lang == "mermaid":
            counts["mermaid"] += 1

# 5. 어느 문서도 가리키지 않는 증빙
for f in sorted(EVIDENCE.rglob("*")):
    if f.is_file() and f.name not in {".gitkeep", "validation.md", "docs_check.txt"} and f not in referenced:
        if any(p in referenced for p in f.parents):      # 폴더를 통째로 가리킨 경우
            continue
        notes.append(f"가리키는 문서가 없는 증빙: {f.relative_to(ROOT)}")

# 6. 검증 번호
for doc, (plain, _, _) in parsed.items():
    for n, line in plain:
        for v in re.findall(r"validation\.md#(v\d+)", line):
            if v not in v_defined:
                problems.append(f"{doc.relative_to(ROOT)}:{n}: 검증 기록에 없는 번호: {v}")

# 7. 보관 문서
dirty = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--", "docs/research", "tools/verify", "tools/jeokryang", "project"],
                       capture_output=True, text=True).stdout.strip()
if dirty:
    problems.append("보관 문서나 서빙 앱에 커밋되지 않은 변경이 있다:\n" + dirty)

out = [f"점검한 문서 {len(DOCS)}개: 링크 {counts['links']}개, 그림 {counts['images']}개, 표 {counts['tables']}개, JSON 예시 {counts['json']}개, Mermaid 그림 {counts['mermaid']}개",
       f"문제 {len(problems)}건"]
out += ["  " + p for p in problems]
out += [f"참고 {len(notes)}건"] + ["  " + s for s in notes]
out.append("docs/research, tools/verify, tools/jeokryang, project 에 커밋되지 않은 변경: " + ("있음" if dirty else "없음"))
(EVIDENCE / "docs_check.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
print("\n".join(out))
sys.exit(1 if problems else 0)
