# 조사: 리서치 자동 흡수 + JIT 지식 저장소 패턴 (2026-11-05, 리서치 서브에이전트 보고 요약)

## 기존 digest 에이전트의 공통 구조
fetch(arXiv RSS/API) → 키워드 선별 → LLM 0~10 점수(관심 프로필) → 상위 k 정독 → 날짜 붙은 md/json. 참고 구현: sphy2016/arxiv-daily-agent(관심 프로필 `interests.md` + `feedback.jsonl` + 주간 반영 + changelog, `claude -p` 프로바이더), 0xHalo22/arxiv-llm-daily(GitHub Actions cron, 36h 창), wjcwjc77/hacker-news-agent(Claude Code 서브에이전트). 공통 공백: **주장 단위 검증 없음**.

## 잘 동작하는 지식 저장 형식
- Claude Code auto-memory: 인덱스 200줄/25KB + 토픽 파일, `modified` 타임스탬프 자동.
- Karpathy LLM Wiki(2026-04): raw(불변)/wiki(LLM 유지)/schema 3층 + index.md + log.md; ~100 소스까지 평문 인덱스로 충분, 그 이상은 하이브리드 검색.
- A-MEM: 작은 연결 노트, 질의당 1.1~2.5k 토큰 vs MemGPT 17k.
- Letta 블록 2,000자; Graphiti 양시제 필드(valid_at/invalid_at/created_at) — 삭제 대신 무효화.
- Chroma Context Rot(2025-07): 입력이 길수록 모든 모델 성능 저하 → 포인터만 컨텍스트에, 본문은 JIT.
- 권장 노트 크기: 본문 150~400단어, 인덱스 한 줄 120자 이내.

## Anthropic 오케스트레이션 레시피(멀티에이전트 리서치 시스템, 2025-06)
리드가 계획 저장 → 병렬 서브에이전트(목표/출력형식/도구/경계 명시) → 종합 → **별도 CitationAgent**. 노력 규칙: 단순 1에이전트 3~10콜, 비교 2~4 에이전트 10~15콜, 복잡 10+. 멀티에이전트는 채팅의 ~15배 비용.

## 환각 통제 수치
- 2604.03173: 인용 URL 3~13% 환각, 5~18% 미해결; 딥리서치 에이전트 URL 10.7% 환각; URL 헬스 도구로 <1%.
- 2605.06635: URL 유효 >94%, 관련성 >80% 인데 **실제 뒷받침 39~77%**; 도구 호출 2→150 늘리면 정확도 −42%.
→ url + verbatim quote + fetched_at 필수, 재조회로 quote 포함 확인, 2개 독립 출처, 미도달은 status unverified 로 JIT 제외, 서브에이전트 도구 호출 10~15 캡.

## 한국어
GeekNews 피드(feedburner 'geeknews-feed', 공식 안내 news.hada.io/blog/geeknews_feed), 요즘IT 는 RSS 없음(뉴스레터), AI타임스/Kakao Tech/Naver D2 피드 URL 은 확인 필요. WebSearch 는 US 중심이라 한국어 질의는 노이즈 큼 → 알려진 출처 직접 WebFetch 권장.

## 고신호 출처
Anthropic Engineering, code.claude.com/docs/llms.txt, arXiv cs.IR/cs.CL(API·RSS), Semantic Scholar API, HF Papers, hnrss(q=RAG), Simon Willison, Chroma research, Zep blog / GeekNews, Kakao Tech, Naver D2, AI타임스, 모두의연구소, awesome-kr-blogs.

## self-tuner 반영(구현 완료)
`knowledge.py`: 출처 필수, 각 출처 quote·published_at, `verify` 가 URL 재조회+quote 매칭 → status/confidence 갱신, seen.jsonl 중복 방지, log.md 추가 기록, verify_by 90일(api-change/pricing 30일), 미검증 노트는 프롬프트 자동 주입 제외. `/self-tuner:research` 스킬: 병렬 3 스카우트(1개 한국어 전담) + 검증 패스.

출처: https://github.com/sphy2016/arxiv-daily-agent · https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f · https://arxiv.org/abs/2502.12110 · https://trychroma.com/research/context-rot · https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents · https://www.anthropic.com/engineering/multi-agent-research-system · https://arxiv.org/abs/2604.03173 · https://arxiv.org/abs/2605.06635 · https://help.getzep.com/graphiti/graphiti/overview/ · https://news.hada.io/blog/geeknews_feed
