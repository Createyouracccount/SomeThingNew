#!/usr/bin/env python3
"""UserPromptSubmit 훅 (30초 제한, 매 프롬프트 실행 → LLM 호출 금지, 순수 파이썬만).

하는 일 두 가지:
1. 프롬프트를 episodes.jsonl 에 기록(교정 여부 플래그 포함). 세션 끝 리플렉터의 입력이 된다.
2. 프롬프트 키워드와 겹치는 교훈 중 rules 파일에 '안 실린' 것(프로젝트 범위 / 하위 순위)을
   최대 3개 주입한다. 검색 기반 주입(Generative Agents의 relevance 검색)이라 컨텍스트 낭비가 적다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import EPISODES, append_jsonl, bail_if_child, data_dir, emit, keywords, looks_like_correction, now_iso, project_key, read_hook_input  # noqa: E402
import curate  # noqa: E402
import knowledge  # noqa: E402
import lessons  # noqa: E402

bail_if_child()
inp = read_hook_input()
prompt = (inp.get("prompt") or "").strip()
if not prompt or prompt.startswith("/"):
    sys.exit(0)  # 슬래시 커맨드는 '내 말'이 아니다

proj = project_key(inp.get("cwd"))
corr = looks_like_correction(prompt)
append_jsonl(data_dir() / EPISODES, {
    "t": now_iso(), "kind": "prompt", "session": inp.get("session_id"), "project": proj,
    "correction": corr, "text": prompt[:1000], "kw": keywords(prompt, limit=8),
})

# rules 파일에 이미 실린 전역 상위 교훈은 제외 → 중복 주입 방지
# 시험 모드에선 전역 교훈이 SessionStart 로 이미 주입됐으므로 동일하게 제외한다
already = {l["id"] for l in lessons.top(scope_filter={"global"}, k=20 if curate.is_trial() else 32)}
hits = lessons.relevant(prompt, scope_filter={"global", f"project:{proj}"}, k=3, exclude_ids=already)
parts = []
if hits:
    parts.append("[self-tuner] 이 요청과 관련 있을 수 있는 과거 교훈:\n" + "\n".join(f"- {l['text']} [{l['id']}]" for l in hits))
# 지식 노트는 '포인터'만 넣는다(제목·요약·경로). 왜: 본문을 넣으면 컨텍스트가 터진다. 필요하면 Claude 가 Read 로 연다.
knotes = knowledge.relevant(prompt, k=2)
if knotes:
    parts.append("[self-tuner] 관련 지식 노트(필요하면 Read 로 열기):\n" + "\n".join(
        f"- {n['title']} — {n['summary'][:100]} (수집 {n.get('fetched_at','?')}) → {n['path']}" for n in knotes))
if parts:
    emit({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "\n".join(parts)}})
