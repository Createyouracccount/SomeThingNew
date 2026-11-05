---
name: weekly
description: self-tuner 주간 유지보수 — 지난 7일 통계, 오래 안 쓰인 교훈 보관 제안, 훅 강제 후보, 대기 스킬 후보, /skill-doctor·/doctor prompt-audit 권장. "주간 점검", "self-tuner 정리", "/self-tuner:weekly" 요청이나 예약 작업에서 사용.
argument-hint: "[--apply]"
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/*)
---

# /self-tuner:weekly — 주간 유지보수

1. `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/cli.py" weekly $ARGUMENTS` 를 실행하고 결과를 그대로 보여준다.
2. "보관 제안" 이 있으면 사용자에게 적용 여부를 묻고, 승인 시 `weekly --apply` 로 재실행한다.
3. "훅 강제 후보" 가 있으면 `/self-tuner:enforce` 로 이어갈지 묻는다.
4. 마지막에 `/skill-doctor` 와 `/doctor prompt-audit` 를 이번 세션에서 바로 실행할지 묻는다(둘 다 Claude Code 내장).

예약 실행: Desktop 예약 작업이나 `~/.claude/loop.md` 에 "`/self-tuner:weekly` 를 실행하고 보관 제안은 적용하지 말고 요약만" 을 넣으면 주 1회 자동.
