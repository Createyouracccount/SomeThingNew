---
name: mine
description: 과거 Claude Code 기록(~/.claude/projects/**/*.jsonl, auto-memory)을 마이닝해 자주 하는 요청 유형, 교정 패턴, 자주 쓰는 도구, 스킬 후보를 리포트한다. 처음 설치했을 때(cold start), 또는 "내가 주로 뭘 시키는지 분석", "스킬 후보 찾아줘", "사용 기록 분석" 요청에 사용.
argument-hint: "[--days N]"
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/*)
---

# /self-tuner:mine — 사용 기록 마이닝 (오프라인 유도, AWM 의 offline induction)

1. 리포트를 생성한다:
   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/mine_history.py" $ARGUMENTS --json "$HOME/.claude/plugins/data/self-tuner/mine.json"
   ```
2. 리포트는 규칙 기반 거친 통계다. 교훈 후보는 **transcript 를 직접 읽고**(`~/.claude/projects/<proj>/*.jsonl` 에서 사용자 턴 몇 개를 Read) 사용자에게 보여준다. 저장은 승인 후 `cli.py add`.
3. **스킬 후보** 섹션의 각 항목에 대해:
   - 왜 스킬이 될 만한지(여러 세션에서 반복, 절차가 정형화 가능) 한 줄로 판단.
   - 스킬이 될 만하면 `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/cli.py" candidate add --intent "<intent>" --keyword "<kw>" --examples "<예시1>|<예시2>"` 로 후보 큐에 넣는다(status=pending).
   - 승격은 `/self-tuner:promote` 가 평가를 거쳐 수행한다. 여기서 바로 스킬을 만들지 않는다(격리: EvoMal 논문 — 에이전트가 만든 스킬은 검토 전엔 검색 가능 상태로 두지 않는다).
4. ECC 포크(또는 다른 스킬 모음)가 로컬에 있으면 맞는 스킬만 추천한다:
   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/cli.py" recommend --ecc-dir <ECC 경로> --top 10
   ```
   경로를 모르면 사용자에게 묻는다(예: `~/dev/ECC`). 통째 설치 대신 추천된 것만 복사하는 이유(설명 ~100KB 상시 로드)를 한 줄로 설명한다.
5. 요청 유형 분포를 보고 `~/.claude/CLAUDE.md` 에 넣을 만한 **상시 지시 1~3줄** 을 제안한다. 단, 실제 편집은 사용자가 승인한 뒤에만.
