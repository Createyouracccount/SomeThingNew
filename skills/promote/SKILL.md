---
name: promote
description: self-tuner 의 스킬 후보(반복 요청 패턴)를 검토해 실제 개인 스킬(~/.claude/skills/<name>/SKILL.md)로 만들고, 평가 케이스를 붙여 `claude plugin eval` 의 with/without 비교로 효과가 있을 때만 유지한다. "스킬 후보 승격", "이 패턴 스킬로 만들어", "/self-tuner:promote" 요청에 사용.
argument-hint: "[candidate-id | list]"
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/*), Bash(claude plugin *), Read, Write, Edit
---

# /self-tuner:promote — 후보 → 검증된 스킬

핵심 원칙(연구 근거): Voyager/SkillWeaver — **성공이 검증된 절차만 스킬로 인정**; gskill/Self-Harness — **테스트 신호로 스킬 텍스트를 최적화**; DGM — **측정상 개선될 때만 채택**.

## 절차

1. 후보 목록: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/cli.py" candidate list`
   인자가 `list` 이거나 없으면 목록만 보여주고 어떤 것을 승격할지 묻는다.
2. 선택된 후보의 예시 프롬프트들을 읽고, 다음을 사용자와 합의한다:
   - 스킬 이름(kebab-case), 트리거 설명(description: 사용자가 실제로 치는 말투로), 절차(3~8단계), 입력 인자.
3. **격리 디렉터리** 에 초안을 만든다: `~/.claude/plugins/data/self-tuner/staging/<name>/` 아래
   `.claude-plugin/plugin.json`(name=<name>), `skills/<name>/SKILL.md`, `evals/<case>/prompt.md`, `evals/<case>/graders/*.md`.
   - 평가 케이스는 후보의 실제 예시 프롬프트 2~3개로 만든다(각각 하나의 case).
   - 그레이더: `llm`(PASS/FAIL 기준을 구체적으로) + `tool_used`(Skill 호출 확인; with-only 지표).
   - 포맷은 공식 문서를 따른다: prompt.md frontmatter `max_turns`, `allowed_tools`; graders/<name>.md frontmatter `type`.
4. 평가 실행: `claude plugin eval "$HOME/.claude/plugins/data/self-tuner/staging/<name>" --ablation with-without --threshold 0.67`
   - Δ(WITH − W/OUT) 가 0 이하이면: 스킬 설명/절차를 고쳐 **한 번 더** 시도. 그래도 안 되면 후보를 `candidate reject <id>` 로 닫고 이유를 기록한다(가짜 개선 금지).
   - Δ > 0 이고 WITH ≥ threshold 면 승격.
5. 승격: `skills/<name>/` 를 `~/.claude/skills/<name>/` 로 복사하고(`cp -r`), `candidate promote <id> --skill <name>` 로 상태 갱신. 평가 결과 요약(WITH/W/OUT/Δ/비용)을 함께 기록한다.
6. 사용자에게: 새 스킬 호출법, 평가 수치, 다음 번 재평가 시점(기본 30일 뒤 `/skill-doctor` 로 미사용이면 제거 권고)을 보고한다.
