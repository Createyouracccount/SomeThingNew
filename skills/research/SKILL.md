---
name: research
description: 서브에이전트 여러 개를 병렬로 띄워 사용자의 분야(AI·검색·에이전트·Claude Code 도구)에서 필요한 정보를 조사하고, 출처·날짜가 붙은 지식 노트로 self-tuner 에 저장한다. 이후 관련 프롬프트가 들어오면 노트 포인터가 자동 주입된다. "조사해서 우리 거에 반영해", "최신 동향 정리", "리서치", "/self-tuner:research <주제>" 요청과 주간 재검증(--refresh)에 사용.
argument-hint: "[주제 | --auto | --refresh <노트 제목>]"
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/*), Agent, WebSearch, WebFetch, Read, Write
---

# /self-tuner:research — 리서치 서브에이전트 → 지식 노트

설계 근거: Anthropic 멀티에이전트 리서치 패턴(오케스트레이터 + 병렬 서브에이전트 + 인용 검증 단계),
"Effective context engineering"(필요할 때 가져오는 just-in-time 검색, 구조화된 노트). 리서치 에이전트의 환각을 막기 위해
**출처 URL 없는 주장은 저장하지 않는다**(cli 가 거부). 노트는 인덱스 한 줄 + 본문 파일(점진 공개).

## 0. 주제 정하기
- `$ARGUMENTS` 에 주제가 있으면 그대로.
- `--auto` 이거나 비어 있으면: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/cli.py" knowledge list` 와
  `cat "$HOME/.claude/plugins/data/self-tuner/mine.json" 2>/dev/null | head -c 3000` 을 보고,
  사용자 요청 유형·키워드에서 **아직 노트가 없는** 주제 3개를 제안하고 하나를 고르게 한다.
- `--refresh "<제목>"` 이면 그 노트를 Read 로 열어 기존 내용을 알고 시작하며, "이후 무엇이 바뀌었나"만 조사한다.

## 1. 병렬 조사 (Agent 도구, 서브에이전트 3개, 한 메시지에서 동시에 띄움)
주제를 3개 하위 질문으로 나눈다(예: "현재 최선의 방법 / 최근 3개월 변화 / 함정과 실패 사례"). 각 서브에이전트(`general-purpose`) 프롬프트에 반드시 포함:
- 오늘 날짜, 하위 질문, 사용자 맥락(Python, 검색/RAG/에이전트, 한국어 사용자, Claude Code 환경)
- "WebSearch 는 최근·틈새 주제에 extended 모드. 모든 주장에 URL 과 날짜를 붙여라. 확인 못 한 것은 '미확인'으로 표시. 한국어 출처(GeekNews news.hada.io, 요즘IT, 기업 기술블로그)도 1개 이상 찾아라."
- 출력 형식: `- 주장 (날짜) — URL` 목록 8~15개 + 3줄 요약 + 신뢰도(high/medium/low)와 이유

## 2. 검증 패스 (서브에이전트 1개)
세 보고서를 합쳐 넘기고: "서로 모순되는 주장, 날짜 없는 주장, URL 이 주장과 안 맞는 항목을 골라내라. 핵심 주장 5개는 WebFetch 로 원문을 열어 실제로 그렇게 쓰여 있는지 확인하라." 결과로 **제거/수정 목록**을 받는다.

## 3. 저장
하위 질문당 노트 1개(총 3개 내외). 본문은 임시 파일에 쓰고 cli 로 저장한다:
```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/cli.py" knowledge add --title "<제목>" --topic "<주제>" \
  --summary "<한 문장>" --body-file /tmp/note.md --sources "<url1>|<url2>|..." --keywords "<k1,k2,...>" --confidence <high|medium|low>
```
- 본문 규칙: 400~900자, 각 항목 끝에 (날짜, URL). '미확인' 항목은 별도 절에.
- 저장 뒤 `knowledge list` 로 인덱스를 보여준다.

## 4. 교훈으로 올릴 것 제안 (선택)
조사 결과 중 **사용자의 작업 방식을 바꿔야 할 것**(예: "2026-10 이후 X 라이브러리는 Y 호출 방식이 바뀜")이 있으면
`domain` 범주 교훈 후보로 1~3개 제안하고, 승인된 것만 `cli.py add --category domain --scope global --rationale "<노트 제목>"` 로 저장한다.

## 5. 비용 안내
서브에이전트 4개 × WebSearch 수 회 = 세션 하나 분량의 토큰. 주간 `--refresh` 는 바뀐 것만 보므로 더 싸다. 사용자가 비용을 묻으면 이렇게 답한다.
