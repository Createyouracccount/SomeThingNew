#!/usr/bin/env python3
"""스킬이 Bash 로 호출하는 단일 진입점. 서브커맨드:
  list | good <id> | bad <id> | pin <id> | archive <id> | stats | curate
  add --text ... --category ... --scope ... [--source ...] [--rationale ...]
  candidate list | candidate add --intent --keyword --examples "a|b" | candidate promote <id> --skill <name> | candidate reject <id>

왜 하나의 CLI 인가: 스킬의 allowed-tools 를 `Bash(python3 .../scripts/*)` 한 패턴으로 좁힐 수 있고,
스킬 본문이 짧아진다(스킬 본문은 500줄 이하 권고).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import CANDIDATES, SESSIONS, data_dir, now_iso, read_jsonl  # noqa: E402
import curate  # noqa: E402
import lessons  # noqa: E402


def _cands() -> list[dict]:
    p = data_dir() / CANDIDATES
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def _save_cands(c: list[dict]) -> None:
    (data_dir() / CANDIDATES).write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")


def cmd_list(_a):
    rows = lessons.load()
    now = time.time()
    active = [l for l in rows if l.get("status", "active") == "active"]
    active.sort(key=lambda l: lessons.score(l, now), reverse=True)
    print(f"| id | 점수 | 범주 | 범위 | 증거/👍/👎 | 교훈 |\n|---|---|---|---|---|---|")
    for l in active:
        print(f"| {l['id']} | {lessons.score(l, now):.1f} | {l['category']} | {l['scope']} | "
              f"{l.get('evidence',1)}/{l.get('helpful',0)}/{l.get('harmful',0)} | {l['text']} |")
    arch = [l for l in rows if l.get("status") == "archived"]
    print(f"\n활성 {len(active)}개, 보관 {len(arch)}개. rules 뷰: {curate.claude_home() / 'rules' / curate.RULES_FILE}")


def cmd_vote(a, good: bool):
    ok = lessons.vote(a.id, good)
    print(("반영됨" if ok else "해당 id 없음") + f": {a.id} {'good' if good else 'bad'}")
    curate.write_rules()


def cmd_status(a, status: str):
    ok = lessons.set_status(a.id, status)
    print(("반영됨" if ok else "해당 id 없음") + f": {a.id} → {status}")
    curate.write_rules()


def cmd_add(a):
    lid, how = lessons.upsert(a.text, a.category, a.scope, a.source or "manual", a.rationale or "")
    print(json.dumps({"id": lid, "result": how}, ensure_ascii=False))
    curate.write_rules()


def cmd_curate(_a):
    print("wrote", curate.write_rules())


def cmd_stats(_a):
    runs = read_jsonl(data_dir() / SESSIONS)
    rows = lessons.load()
    errs = [r for r in runs if r.get("error")]
    print(json.dumps({
        "data_dir": str(data_dir()),
        "lessons_active": sum(1 for l in rows if l.get("status", "active") == "active"),
        "lessons_archived": sum(1 for l in rows if l.get("status") == "archived"),
        "by_scope": {s: sum(1 for l in rows if l.get("scope") == s) for s in sorted({l.get("scope") for l in rows})},
        "reflections": len(runs),
        "reflections_with_error": len(errs),
        "last_error": errs[-1]["error"] if errs else None,
        "added_total": sum(r.get("added", 0) for r in runs),
        "merged_total": sum(r.get("merged", 0) for r in runs),
        "candidates_pending": sum(1 for c in _cands() if c.get("status") == "pending"),
    }, ensure_ascii=False, indent=2))


def cmd_candidate(a):
    c = _cands()
    if a.sub == "list":
        for x in c:
            print(f"- [{x['status']}] {x['id']} {x['intent']}/{x['keyword']} — 예: {' | '.join(x.get('examples', [])[:2])}"
                  + (f" → skill: {x.get('skill')}" if x.get("skill") else ""))
        if not c:
            print("(후보 없음 — /self-tuner:mine 을 먼저 실행)")
    elif a.sub == "add":
        cid = "C" + hashlib.sha1(f"{a.intent}/{a.keyword}".encode()).hexdigest()[:6]
        if any(x["id"] == cid for x in c):
            print(f"이미 있음: {cid}")
            return
        c.append({"id": cid, "intent": a.intent, "keyword": a.keyword,
                  "examples": [e.strip() for e in (a.examples or "").split("|") if e.strip()],
                  "status": "pending", "created": now_iso()})
        _save_cands(c)
        print(f"추가됨: {cid}")
    elif a.sub in ("promote", "reject"):
        for x in c:
            if x["id"] == a.id:
                x["status"] = "promoted" if a.sub == "promote" else "rejected"
                x["updated"] = now_iso()
                if a.skill:
                    x["skill"] = a.skill
                if a.note:
                    x["note"] = a.note
                _save_cands(c)
                print(f"{a.id} → {x['status']}")
                return
        print("해당 id 없음")


def main() -> int:
    ap = argparse.ArgumentParser(prog="self-tuner")
    sp = ap.add_subparsers(dest="cmd")
    sp.add_parser("list").set_defaults(f=cmd_list)
    for name, g in (("good", True), ("bad", False)):
        p = sp.add_parser(name); p.add_argument("id"); p.set_defaults(f=lambda a, g=g: cmd_vote(a, g))
    for name in ("pin", "archive"):
        p = sp.add_parser(name); p.add_argument("id"); p.set_defaults(f=lambda a, s=name: cmd_status(a, s))
    p = sp.add_parser("add")
    p.add_argument("--text", required=True); p.add_argument("--category", default="workflow")
    p.add_argument("--scope", default="global"); p.add_argument("--source"); p.add_argument("--rationale")
    p.set_defaults(f=cmd_add)
    sp.add_parser("curate").set_defaults(f=cmd_curate)
    sp.add_parser("stats").set_defaults(f=cmd_stats)
    p = sp.add_parser("candidate")
    p.add_argument("sub", choices=["list", "add", "promote", "reject"])
    p.add_argument("id", nargs="?"); p.add_argument("--intent"); p.add_argument("--keyword")
    p.add_argument("--examples"); p.add_argument("--skill"); p.add_argument("--note")
    p.set_defaults(f=cmd_candidate)
    a = ap.parse_args()
    if not a.cmd:
        a = ap.parse_args(["list"])
    a.f(a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
