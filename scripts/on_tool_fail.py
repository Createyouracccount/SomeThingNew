#!/usr/bin/env python3
"""PostToolUseFailure 훅: 도구 실패를 episodes 에 기록한다(Reflexion: 실패는 1급 메모리).
LLM 호출 없음. 어떤 도구가 어떤 입력으로 실패했는지의 머리 부분만 남긴다."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import EPISODES, append_jsonl, bail_if_child, data_dir, now_iso, project_key, read_hook_input  # noqa: E402

bail_if_child()
inp = read_hook_input()
tool = inp.get("tool_name", "?")
ti = inp.get("tool_input") or {}
# 왜 Bash 명령은 앞 200자만: 비밀값이 섞일 수 있고, 교훈 추출에는 명령의 '종류'만 필요하다.
summary = ti.get("command") or ti.get("file_path") or ti.get("pattern") or json.dumps(ti, ensure_ascii=False)
err = str(inp.get("error") or inp.get("tool_response") or "")[:300]
append_jsonl(data_dir() / EPISODES, {
    "t": now_iso(), "kind": "tool_failure", "session": inp.get("session_id"),
    "project": project_key(inp.get("cwd")), "tool": tool, "input": str(summary)[:200], "error": err,
})
