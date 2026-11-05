#!/usr/bin/env python3
"""UserPromptSubmit 훅: 프롬프트를 episodes.jsonl 에 **기록만** 한다. 판단·주입 없음.

왜 기록만 하나: 이전 버전은 정규식으로 교정을 표시하고 키워드로 교훈을 끼워넣었다.
둘 다 문맥을 모르는 방식이라 오탐이 많았고, 틀린 주입은 컨텍스트만 더럽힌다.
교훈 추출과 효과 판정은 세션 끝에 리플렉터(LLM)가 전체 대화를 보고 한다. 이 훅의 일은 그 재료를 남기는 것뿐이다.
LLM 호출 없음, 수 ms.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import EPISODES, append_jsonl, bail_if_child, data_dir, now_iso, project_key, read_hook_input  # noqa: E402

bail_if_child()
inp = read_hook_input()
prompt = (inp.get("prompt") or "").strip()
if not prompt or prompt.startswith("/"):
    sys.exit(0)  # 슬래시 커맨드는 '내 말'이 아니다
append_jsonl(data_dir() / EPISODES, {
    "t": now_iso(), "kind": "prompt", "session": inp.get("session_id"),
    "project": project_key(inp.get("cwd")), "text": prompt[:1000],
})
