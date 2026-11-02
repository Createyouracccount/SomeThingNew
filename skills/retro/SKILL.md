---
name: retro
description: 지금 세션(또는 지정한 세션)을 돌아보며 다음에도 쓸 교훈을 뽑아 self-tuner 저장소에 델타로 추가한다. "회고", "retro", "이 세션에서 배운 거 저장", "교훈 정리" 같은 요청에 사용. 자동 리플렉터(Stop 훅)와 달리 사용자가 각 교훈을 승인한다.
argument-hint: "[session-id]"
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/*)
---

# /self-tuner:retro — 사람이 승인하는 회고

이 스킬은 ACE 논문의 Reflector 역할을 **대화 안에서** 수행한다. 자동 리플렉터와 다른 점은
사용자가 각 교훈을 보고 승인한다는 것(업계 공통 패턴: 에이전트는 *제안*, 사람이 *승격*).

## 절차

1. 현재 세션의 다이제스트를 만든다:
   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/reflect.py" --session "${CLAUDE_SESSION_ID}" --dry-run
   ```
   (`$ARGUMENTS` 에 세션 id 가 있으면 그 값을 `--session` 에 쓴다.)
2. 다이제스트 **와 이 대화의 실제 내용** 을 함께 보고 교훈 후보를 0~5개 뽑는다.
   - 교훈이 없으면 "이번 세션엔 저장할 교훈이 없습니다"라고 말하고 끝낸다. 억지로 만들지 않는다.
   - 코드베이스에서 읽어낼 수 있는 사실은 교훈이 아니다. 사용자의 선호·교정·반복 작업 방식·도구 함정만.
   - 각 후보: 한국어 한 문장(≤120자, 명령형) / category(preference|workflow|pitfall|tool|domain|project) / scope(global|project) / 근거.
3. 후보를 번호 목록으로 보여주고 어떤 것을 저장할지 묻는다.
4. 승인된 것만 저장한다. 각 항목마다:
   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/cli.py" add --text "..." --category workflow --scope global --source "${CLAUDE_SESSION_ID}" --rationale "..."
   ```
   (project 범위면 `--scope "project:<git 루트 폴더명>"`)
5. 마지막에 `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/cli.py" curate` 로 `~/.claude/rules/self-tuner.md` 를 갱신하고, 추가/병합된 개수를 보고한다.
