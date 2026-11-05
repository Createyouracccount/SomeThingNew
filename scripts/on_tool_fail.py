#!/usr/bin/env python3
"""PostToolUseFailure 훅: 도구 실패를 기록하고, '실패 신호가 있을 때만' 교훈을 주입한다.

두 가지 근거(2026-10/11 연구):
- REM: 교훈을 매 세션 시작에 넣는 대신 에이전트가 **막혔을 때만** 주입(struggle-gated) → 비용 -17%, 성능 유지.
- TokenEconomizer(MS Research): 같은 실패를 반복하는 루프를 끊는 가드가 비용 18~31% 절감.

그래서:
1) 실패를 episodes 에 기록한다(기존).
2) 이 세션에서 같은 도구+같은 입력 머리가 2번 이상 실패했으면 "반복 실패" 경고와 함께
   이 범위의 pitfall/tool 교훈 상위 5개를 주입한다(키워드 매칭 없음). LLM 호출 없음.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import EPISODES, append_jsonl, bail_if_child, data_dir, emit, now_iso, project_key, read_hook_input, read_jsonl  # noqa: E402
import lessons  # noqa: E402
import outcomes  # noqa: E402

bail_if_child()
inp = read_hook_input()
tool = inp.get("tool_name", "?")
ti = inp.get("tool_input") or {}
# 왜 Bash 명령은 앞 200자만: 비밀값이 섞일 수 있고, 교훈 추출에는 명령의 '종류'만 필요하다.
summary = str(ti.get("command") or ti.get("file_path") or ti.get("pattern") or json.dumps(ti, ensure_ascii=False))[:200]
err = str(inp.get("error") or inp.get("tool_response") or "")[:300]
sid = inp.get("session_id")
proj = project_key(inp.get("cwd"))
append_jsonl(data_dir() / EPISODES, {
    "t": now_iso(), "kind": "tool_failure", "session": sid, "project": proj,
    "tool": tool, "input": summary, "error": err,
})

# 테스트 명령 실패 → 직전 주입 교훈 중 관련 있는 것은 failed
if tool == "Bash" and outcomes.TEST_CMD.search(summary):
    try:
        outcomes.on_test_result(sid, summary, passed=False, error=err)
    except Exception:
        pass

# ---- 반복 실패 감지 (같은 도구 + 입력 앞 60자) ----
sig = (tool, summary[:60])
same = [e for e in read_jsonl(data_dir() / EPISODES)
        if e.get("session") == sid and e.get("kind") == "tool_failure"
        and (e.get("tool"), (e.get("input") or "")[:60]) == sig]
if len(same) < 2:
    sys.exit(0)

parts = [f"[self-tuner] 같은 실패가 이 세션에서 {len(same)}번 반복됐습니다 ({tool}: {summary[:60]}…). "
         f"같은 시도를 되풀이하지 말고 원인 가설을 바꾸거나 사용자에게 확인하세요."]
# 키워드 매칭 대신 '이 범위의 pitfall/tool 교훈 상위 5개'. 왜: 실패 상황 자체가 강한 문맥이라
# 작은 목록을 통째로 보여주고 모델이 고르게 하는 쪽이 토큰 겹침 추측보다 정확하다.
hits = [l for l in lessons.top(scope_filter={"global", f"project:{proj}"}, k=30)
        if l.get("category") in ("pitfall", "tool")][:5]
if hits:
    parts.append("관련 교훈:\n" + "\n".join(f"- {l['text']} [{l['id']}]" for l in hits))
    outcomes.log_injection(sid, [l["id"] for l in hits], "repeated_failure")
emit({"hookSpecificOutput": {"hookEventName": "PostToolUseFailure", "additionalContext": "\n".join(parts)}})
