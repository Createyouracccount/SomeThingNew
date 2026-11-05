# 조사: 결과 기반 피드백 루프 (2026-11-05, 리서치 서브에이전트 보고 요약)

## Claude Code 훅에서 쓸 수 있는 결과 신호
- `Stop`: `last_assistant_message`, `stop_hook_active`; `type: prompt|agent` 훅은 `{ok, reason, impossible}` 반환, agent 훅은 50턴·60초.
- `PostToolUse`: `tool_response`, `duration_ms`; `PostToolUseFailure`: `error`. 둘 다 `additionalContext`(≤10,000자).
- `TaskCompleted`: exit 2 로 완료 차단(공식 예: `npm test` 실패 시).
- 커뮤니티: okl #251 — Stop 훅 교훈 '조작' 측정(특징 없는 과제 풀에서 교훈 수 세기), `found_by` 증거 필드 요구. lessons-learned 플러그인 — 교훈 유/무 2-arm 평가, 2026-06 실행에서 교훈의 ~65% 가 모델 업데이트로 무용(CONTROL_CORRECT).

## 예측 → 검증 (AHE 2604.25850, Self-Harness 2606.09498)
- AHE: 모든 하네스 편집에 change manifest(Evidence/Root Cause/Fix/Predicted Impact). 다음 라운드에 예측 정밀도/재현율 측정(fix-precision 33.7%, recall 51.4% vs 랜덤 6.5/10.6). 실패 예측은 파일 단위 롤백.
- Self-Harness: 약점 채굴 → 9개 표면 한정 YAML 제안 → held-out 64과제×2 회귀 검증 후 승격. "비퇴행만으로는 약한 게이트".
- Phantom Guardrails: 특징 없는 입력에도 15/60 회 가짜 실패 발명 → 증거 기반 게이트·negative control 필요.

## 다음 사용자 턴의 암묵 피드백 (정밀도 수치)
- EMNLP 2025 (2507.23158): Repeat/Rephrase 37%, 교정 18%, LLM 탐지 정밀도 100%/재현율 69%.
- WildFeedback (2408.15549): DSAT 탐지 정밀도 83.3%, 재현율 48.4%; 가장 흔한 불만 = 수정 요청(50.4%).
- 좌절 탐지(2411.17437): 키워드만 쓰면 정밀도 100%/재현율 1%; 마지막 발화만 봐야 성능 유지.
- 개발자 어시스턴트(2509.18361, Google 372명): 프롬프트 감성은 명시적 👍👎의 13배 신호.
- **주의**(2609.02859): LLM 심판은 피드백 기반 수정을 체계적으로 놓침 → 피드백은 '라벨'로만, 심판 재채점 금지.

## 자기 라벨링 (ReasoningBank / ACE / TF-GRPO)
- ReasoningBank: (질문, 궤적, 최종 상태, 출력) → Success/Failure 판정, 성공→전략, 실패→예방 교훈. 심판 정확도 미보고.
- ACE: Reflector 가 bullet 별 helpful/harmful/neutral 태깅, Curator 가 병합·가지치기. 라벨 없이 AppWorld +14.8%.
- RCL(2604.03189): 에이전트가 참고한 playbook 항목을 인용하게 해(dual-trace) 그 항목에만 공로 부여.

## 기존 플러그인의 결과 채점
- **roampal-core**: 유일한 실제 루프. 라벨 worked/partial/unknown/failed, 델타 +0.20/+0.05/−0.05/−0.30, 계층 working→history→patterns(score≥0.9, uses≥3, success≥5). 단 '주 모델에게 점수 묻기' 방식.
- ECC continuous-learning-v2: confidence 임계만 있고 런타임 증감 코드 없음. claude-reflect, lesson-reflex: 교정 수집만.

## self-tuner 반영 (구현 완료)
1. `outcomes.py`: 주입 기록(inject) → 다음 ≤3 프롬프트에서 교정+겹침/재요청 → failed, 새 주제 → worked; Bash 테스트 통과 → worked, 실패+겹침 → failed. roampal 델타 차용, 결정론 규칙만.
2. `lessons.score` 에 결과 보너스 반영. 다중 주입은 델타를 나눔.
3. 리플렉터 교훈은 2개 이상 세션에서 독립 관찰될 때만 rules 뷰에(reSolve 의 독립 재현; Treude&Baltes 의 125→2 결과).
4. 리플렉터 프롬프트: 근거는 다이제스트의 구체 사건을 가리켜야 함(okl `found_by`).

## 미구현(다음)
- AHE 식 `prediction` 필드와 falsifier 이벤트, 예측 정밀도 헬스 지표.
- `claude plugin eval` 로 교훈 제거 control-arm 실행(CONTROL_CORRECT 시 보관).
- Stop `type: agent` 심판(인용된 교훈에만 ±0.1).

출처: https://code.claude.com/docs/en/hooks · https://arxiv.org/abs/2604.25850 · https://arxiv.org/abs/2606.09498 · https://arxiv.org/abs/2607.13083 · https://arxiv.org/abs/2608.27311 · https://arxiv.org/abs/2507.23158 · https://arxiv.org/pdf/2408.15549 · https://arxiv.org/abs/2509.18361 · https://arxiv.org/abs/2609.02859 · https://arxiv.org/html/2509.25140v1 · https://github.com/ace-agent/ace · https://arxiv.org/abs/2604.03189 · https://github.com/roampal-ai/roampal-core · https://github.com/joeblackwaslike/lessons-learned · https://github.com/emeraldleaf/okl/issues/251
