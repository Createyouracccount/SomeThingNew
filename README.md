# self-tuner — Claude Code 를 '나에게 맞게' 계속 조율하는 개인용 자가 개선 하네스

> 세션에서 배운 교훈을 **id 단위 델타**로 축적하고(ACE), 반복되는 요청을 **스킬 후보**로 유도하고(AWM),
> **평가(with/without)로 검증된 것만** 승격하는(DGM/gskill) Claude Code 플러그인.
> 외부 서비스·상시 프로세스·추가 의존성 없음: Python 3 + `claude` CLI 만 있으면 된다.

---

## 0. 왜 이걸 만들었나 (조사 결론 한 페이지)

2025~2026 논문 20여 편과 Anthropic/OpenAI/Cursor/Devin/Copilot 등 제품, 그리고 커뮤니티 플러그인
(claude-mem, ECC continuous-learning, claude-reflect 등)을 조사했다. 원문 정리는
[`docs/research-academic.md`](docs/research-academic.md), [`docs/research-industry.md`](docs/research-industry.md).

살아남는 설계는 전부 같은 모양이었다:

| 원칙 | 근거 | self-tuner 에서의 구현 |
|---|---|---|
| **전체를 다시 쓰지 말고 델타로 갱신** | ACE(ICLR 2026): LLM 이 컨텍스트를 통째로 다시 쓰면 18k→122 토큰으로 붕괴, 정확도는 기준선 아래로 | `lessons.jsonl` 은 id·카운터가 있는 한 줄 단위. LLM 은 "추가할 항목"만 내고, 파일은 코드가 쓴다 |
| **도움됨/해악 카운터 + 감쇠** | ExpeL 의 UPVOTE/DOWNVOTE, Copilot Memory 의 28일 만료, Misevolution(잘못된 메모리 축적 → 환각 증가) | `helpful/harmful` 투표, 반감기 60일, 해악 3표면 자동 보관 |
| **성공이 검증된 절차만 스킬로** | Voyager, SkillWeaver, gskill(테스트 신호로 SKILL.md 최적화) | 후보는 격리 디렉터리에서 `claude plugin eval --ablation with-without` 를 통과해야 `~/.claude/skills/` 로 승격 |
| **반성(reflect)은 비판적 경로 밖에서** | Letta sleep-time compute, ACE Reflector/Curator 분리 | Stop 훅(async) 이 세션당 1회 `claude -p --model haiku` 를 **분리 프로세스**로 실행 |
| **에이전트는 제안, 사람이 승격** | Cursor 가 자동 Memories 를 제거하고 규칙으로 회귀; Devin 이 Knowledge → Skills 로 통합 | 자동 교훈은 "교훈 뷰"에만 들어가고, CLAUDE.md 편집·스킬 생성은 항상 사용자 승인 |
| **상시 로드 층은 아주 작게** | 공식 가이드 200줄 권고; 'Evaluating AGENTS.md'(2026): 컨텍스트 파일이 비용 +20% 인데 성공률은 안 오르는 경우 다수 | 전역 교훈 뷰 ≤40줄, 프로젝트 교훈은 SessionStart 에서 10줄, 프롬프트 관련 교훈은 검색으로 3줄만 |
| **중립적 프롬프트** | Phantom Guardrails(2026): "문제를 찾아라" 라고 하면 없는 문제를 지어냄 | 리플렉터 프롬프트는 "교훈이 없으면 `[]`" 을 명시 |
| **측정 없이 추가하지 않는다** | Lilian Weng(2026): "evals·격리·감사 가능한 추적이 없는 자가 개선은 자신감 있는 퇴행" | 플러그인 자체에 `evals/` 포함, `/skill-doctor`·`/doctor prompt-audit` 와 병행 |

Claude Code 에 이미 있는 것(auto memory, skill-creator, `/insights`, `/doctor prompt-audit`, `/skill-doctor`, `claude plugin eval`)
은 **대체하지 않고 그 위에 얹는다** — 아래 §6 참고.

---

## 1. 동작 개요

```
                    ┌──────────── 세션 중 (LLM 호출 0회, 전부 순수 파이썬) ────────────┐
  SessionStart ──►  on_session_start.py  : 프로젝트 교훈 ≤10줄 + 대기 중 스킬 후보 알림 주입
  UserPromptSubmit► on_prompt.py         : 프롬프트 기록(교정 여부 플래그) + 관련 교훈 ≤3줄 검색 주입
  PostToolUseFailure► on_tool_fail.py    : 도구 실패 기록 (Reflexion: 실패는 1급 메모리)
  Stop (async) ──►  on_stop.py           : 게이트 통과 시 reflect.py 를 분리 프로세스로 띄움
                    └────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼  (세션당 ≤1회, haiku, 사용자를 막지 않음)
                    reflect.py  ── Reflector ──► JSON 델타 [{text, category, scope, rationale}]
                                ── Curator  ──► lessons.upsert(): 중복이면 evidence+1·문장 정제, 아니면 추가
                                              ► curate.write_rules(): ~/.claude/rules/self-tuner.md 재생성(뷰)
                                   │
                                   ▼
  다음 세션: ~/.claude/rules/self-tuner.md 는 Claude Code 가 자동 로드 (훅 비용 0)

  사람 루프:  /self-tuner:mine  → 과거 기록 마이닝(cold start), 스킬 후보 큐 적재
             /self-tuner:retro → 이 세션 회고, 교훈을 보고 승인
             /self-tuner:lessons good|bad <id> → 피드백(점수 반영, 자동 보관)
             /self-tuner:promote → 후보를 격리 폴더에 스킬+평가로 만들고 Δ>0 일 때만 ~/.claude/skills/ 로
```

### 데이터 (모두 `~/.claude/plugins/data/self-tuner/`, 플러그인 업데이트에도 유지)
| 파일 | 내용 |
|---|---|
| `lessons.jsonl` | 교훈 원본. `{id, text, category, scope, keywords, evidence, helpful, harmful, status, created, last_seen, sources}` |
| `episodes.jsonl` | 세션 중 포착한 원시 신호(프롬프트/교정/도구 실패). 리플렉터 입력 |
| `sessions.jsonl` | 리플렉션 실행 기록(추가/병합 수, 오류) |
| `skill_candidates.json` | 스킬 후보 큐(pending/promoted/rejected) |
| `staging/<name>/` | 승격 전 격리된 스킬 초안 + evals |
| `reflect.log` | 백그라운드 리플렉터 로그 |

교훈 점수 = `(evidence + helpful − 2·harmful) × 0.5^(미사용일수/60)`; `pinned` 는 +100.

---

## 2. 설치

```bash
git clone https://github.com/Createyouracccount/SomeThingNew.git ~/dev/claude-self-tuner
~/dev/claude-self-tuner/install.sh              # → ~/.claude/skills/self-tuner (self-tuner@skills-dir 로 자동 로드)
```

### 한 세션에서만 시험하기 (전역 설치 없이)
```bash
cd <시험할 프로젝트>
SELF_TUNER_TRIAL=1 claude --plugin-dir ~/dev/claude-self-tuner
```
- `--plugin-dir` 는 **이 세션에만** 플러그인을 로드한다. 다른 터미널의 Claude Code 는 영향을 받지 않는다.
- `SELF_TUNER_TRIAL=1` 은 교훈 뷰를 `~/.claude/rules/` 에 쓰지 않고 데이터 디렉터리에만 두며, 이 세션에만 주입한다.
- 흔적은 `~/.claude/plugins/data/self-tuner-inline/` 하나뿐이다. 시험이 끝나면 그 폴더만 지우면 된다.
- 세션 안에서 확인: `/self-tuner:lessons stats` → 데이터 경로·교훈 수, `/self-tuner:mine` → 과거 기록 리포트.
- 훅이 실제로 돌았는지 보려면 프롬프트 몇 개 입력 후 다른 터미널에서
  `cat ~/.claude/plugins/data/self-tuner-inline/episodes.jsonl` (프롬프트마다 한 줄씩 쌓인다).
- 마음에 들면 `install.sh` 로 전역 설치. 시험 중 쌓인 교훈을 가져가려면
  `cp ~/.claude/plugins/data/self-tuner-inline/lessons.jsonl ~/.claude/plugins/data/self-tuner/`.

요구사항: Claude Code ≥ 2.1.3xx(`claude plugin eval`, `--plugin-dir`, async 훅), Python 3.9+, macOS/Linux.
Windows 는 `hooks.json` 의 `python3` 를 `python` 으로 바꾸면 동작할 가능성이 높지만 검증하지 않았다.

### 첫날 할 일 (cold start 를 피하는 법)
1. 새 세션에서 `/self-tuner:mine` — `~/.claude/projects/**/*.jsonl` 과 auto-memory 를 훑어
   요청 유형 분포·교정 패턴·자주 쓰는 도구·스킬 후보를 리포트한다. 여기서 나온 교훈 후보를 승인해 저장.
2. `/self-tuner:lessons` 로 저장된 교훈 확인. 틀린 건 `bad <id>`, 핵심은 `pin <id>`.
3. 평소처럼 쓴다. 3개 이상 프롬프트가 있는 세션이 끝날 때마다 리플렉터가 한 번 돈다.
4. 2~3주 뒤 `/self-tuner:promote` 로 후보를 평가·승격. `/skill-doctor` 로 안 쓰는 스킬은 제거.

---

## 3. 비용과 안전장치

- **세션 중 LLM 호출 0회.** 훅은 전부 파이썬 정규식/키워드 매칭(UserPromptSubmit 30초 제한 안에서 ~50ms).
- **리플렉터**: 세션당 최대 1회 + 새 프롬프트 5개마다 1회, haiku, 다이제스트 ≤9k자, 일일 상한 12회
  (`SELF_TUNER_DAILY_CAP`, `SELF_TUNER_MIN_PROMPTS`, `SELF_TUNER_NEW_PROMPTS`, `SELF_TUNER_MODEL` 로 조정).
- **재귀 방지**: 자식 `claude -p` 에 `SELF_TUNER_CHILD=1` 을 넘기고 모든 훅은 이 값이 있으면 즉시 종료.
  자식은 `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` 로 auto-memory 를 건드리지 않고, 도구는 전부 비허용.
- **메모리 오염 방지**: LLM 은 lessons.jsonl 을 직접 쓰지 않는다. 쓰기 시 조정(중복 병합), 해악 3표 자동 보관,
  rules 뷰는 상위 K개만. 에이전트가 만든 스킬은 `staging/` 에 격리되어 평가 통과 전엔 검색되지 않는다(EvoMal 대응).
- **비밀값**: 도구 실패 기록은 명령 앞 200자·에러 앞 300자만. 프롬프트는 1,000자까지 기록되므로
  비밀을 프롬프트에 붙여 넣는 습관이 있다면 `on_prompt.py` 의 길이를 줄이거나 마스킹을 추가할 것.
- **끄기**: `claude plugin disable self-tuner@skills-dir`. 데이터는 `~/.claude/plugins/data/self-tuner/` 에 남는다.

---

## 4. 스킬

| 스킬 | 역할 | 누가 승인 |
|---|---|---|
| `/self-tuner:mine [--days N]` | 과거 기록 마이닝 → 교훈 후보·스킬 후보·CLAUDE.md 제안 | 저장/편집은 사용자 |
| `/self-tuner:retro [session-id]` | 현재 세션 회고(사람 승인형 Reflector) | 사용자 |
| `/self-tuner:lessons [list\|good\|bad\|pin\|archive\|stats\|curate]` | 교훈 관리·피드백 | — |
| `/self-tuner:promote [id\|list]` | 후보 → 격리 초안 → `claude plugin eval` Δ>0 → `~/.claude/skills/` | 사용자 + 평가 |

`agents/reflector.md` 는 `memory: user` 를 가진 haiku 서브에이전트로, 큰 세션의 회고를 위임할 때 쓴다
(자기 메모리에 '기각된 교훈 유형'을 적어 같은 노이즈를 반복 제안하지 않도록).

---

## 5. 직접 검증하기

```bash
# 플러그인 구조 검증
claude plugin validate .

# 격리된 데이터 디렉터리로 훅 단위 테스트
export SELF_TUNER_DATA=/tmp/st-test
echo '{"session_id":"s1","cwd":"'$PWD'","prompt":"아니 그게 아니라 pnpm 으로 설치해"}' | python3 scripts/on_prompt.py
python3 scripts/reflect.py --session s1 --project demo --dry-run     # LLM 없이 다이제스트만
python3 scripts/reflect.py --session s1 --project demo               # haiku 1회 호출 (~9초)
python3 scripts/cli.py list

# 플러그인 자체 평가 (with/without 비교, 케이스 2개 × 3회 × 2arm)
claude plugin eval . --allow-tools Bash
```

이 저장소를 만들 때 실제로 확인한 것: `claude plugin validate` 통과, `claude --plugin-dir . -p` 라이브 실행에서
SessionStart/UserPromptSubmit/Stop(async) 훅이 모두 실행되고 에피소드가 기록됨, 리플렉터가 합성 세션에서
"커밋 메시지는 한국어로" 같은 교훈을 추출해 저장함. `claude plugin eval` 전체 실행은 비용 문제로 사용자 환경에서 돌리길 권한다.

---

## 6. Claude Code 내장 기능과의 관계 (중복 아님, 역할 분담)

| 내장 기능 | 하는 일 | self-tuner 가 더하는 것 |
|---|---|---|
| **Auto memory** (`~/.claude/projects/<p>/memory/`) | Claude 가 세션 중 스스로 판단해 메모 | 프로젝트 간 일반화(global scope), 점수·감쇠·투표, 교정 신호 기반 추출, 중복 병합. 리플렉터는 auto-memory 내용을 '기존 지식'으로 읽어 중복을 피함 |
| **`~/.claude/rules/`** | 전 프로젝트 상시 규칙 | `self-tuner.md` 한 파일을 '뷰'로 생성. 사용자가 쓴 다른 rules 는 건드리지 않음 |
| **`/doctor prompt-audit`** | CLAUDE.md/rules 모순 탐지 | 승격 전후에 실행 권장 — 자동 교훈이 사용자 규칙과 충돌하면 여기서 잡힌다 |
| **`/skill-doctor`** | 스킬별 컨텍스트 비용·미사용 | 승격 30일 뒤 미사용 스킬 제거 판단에 사용 |
| **`skill-creator` 플러그인** | 스킬 작성·evals.json 평가 | `/self-tuner:promote` 가 초안을 만든 뒤 `/skill-creator` 로 다듬어도 좋음(포맷은 다름: skill-creator 는 evals.json, 여기는 `claude plugin eval` 의 prompt.md+graders) |
| **`claude plugin eval`** | with/without 비교·CI 게이트 | 승격 게이트로 그대로 사용 |
| **`/insights`** | 30일 transcript 분석 리포트 | `/self-tuner:mine` 과 겹침. `/insights` 는 읽기용, `mine` 은 후보 큐에 적재해 승격 루프와 연결 |
| **`/init` (`CLAUDE_CODE_NEW_INIT=1`)** | 코드베이스 분석 → CLAUDE.md/skills/hooks 제안 | 새 프로젝트 시작용. self-tuner 는 그 이후의 '운영 중 학습' |

---

## 7. 로드맵 (다음 단계 아이디어, 우선순위순)

1. **Agent 훅으로 '예측 검증'**: Agentic Harness Engineering(2026) 의 "모든 편집은 반증 가능한 예측을 가진다" —
   교훈 추가 시 `prediction` 필드를 받고, 다음 세션 Stop 에서 `type: agent` 훅이 예측이 맞았는지 채점 → helpful/harmful 자동 투표.
2. **MaTTS 식 대조 신호**: 같은 요청을 서브에이전트 2개가 풀게 하고 차이에서 교훈 추출(ReasoningBank). `/self-tuner:retro --contrast`.
3. **Mod 로 전환**: `plugin-authoring` 스킬로 in-process 모듈을 만들면 패널에 교훈·점수를 상시 표시하고 👍/👎 를 클릭으로.
4. **임베딩 검색**: 지금은 키워드 겹침. 교훈이 200개를 넘으면 로컬 임베딩(예: `fastembed`)으로 `relevant()` 교체.
5. **MCP 메모리 서버**: 여러 머신에서 같은 lessons 를 쓰려면 `.mcp.json` 에 작은 HTTP 서버를 붙여 `~/.claude/plugins/data` 대신 원격 저장.
6. **Pareto 아카이브**: rules 뷰를 git 브랜치로 버전 관리하고, 평가 점수가 떨어지면 이전 뷰로 롤백(GEPA/DGM 의 archive).

---

## 8. 파일 구조

```
claude-self-tuner/
├── .claude-plugin/plugin.json      # 매니페스트 (experimental.evals = evals/)
├── hooks/hooks.json                # SessionStart / UserPromptSubmit / PostToolUseFailure / Stop(async)
├── scripts/
│   ├── common.py                   # 경로·JSONL·재진입 가드·교정 정규식·키워드
│   ├── lessons.py                  # 교훈 저장소: upsert(쓰기 시 조정)·vote·score(감쇠)·relevant(검색)
│   ├── curate.py                   # lessons → ~/.claude/rules/self-tuner.md (뷰)
│   ├── on_session_start.py / on_prompt.py / on_tool_fail.py / on_stop.py
│   ├── reflect.py                  # Reflector+Curator: 다이제스트 → claude -p haiku → 델타 → upsert
│   ├── mine_history.py             # 과거 transcript/메모리 마이닝 (cold start)
│   └── cli.py                      # 스킬이 호출하는 단일 CLI
├── skills/{mine,retro,lessons,promote}/SKILL.md
├── agents/reflector.md             # memory: user 를 가진 haiku 리플렉터
├── evals/                          # claude plugin eval 케이스 (플러그인 자기 평가)
├── docs/research-academic.md       # 논문 조사
├── docs/research-industry.md       # 업계·커뮤니티 조사
├── install.sh / LICENSE
```

모든 스크립트에는 "왜 이렇게 했는가" 주석이 있다. 설계를 바꿀 땐 먼저 그 주석의 질문에 다른 답이 있는지 확인할 것.
