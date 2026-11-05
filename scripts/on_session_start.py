#!/usr/bin/env python3
"""SessionStart 훅: 프로젝트 범위 교훈 + 대기 중인 스킬 후보를 컨텍스트에 주입한다.

전역 교훈은 ~/.claude/rules/self-tuner.md 로 이미 로드되므로 여기서 다시 넣지 않는다(중복 방지).
왜 짧게 넣나: 'Evaluating AGENTS.md'(2026) 연구는 컨텍스트 파일이 비용을 20% 이상 올리면서
성공률은 못 올리는 경우가 많다고 보고했다. 주입은 '지시'만, '개요'는 넣지 않는다.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import CANDIDATES, bail_if_child, data_dir, emit, project_key, read_hook_input  # noqa: E402
import lessons  # noqa: E402
import curate  # noqa: E402
import outcomes  # noqa: E402
import knowledge  # noqa: E402

bail_if_child()
inp = read_hook_input()
proj = project_key(inp.get("cwd"))

# 세션 시작마다 rules 뷰를 최신 상태로 맞춘다(비용: 파일 1개 비교·쓰기).
try:
    curate.write_rules()
except Exception:
    pass

parts = []
if curate.is_trial():
    parts.append("[self-tuner] 시험 모드(SELF_TUNER_TRIAL=1): 교훈은 이 세션에만 주입되고 ~/.claude/rules 에는 쓰지 않습니다.")
    glob_rows = lessons.top(scope_filter={"global"}, k=20)
    if glob_rows:
        parts.append("[self-tuner] 전역 교훈:")
        parts += [f"- {l['text']} [{l['id']}]" for l in glob_rows]
proj_rows = lessons.top(scope_filter={f"project:{proj}"}, k=10)
if proj_rows:
    parts.append(f"[self-tuner] 이 프로젝트({proj})에서 과거에 배운 교훈:")
    parts += [f"- {l['text']} [{l['id']}]" for l in proj_rows]
    outcomes.log_injection(inp.get("session_id"), [l["id"] for l in proj_rows], "session_start")

# 지식 노트는 인덱스 경로만 알린다(auto-memory 와 같은 방식). 왜: 프롬프트마다 키워드로 끼워넣으면 오탐과 잡음.
# 인덱스 한 줄만 보고 필요할 때 Claude 가 Read 로 연다.
kn = [n for n in knowledge.notes() if n.get("status") == "verified" or n.get("confidence") == "high"]
if kn:
    parts.append(f"[self-tuner] 지식 노트 {len(kn)}개(검증됨) — 인덱스: {knowledge.kdir() / 'KNOWLEDGE.md'} (주제가 겹치면 Read 로 열어 참고)")

cand_path = data_dir() / CANDIDATES
if cand_path.exists():
    try:
        cands = [c for c in json.loads(cand_path.read_text(encoding="utf-8")) if c.get("status") == "pending"]
    except Exception:
        cands = []
    if cands:
        parts.append(f"[self-tuner] 검토 대기 중인 스킬 후보 {len(cands)}개가 있습니다. 사용자가 원하면 /self-tuner:promote 로 확인.")

if parts:
    emit({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "\n".join(parts)}})
