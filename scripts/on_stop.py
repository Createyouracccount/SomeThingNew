#!/usr/bin/env python3
"""Stop 훅 (async): 세션이 '충분히 의미 있을 때만' 리플렉터를 분리 프로세스로 띄운다.

왜 Stop 이고 SessionEnd 가 아닌가: SessionEnd 는 기본 1.5초 예산이라 LLM 호출이 불가능하다.
Stop 은 매 턴 끝마다 불리지만 async:true 라 사용자를 막지 않는다.
왜 '게이트'가 있나: 모든 턴마다 LLM 을 부르면 비용·노이즈 폭증. 아래 조건을 모두 만족할 때만:
  - 이 세션에서 리플렉션을 아직 안 했거나, 마지막 리플렉션 이후 새 프롬프트가 5개 이상
  - 이번 세션 프롬프트 수 ≥ 3  (한두 마디 세션은 교훈이 없다)
  - stop_hook_active 가 아니어야 함(루프 방지)
  - 오늘 리플렉션 횟수 < 일일 상한(기본 12회)
"""
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import EPISODES, SESSIONS, bail_if_child, data_dir, project_key, read_hook_input, read_jsonl, today  # noqa: E402

bail_if_child()
inp = read_hook_input()
if inp.get("stop_hook_active"):
    sys.exit(0)
sid = inp.get("session_id")
if not sid:
    sys.exit(0)

MIN_PROMPTS = int(os.environ.get("SELF_TUNER_MIN_PROMPTS", "3"))
NEW_PROMPTS_BETWEEN = int(os.environ.get("SELF_TUNER_NEW_PROMPTS", "5"))
DAILY_CAP = int(os.environ.get("SELF_TUNER_DAILY_CAP", "12"))
DAILY_COST_CAP = float(os.environ.get("SELF_TUNER_DAILY_COST_USD", "1.00"))  # 왜: 보이지 않는 백그라운드 비용에 상한

all_eps = read_jsonl(data_dir() / EPISODES)
eps = [e for e in all_eps if e.get("session") == sid and e.get("kind") == "prompt"]
had_injection = any(e.get("session") == sid and e.get("kind") == "inject" for e in all_eps)
# 왜 주입이 있으면 예외인가: 주입된 교훈의 효과 판정은 짧은 세션에서도 해야 데이터가 쌓인다
if len(eps) < MIN_PROMPTS and not had_injection:
    sys.exit(0)

runs = read_jsonl(data_dir() / SESSIONS)
mine = [r for r in runs if r.get("session") == sid]
if mine and len(eps) - mine[-1].get("prompts", 0) < NEW_PROMPTS_BETWEEN:
    sys.exit(0)
today_runs = [r for r in runs if str(r.get("t", "")).startswith(today())]
if len(today_runs) >= DAILY_CAP or sum(r.get("cost_usd", 0.0) for r in today_runs) >= DAILY_COST_CAP:
    sys.exit(0)

# 분리(detached) 실행: Stop 훅 프로세스가 끝나도 리플렉터는 계속 돈다.
cmd = [sys.executable, str(Path(__file__).parent / "reflect.py"), "--session", sid,
       "--project", project_key(inp.get("cwd")), "--transcript", inp.get("transcript_path") or ""]
log = open(data_dir() / "reflect.log", "a")
subprocess.Popen(cmd, stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True, env=dict(os.environ))
print(json.dumps({"systemMessage": "self-tuner: 백그라운드에서 이 세션의 교훈을 정리하는 중"}))
