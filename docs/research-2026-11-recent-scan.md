# 조사: 최근 3개월(2026-08~11) 자가 개선 하네스·에이전트 메모리 (리서치 서브에이전트 보고 요약)

> arxiv.org 등은 세션 네트워크에서 차단되어 일부 수치는 스니펫 기반(미검증). 로컬에서 `knowledge verify` 로 재확인 권장.

## 설계를 바꾼 발견 3가지
1. **자동 회고는 대부분 노이즈** — Treude & Baltes(2610.34938, 2026-10-26): Claude Code `/retro` 30세션 → 제안 125, 구현 24, 효과 2. 대부분 세션에 근거 없는 일반 lint/CI 조언. → self-tuner: 리플렉터 교훈은 **2세션 독립 관찰** 전까지 잠정, 근거는 구체 사건 필수.
2. **막혔을 때만 주입** — REM(2610.27377): struggle-gated 회상, 비용 −17% 성능 유지; TokenEconomizer(MS, 2610.22732): 반복 실패 루프 차단 + 미사용 도구 정리로 비용 −18~31%. → `on_tool_fail.py` 반복 실패 가드 + 교훈 주입.
3. **백그라운드 비용은 보이게** — claude-mem #2643: 옵저버가 649M 토큰(~$580) 소모. → 리플렉터 비용 기록, 일일 $1 상한.

## 채택(adopt)
- HSE(2610.35616): 반복 실패 서명에서 '복구 스킬' 증류, repo/global 계층. → 후속: lessons category `recovery`.
- 지속 진화의 망각(2611.03219, 2609.04280): 하네스 편집이 과거 능력을 파괴(94→32%). → promote 전 회귀 세트(evals/) 필수.
- HarnessLens(2608.27311): 편집이 겨냥한 실패 사례로만 검증. → promote 평가 케이스는 후보의 실제 예시 프롬프트로.
- WikiSkill(Google, 2608.27454): raw → wiki → skills 3층. → knowledge(wiki) 와 lessons/skills 분리 유지.
- SkillGLoW(2609.02217): 유사 교훈을 '절차 가족'으로 병합, 3.6배 작은 라이브러리. → upsert 병합 임계 유지, weekly 에 중복 병합 제안(후속).
- reSolve(2608.28638): 독립 세션 재현 시에만 스킬 인정. → is_confirmed().
- 스킬 해악 3편(2608.11888, 2608.23067, 2608.14036): 관련해 보이는 스킬도 실패 유발, 토큰 +72~394%; 안티패턴 규칙이 예시형보다 우수; 풀 100개면 검색 정밀도 3.3%. → pitfall 은 "X 말고 Y" 한 줄, 상시 로드 스킬 캡.
- 안전(2608.12851, 2610.00093, 2610.35215, 2608.08303): 자기 기록 파일에 출처·세션·확인 수(provenance), 보이지 않는 문자/태그 중화, 계보 롤백. → `sanitize()`, sources/origin 필드.
- Claude Code 변경: `/skill-doctor`(2.1.261), `claude plugin eval`(2.1.269), `/doctor prompt-audit`(2.1.283), MEMORY.md 중화(2.1.284), 훅 `onFailure: block`(2.1.295), 유휴 컴팩션(2.1.299), Mods(2.1.287).
- Mem0(2026-09-23): 코딩 플러그인은 "도움될 때만 1회 검색". → relevant() 상위 3개 제한 유지.
- Codex 0.165.0(2026-10-27): Claude Code 메모리 import 지원. → 후속: export 형식.

## 관찰(watch)
ContextEvo(2609.34649), Harness²(2610.14224), Evo-Harness(2608.15071), PILOT(2608.26530), Bad Genius 평가 게이밍(2609.18366), DolphinBench(비용 동시 보고), AgentMemBench(장기 회상 붕괴), RD-Forget, PrisMem, Letta MemFS, Agent Skills 표준의 Linux Foundation 이관(2026-10-22).

출처: https://arxiv.org/abs/2610.34938 · https://arxiv.org/abs/2610.27377 · https://arxiv.org/abs/2610.22732 · https://arxiv.org/abs/2610.35616 · https://arxiv.org/abs/2611.03219 · https://arxiv.org/abs/2609.04280 · https://arxiv.org/abs/2608.27311 · https://arxiv.org/abs/2608.27454 · https://arxiv.org/html/2609.02217 · https://arxiv.org/abs/2608.28638 · https://arxiv.org/abs/2608.11888 · https://arxiv.org/abs/2608.23067 · https://arxiv.org/abs/2608.14036 · https://arxiv.org/abs/2608.12851 · https://arxiv.org/abs/2610.00093 · https://github.com/microsoft/TokenEconomizer · https://github.com/thedotmack/claude-mem/issues/2643 · https://www.ajayk.sh/blog/agent-memory-systems-2026/
