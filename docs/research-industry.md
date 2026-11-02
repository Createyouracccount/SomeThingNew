# 업계·커뮤니티 조사: 코딩 에이전트가 하네스로 '학습'하는 방식 (2026-11-02 기준)

> 리서치 서브에이전트 보고서 요약(영문 원문 기반). 일부 벤더 문서는 샌드박스 네트워크 정책으로 직접 열지 못해 검색 스니펫·2차 출처에 의존함.

## 1. Anthropic Claude Code (공식)
- **지시 파일 계층**: managed CLAUDE.md → `~/.claude/CLAUDE.md` → `./CLAUDE.md`(상위 디렉터리 포함) → `CLAUDE.local.md`. `.claude/rules/*.md`, `~/.claude/rules/` 는 모듈형 규칙, `paths:` frontmatter 로 경로 범위 지정. 권고: 파일당 200줄 이하. `/doctor prompt-audit` 가 모순·구식 지시 탐지, `InstructionsLoaded` 훅이 로드 로그. 공식 best-practices: "강조를 계속 추가하게 되면 그 줄은 훅에 들어가야 한다" — CLAUDE.md는 비결정적 가이드, 반드시 지킬 것은 훅/deny 규칙으로.
- **Auto memory** (v2.1.59+, 2026-02): `~/.claude/projects/<proj>/memory/MEMORY.md`(인덱스, 첫 200줄/25KB만 로드) + 토픽 파일. type: user/feedback/project/reference. 서브에이전트는 `memory: user|project|local` 로 별도 메모리. 알려진 문제: [#85075](https://github.com/anthropics/claude-code/issues/85075) 오래된 메모리가 신선도 신호 없이 로드, [#75334](https://github.com/anthropics/claude-code/issues/75334) 메모리가 권고일 뿐 같은 실수 반복.
- **Skills**: SKILL.md + frontmatter(`context: fork`, `hooks`, `paths`, `when_to_use`…). 설명만 상시 로드(1,536자 캡), 본문은 호출 시. `/skill-doctor`(v2.1.252+) 가 스킬별 컨텍스트 비용·미사용 스킬 보고. `skill-creator` 플러그인(evals.json) 과 `claude plugin eval`(with/without 비교, CI 게이트).
- **Hooks**: 30여 이벤트, `command|http|mcp_tool|prompt|agent` 타입. `additionalContext` 로 주입(≤10,000자), Stop `decision: block` 으로 계속 작업 강제, `${CLAUDE_PLUGIN_DATA}` 에 영속 상태.
- **플러그인 마켓**: 공식 마켓 315개. 관련: `skill-creator`, `superpowers`, `ralph-loop`, `claude-md-management`(`/revise-claude-md` 가 세션 학습 반영), `remember`, `claude-code-setup`. **Mods**(v2.1.287+): in-process JS 훅 모듈. `/goal` = 세션 범위 prompt형 Stop 훅. `/usage`, `/insights`(30일 transcript 분석 → CLAUDE.md 제안; 공식 문서 인덱스엔 없음).
- **엔지니어링 블로그**: Effective context engineering(2025-09), Code execution with MCP(2025-11, 에이전트가 동작하는 코드를 skills 폴더에 저장), Effective harnesses for long-running agents(2025-11, progress 파일·JSON 피처 리스트·git as memory), Harness design for long-running apps(2026-03, planner/generator/evaluator 분리 — 에이전트는 자기 작업을 과대평가), Managed Agents(2026-04).

## 2. OpenAI Codex
AGENTS.md 체인(`~/.codex/AGENTS.md` → repo → 하위, 32KiB 캡). Skills: `~/.codex/skills/`, `.agents/skills/`. **Memories**: `[features] memories = true`; 세션이 ~6시간 유휴 후 다음 시작 시 백그라운드 통합 → `~/.codex/memories/`. 수정 비권장("영속 규칙은 AGENTS.md에").

## 3. Cursor
`.cursor/rules/*.mdc`(description/globs/alwaysApply), AGENTS.md. 채팅 기반 **Memories 는 2.1.17(2025-11-24) 에서 제거** — 명시적·검토 가능한 규칙으로 회귀. 교훈: 자동 메모리는 사람이 검토하는 규칙으로 승격되는 구조가 살아남는다.

## 4. Cognition Devin / Windsurf
Knowledge(트리거 설명 필수, 접근 로그) → **Skills 로 통합**(Devin 2026.10.23 부터 Playbook→SKILL.md). 세션에서 배운 것을 스킬 생성/갱신으로 제안. Windsurf memories 도 Skills 로 마이그레이션.

## 5. 기타
- **GitHub Copilot Memory**(2026-01 preview, 3월 기본 ON): 저장소 범위 사실, 사용 전 현재 코드와 대조 검증, **28일 자동 만료**, 저장소 설정에서 검토.
- **Gemini CLI**: `save_memory` → `~/.gemini/GEMINI.md` 의 `## Gemini Added Memories`. Jules 는 2026-11-11 읽기 전용화.
- **Letta Code**: 메모리 블록을 git 에, `/sleeptime` "dreaming". **Mem0**: Claude Code 플러그인(훅으로 로그 → 백그라운드 추출 → 첫 응답 전 recall).

## 6. 커뮤니티 Claude Code 자가 개선 도구
| 도구 | 메커니즘 | 비고 |
|---|---|---|
| **claude-mem** (thedotmack) | 전 훅 → Bun 워커 → SQLite FTS5 + Chroma, 3단 검색 | 상시 프로세스 필요 |
| **obra/superpowers** | SessionStart 가 방법론 스킬 주입 | 학습 루프는 없음 |
| **affaan-m/ECC continuous-learning-v2** | Pre/PostToolUse 관찰 → Haiku 옵저버(5분, ≥20건)가 confidence 점수 'instinct' 추출 → `/evolve` 가 스킬로 클러스터링; 전역 승격은 2+ 프로젝트에서 ≥0.8 | 효과 데이터 미공개 |
| **claude-reflect** | 프롬프트 훅이 교정 정규식 탐지 → 큐 → `/reflect` 가 사람 검토 후 CLAUDE.md 반영, `--scan-history` | 우리 설계와 가장 유사 |
| **compound-engineering** | `/ce-compound` 가 `docs/solutions/` 에 교훈 기록 | |
| transcript miners (bokan, yorrick, roampal-core) | `.jsonl` → 개선 제안; 고신뢰만 자동 적용 | |
| ralph-loop / continuous-claude | Stop 훅 exit 2 로 재투입 | `/goal`, `/loop` 가 공식 대체 |

## 좋은 셋업의 공통점
1. **2단 메모리 + 사람 게이트**: 에이전트는 *제안*, 사람이 CLAUDE.md/rules/skills 로 *승격*.
2. **상시 로드 층은 아주 작게, 나머지는 점진 공개**(모든 벤더가 25KB/32KiB/6,000자 캡).
3. **"항상/절대" 는 결정론적 강제**(훅, deny, Stop/`/goal` 평가기, CI).
4. **신선도/감쇠 메커니즘**(타임스탬프, 28일 만료, 통합 패스, `/doctor prompt-audit`, `/skill-doctor`).
5. **생성기와 평가기 분리**.
6. **파일 + git 이 메모리 기판**.
7. **추가 전에 측정**(`/skill-doctor`, `/usage`, `/insights`, `claude plugin eval`); 모델이 좋아지면 하네스 비계를 걷어낸다.
