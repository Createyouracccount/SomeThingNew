#!/usr/bin/env python3
"""PostToolUse(Bash) 훅: 테스트 명령이 '성공'했을 때만 동작한다 — 직전에 주입한 교훈에 worked 를 준다.
왜 Bash 만 보나: 결정론적 성공 신호는 테스트 통과뿐이다. 그 외 도구 성공은 교훈과 인과가 없다.
LLM 호출 없음, 테스트 명령이 아니면 즉시 종료(비용 ~수 ms)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import bail_if_child, read_hook_input  # noqa: E402
import outcomes  # noqa: E402

bail_if_child()
inp = read_hook_input()
cmd = str((inp.get("tool_input") or {}).get("command") or "")
if not outcomes.TEST_CMD.search(cmd):
    sys.exit(0)
resp = inp.get("tool_response")
# tool_response 형태가 버전마다 달라 보수적으로 판단: 명시적 실패 흔적이 없으면 성공으로 본다(PostToolUse 는 성공 시에만 발화)
text = resp if isinstance(resp, str) else (resp or {}).get("stdout", "") if isinstance(resp, dict) else ""
if any(k in str(text)[-2000:].lower() for k in ("failed", "error", "fail:", "errors=")):
    sys.exit(0)
try:
    outcomes.on_test_result(inp.get("session_id"), cmd, passed=True)
except Exception:
    pass
