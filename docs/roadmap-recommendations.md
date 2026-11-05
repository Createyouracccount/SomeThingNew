# 추가로 붙일 만한 것들 (2026-11-05 조사)

대상: Python/AI/검색 코드 중심, 한국어 사용, Claude Code 상시 사용. 공식 마켓(315개)·문서·커뮤니티를 다시 훑어 "설치만 하면 효과"부터 "self-tuner 개선"까지 정리.

## 1단계. 설치만 하면 바로 효과 (전부 공식 마켓, `/plugin install <name>@claude-plugins-official`)

| 플러그인 | 왜 사용자님에게 | 비고 |
|---|---|---|
| `pyright-lsp` | Claude 가 Python 파일을 고칠 때마다 타입 오류·누락 import 를 즉시 본다. 컴파일 없이 자기 실수를 잡음 | `pip install pyright` 먼저. 터미널 세션에서만 동작 |
| `context7` | LangChain, LlamaIndex, Qdrant 클라이언트처럼 API 가 자주 바뀌는 라이브러리의 **현재 버전 문서**를 조회 | 학습 컷오프 이후 바뀐 API 환각을 줄임 |
| `exa` 또는 `tavily` | 리서치용 웹검색 + 본문 추출. exa 는 "이 글과 비슷한 글" 식 의미 검색 | API 키 필요. 둘 중 하나만 |
| `hookify` | "다음부터 X 하지 마" 를 **훅으로** 만들어 강제. self-tuner 의 교훈은 '권고'지만 hookify 는 '강제' | self-tuner pitfall 교훈 → hookify 로 승격하는 다리가 자연스러움 |
| `claude-md-management` | `/revise-claude-md` 로 세션 학습을 CLAUDE.md 에 제안 | self-tuner 와 역할 분담: CLAUDE.md 쪽은 이것 |
| `skill-creator` | `/self-tuner:promote` 가 만든 초안을 다듬고 평가 | 공식 |
| `deepeval`, `langfuse`, `mlflow` | 사용자님 **자신의 RAG/검색 파이프라인** 평가·추적 스킬. Claude 가 평가 코드를 제대로 짬 | 셋 중 쓰는 스택 하나 |
| `qdrant-skills`, `redis-development`(vector search), `huggingface-skills`, `pydantic-ai` | 검색·임베딩·에이전트 도메인 스킬 | 필요한 것만 |
| `security-guidance` | Claude 가 짠 코드의 보안 패턴 경고 + Stop 시 diff 리뷰 | 가벼움 |
| `session-report`, `receipts` | 세션 토큰·캐시·스킬 사용 리포트 / 기간별 성과 리포트 | self-tuner 의 `stats` 와 함께 "뭐가 효과 있었나" 확인 |

논문 검색 MCP (마켓 외): `blazickjp/arxiv-mcp-server`(약 2.8k★, 메타데이터·초록), `smorande` ArXiv Research MCP(전문 검색 + Semantic Scholar 인용, API 키 불필요, 요청 제한 3초/1회). `~/.claude/.mcp.json` 또는 `claude mcp add` 로 추가.

## 2단계. 안 쓰고 있을 가능성이 높은 Claude Code 기능

- **`/goal`**: "테스트 전부 통과할 때까지" 같은 조건을 세션 범위 Stop 훅으로. `/loop` 는 간격 반복.
- **`~/.claude/loop.md` + Desktop 예약 작업**: 주 1회 "self-tuner 정리 + `/doctor prompt-audit` + `/skill-doctor`" 유지보수를 자동 실행. 세션 `/loop` 는 7일 만료라 장기 예약은 Desktop/클라우드 예약 작업으로.
- **Channels (Telegram/Discord/iMessage)**: 폰에서 메시지 보내면 로컬 세션이 실제 파일로 작업하고 답을 돌려줌. `claude --channels plugin:telegram@claude-plugins-official`. Bun 필요. 연구 프리뷰.
- **Agent teams**: 리드 세션이 worktree 별 팀원 세션을 병렬로. 비용은 에이전트 수에 비례.
- **Remote Control**: 로컬 세션을 폰/웹에서 이어서 조작.
- **`/insights`**: 30일 transcript 분석 리포트(공식 문서 인덱스엔 없음). `/self-tuner:mine` 과 비교해 보면 좋음.

## 3단계. self-tuner 개선 (우선순위순)

1. **hookify 다리**: `pitfall` 범주이고 evidence ≥ 3, harmful = 0 인 교훈을 "훅으로 강제할까요?" 로 제안 → `/hookify` 호출. 근거: 공식 best-practices "강조를 계속 추가하게 되면 그 줄은 훅에 들어가야 한다".
2. **`/self-tuner:weekly` 유지보수 스킬**: 감쇠·보관 정리, rules 뷰 재생성, `/skill-doctor`·`/doctor prompt-audit` 결과 요약, 지난주 추가/병합/투표 통계 리포트. Desktop 예약 작업으로 주 1회.
3. **ECC 스킬 추천기**: `mine` 리포트의 요청 유형 분포 → 사용자님 ECC 포크에서 맞는 스킬 5~10개 추천 + 복사 명령 생성. (ECC 통째 설치는 스킬 설명만 ~100KB 상시 로드라 비권장)
4. **예측 검증 훅**: 교훈 추가 시 `prediction` 을 받고, 다음 세션 Stop 에서 `type: agent` 훅이 맞았는지 채점 → helpful/harmful 자동 투표 (Agentic Harness Engineering 2026).
5. **임베딩 검색**: 교훈 200개 넘으면 키워드 매칭 → `model2vec` `potion-multilingual-128M`(bge-m3 증류, CPU, 256차원). 한국어 포함 여부는 모델 카드에서 직접 확인 필요(이 세션에선 huggingface.co 접근 차단).
6. **한국어 형태소**: `kiwipiepy` 가 있으면 사용, 없으면 현재 조사 제거 정규식 유지(선택 의존성).

## 출처
- 공식 마켓 manifest: https://github.com/anthropics/claude-plugins-official (`.claude-plugin/marketplace.json`, 315개)
- Channels: https://code.claude.com/docs/en/channels · Code intelligence: https://code.claude.com/docs/en/plugins/code-intelligence · Scheduled tasks: https://code.claude.com/docs/en/scheduled-tasks · Goal: https://code.claude.com/docs/en/goal
- arXiv MCP: https://glama.ai/mcp/servers/integrations/arxiv · MCP 비교: https://dev.to/rikuq/best-mcp-servers-for-claude-code-in-2026-honest-picks-4kk0
- RAG 평가 도구 2026: https://qaskills.sh/blog/rag-evaluation-tools-guide-2026 · model2vec: https://github.com/MinishLab/model2vec
