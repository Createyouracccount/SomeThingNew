---
name: enforce
description: 반복 확인된 self-tuner 교훈(증거 3회 이상, 반대표 0)을 '권고'에서 '강제'로 올린다 — hookify 가 있으면 위임, 없으면 LLM 평가형(prompt) 훅을 사용자 승인 후 ~/.claude/settings.json 에 추가. "이건 꼭 지키게 해", "훅으로 강제해", "/self-tuner:enforce" 요청에 사용.
argument-hint: "[list | apply <id> | remove <id>]"
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/*)
---

# /self-tuner:enforce — 교훈을 훅으로 강제

근거: 공식 best-practices "CLAUDE.md 지시는 비결정적 가이드. 강조를 반복하게 되면 그 줄은 훅에 들어가야 한다."

## 절차
1. 후보 확인: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/cli.py" enforce list`
   (인자가 없거나 `list` 면 여기서 멈추고 표로 보여준다. 동시 강제 상한은 5개 — prompt 훅은 호출마다 작은 모델 비용이 든다.)
2. 사용자가 고른 교훈에 대해:
   - 출력에 "hookify 설치: 예" 이면 `/hookify` 에게 교훈 문장을 그대로 넘겨 훅을 만들게 하는 것을 **먼저 제안**한다(정규식 기반이라 비용 0).
   - 아니면 `enforce emit <id>` 로 생성될 훅 JSON 을 보여주고, **승인 뒤에만** `enforce apply <id>` 를 실행한다. (settings.json 은 백업 후 수정, 새 세션부터 동작)
3. 범주별 기본 이벤트: pitfall/tool → PreToolUse(Edit|Write|Bash), 그 외 → Stop(continueOnBlock). 사용자가 원하면 `--event`, `--matcher` 로 바꾼다.
4. 강제된 교훈은 rules 뷰에서 자동 제외된다(중복 방지). 해제는 `enforce remove <id>`.
