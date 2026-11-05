#!/usr/bin/env python3
"""교훈 → 훅 강제 (enforce).

왜 필요한가: CLAUDE.md/rules 의 문장은 '권고'다. 공식 best-practices 는 "강조를 반복하게 되면
그 줄은 훅에 들어가야 한다"고 말한다. self-tuner 는 어떤 교훈이 반복 확인됐는지(evidence)와
틀린 적이 없는지(harmful=0)를 알고 있으므로, 강제 후보를 자동으로 고를 수 있다.

구현 선택:
- hookify 플러그인이 설치돼 있으면 그쪽에 위임한다(사람이 검토하는 UI 가 있다).
- 없으면 Claude Code 의 `type: prompt` 훅(LLM 평가형)을 만든다. 교훈 문장을 규칙으로 넣고
  PreToolUse(Edit|Write|Bash) 또는 Stop 에서 평가한다. 정규식 훅보다 범용이지만 호출마다 작은 모델
  비용이 들므로 **동시에 강제하는 교훈은 최대 5개**로 제한한다.
- settings.json 수정은 항상 사용자 승인 뒤 `apply` 로만 한다. 적용 전 백업을 남긴다.
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from common import claude_home, now_iso
import lessons

MAX_ENFORCED = 5
MIN_EVIDENCE = 3

# 교훈 범주 → 기본 이벤트/매처. 왜: pitfall/tool 은 '행동 직전'에 막는 게 맞고(PreToolUse),
# workflow/preference 는 '응답이 끝날 때' 전체를 보고 판단하는 게 맞다(Stop).
DEFAULT_EVENT = {
    "pitfall": ("PreToolUse", "Edit|Write|MultiEdit|Bash"),
    "tool": ("PreToolUse", "Bash"),
    "workflow": ("Stop", None),
    "preference": ("Stop", None),
    "domain": ("Stop", None),
    "project": ("Stop", None),
}


def candidates() -> list[dict]:
    """강제 후보: 활성, 미강제, evidence ≥ 3, harmful == 0, 점수 상위."""
    now = time.time()
    rows = [l for l in lessons.load()
            if l.get("status", "active") == "active" and not l.get("enforced")
            and l.get("evidence", 1) >= MIN_EVIDENCE and l.get("harmful", 0) == 0]
    rows.sort(key=lambda l: lessons.score(l, now), reverse=True)
    return rows


def enforced() -> list[dict]:
    return [l for l in lessons.load() if l.get("enforced")]


def hookify_installed() -> bool:
    """hookify 플러그인 존재 여부. 설치 경로는 버전마다 달라 두 곳을 본다."""
    home = claude_home()
    for p in (home / "plugins", home / "skills"):
        if p.exists() and any("hookify" in str(x) for x in p.rglob("*hookify*")):
            return True
    return False


def build_hook(lesson: dict, event: str | None = None, matcher: str | None = None) -> tuple[str, dict]:
    ev, default_matcher = DEFAULT_EVENT.get(lesson.get("category", "workflow"), ("Stop", None))
    event = event or ev
    matcher = matcher if matcher is not None else default_matcher
    if event == "Stop":
        prompt = (f"다음 규칙을 이 턴의 작업이 위반했는지 평가하세요. 규칙: \"{lesson['text']}\". "
                  f"위반이 명확하면 ok:false 와 함께 무엇을 고쳐야 하는지 한 문장으로 알려주고, "
                  f"위반이 없거나 규칙이 이 작업과 무관하면 ok:true. 입력: $ARGUMENTS")
    else:
        prompt = (f"다음 규칙을 이 도구 호출이 위반하는지 평가하세요. 규칙: \"{lesson['text']}\". "
                  f"명확히 위반하면 차단(ok:false)하고 이유를 한 문장으로. 무관하거나 불확실하면 허용(ok:true). "
                  f"입력: $ARGUMENTS")
    hook = {"type": "prompt", "prompt": prompt, "timeout": 30}
    if event == "Stop":
        hook["continueOnBlock"] = True  # 왜: 턴을 끝내지 말고 고치게 한다
    entry = {"hooks": [hook], "_self_tuner": lesson["id"]}
    if matcher:
        entry["matcher"] = matcher
    return event, entry


def apply(lesson_id: str, event: str | None = None, matcher: str | None = None) -> Path:
    rows = lessons.load()
    target = next((l for l in rows if l["id"] == lesson_id), None)
    if not target:
        raise SystemExit(f"해당 id 없음: {lesson_id}")
    if len(enforced()) >= MAX_ENFORCED:
        raise SystemExit(f"동시 강제 상한({MAX_ENFORCED})에 도달. 먼저 `enforce remove <id>` 로 하나를 내리세요.")
    settings = claude_home() / "settings.json"
    data = {}
    if settings.exists():
        shutil.copy(settings, settings.with_suffix(f".json.bak-{int(time.time())}"))  # 왜 백업: 사용자 설정 파일을 건드리므로
        try:
            data = json.loads(settings.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            raise SystemExit("settings.json 이 올바른 JSON 이 아닙니다. 손으로 확인하세요.")
    ev, entry = build_hook(target, event, matcher)
    hooks = data.setdefault("hooks", {})
    arr = hooks.setdefault(ev, [])
    arr = [e for e in arr if e.get("_self_tuner") != lesson_id]  # 멱등
    arr.append(entry)
    hooks[ev] = arr
    settings.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    target["enforced"] = {"event": ev, "matcher": entry.get("matcher"), "since": now_iso()}
    lessons.save(rows)
    return settings


def remove(lesson_id: str) -> bool:
    settings = claude_home() / "settings.json"
    changed = False
    if settings.exists():
        data = json.loads(settings.read_text(encoding="utf-8"))
        for ev, arr in list(data.get("hooks", {}).items()):
            new = [e for e in arr if e.get("_self_tuner") != lesson_id]
            if len(new) != len(arr):
                changed = True
                if new:
                    data["hooks"][ev] = new
                else:
                    del data["hooks"][ev]
        if changed:
            settings.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rows = lessons.load()
    for l in rows:
        if l["id"] == lesson_id and l.get("enforced"):
            l.pop("enforced", None)
            changed = True
    lessons.save(rows)
    return changed
