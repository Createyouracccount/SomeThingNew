---
name: lessons
description: self-tuner 가 축적한 교훈을 보고 관리한다 — 목록 보기, 도움됨/틀림 투표(good/bad), 고정(pin), 보관(archive), 통계. "교훈 목록", "그 교훈 틀렸어", "self-tuner 상태", "/self-tuner:lessons good L1a2b3c4d" 같은 요청에 사용.
argument-hint: "[list|good <id>|bad <id>|pin <id>|archive <id>|stats|curate]"
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/*)
---

# /self-tuner:lessons — 교훈 저장소 관리

교훈은 `~/.claude/plugins/data/self-tuner/lessons.jsonl` 에 id 단위로 저장되고,
전역 상위 항목이 `~/.claude/rules/self-tuner.md` 로 렌더링된다(코드가 생성하는 '뷰'; LLM 이 직접 쓰지 않음).

인자 `$ARGUMENTS` 를 그대로 CLI 에 넘긴다:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/cli.py" $ARGUMENTS
```

- 인자가 없으면 `list` 로 간주한다.
- `good <id>` / `bad <id>`: 사용자의 피드백을 helpful/harmful 카운터에 반영한다(ExpeL 의 UPVOTE/DOWNVOTE). harmful 이 3 이상이고 점수가 0 이하가 되면 자동 보관된다.
- `pin <id>`: 감쇠와 무관하게 항상 상위 유지.
- `stats`: 세션/교훈/리플렉션 통계와 최근 리플렉터 오류를 보여준다.
- 결과를 표로 간단히 요약해 보여주고, 사용자가 자연어로 "저 교훈 틀렸어"라고 하면 해당 id 로 `bad` 를 실행한다.
