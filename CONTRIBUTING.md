# Contributing to skala-solar-aiops

팀원이 처음 합류할 때 한 번 읽으면 되는 최소한만 담는다.

**상세 규칙은 [`AGENTS.md`](AGENTS.md)에 있다.** 무엇을 어디에 두는지, 함께 맞춰야 하는 숫자의 묶음, 수치를 적는 규칙이 거기 있다. 이 문서와 내용이 다르면 `AGENTS.md` 가 맞다. [`CLAUDE.md`](CLAUDE.md)는 `AGENTS.md` 와 같은 문서다.

## 처음 한 번만

```bash
cd project
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

커밋 양식을 쓰려면 저장소 루트에서 한 번 실행한다.

```bash
git config commit.template .gitmessage
```

## 작업 흐름

발표까지 시간이 짧아 절차를 줄였다. 팀이 다르게 정하면 이 절을 고친다([`docs/followups.md`](docs/followups.md) 2번).

```bash
git switch main
git pull --ff-only
git switch -c feat/short-description
```

작업 → 커밋 → push → PR → Squash merge → 브랜치 삭제.

- 브랜치는 `feat/` `fix/` `docs/` `chore/` `refactor/` `test/` 중 하나로 시작한다.
- 커밋과 PR 제목은 `type(scope): 요약` 형식으로 쓴다.
- 시작하기 전에 [`README.md`](README.md)의 팀 표에 맡은 것을 적는다. 같은 파일을 두 사람이 동시에 고치면 발표 전날에 충돌을 풀게 된다.

## 승인

리뷰할 수 있는 팀원이 있으면 한 명의 승인을 받는다. 시간이 없으면 본인이 merge 하되, PR 본문에 직접 확인한 것과 확인하지 못한 것을 나눠 적는다.

## 반드시 지킬 것

- 비밀값(`.env`)과 실행 산출물(모델 파일, `mlflow.db`, 로그, 업로드 파일)을 커밋하지 않는다.
- `project/` 의 폴더 구조를 바꾸지 않는다.
- 게이트나 드리프트 기준 같은 숫자를 바꾸면 `AGENTS.md` 의 표에 적힌 곳을 함께 맞춘다.
- 직접 실행해 얻지 않은 수치를 결과로 적지 않는다.
- 하나의 PR 은 하나의 목적만 다룬다.
