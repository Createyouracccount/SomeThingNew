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
import enforce  # noqa: E402
import knowledge  # noqa: E402
import lessons  # noqa: E402
import recommend as recommend_mod  # noqa: E402
import weekly  # noqa: E402


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
    print(f"| id | 점수 | 범주 | 범위 | 증거/👍/👎 | 세션수 | 상태 | 교훈 |\n|---|---|---|---|---|---|---|---|")
    for l in active:
        state = "강제" if l.get("enforced") else ("확정" if lessons.is_confirmed(l) else "잠정")
        print(f"| {l['id']} | {lessons.score(l, now):.1f} | {l['category']} | {l['scope']} | "
              f"{l.get('evidence',1)}/{l.get('helpful',0)}/{l.get('harmful',0)} | {lessons.distinct_sessions(l)} | {state} | {l['text']} |")
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
    lid, how = lessons.upsert(a.text, a.category, a.scope, a.source or "manual", a.rationale or "", origin="manual")
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


def cmd_enforce(a):
    if a.sub == "list":
        c = enforce.candidates()
        print(f"강제 중 {len(enforce.enforced())}/{enforce.MAX_ENFORCED}, hookify 설치: {'예' if enforce.hookify_installed() else '아니오'}")
        for l in c[:10]:
            ev, entry = enforce.build_hook(l)
            print(f"- {l['id']} [{l['category']}] {l['text']} → {ev}" + (f" ({entry.get('matcher')})" if entry.get('matcher') else "") + f"  evidence={l.get('evidence')}")
        if not c:
            print("(후보 없음: evidence ≥ 3, 반대표 0 인 교훈이 아직 없음)")
        for l in enforce.enforced():
            print(f"- [강제 중] {l['id']} {l['text']} → {l['enforced'].get('event')}")
    elif a.sub == "emit":
        l = next((x for x in lessons.load() if x["id"] == a.id), None)
        if not l:
            print("해당 id 없음"); return
        ev, entry = enforce.build_hook(l, a.event, a.matcher)
        print(json.dumps({"hooks": {ev: [entry]}}, ensure_ascii=False, indent=2))
    elif a.sub == "apply":
        p = enforce.apply(a.id, a.event, a.matcher)
        curate.write_rules()
        print(f"적용됨 → {p} (백업 생성). 새 세션부터 동작. 해제: enforce remove {a.id}")
    elif a.sub == "remove":
        print("해제됨" if enforce.remove(a.id) else "강제 항목 없음")
        curate.write_rules()


def cmd_weekly(a):
    print(weekly.report(apply=a.apply))


def cmd_recommend(a):
    recs = recommend_mod.recommend(Path(a.ecc_dir).expanduser(), Path(a.mine).expanduser() if a.mine else None,
                                   top=a.top, extra_terms=(a.terms or "").split(",") if a.terms else None)
    print(recommend_mod.render(recs, Path(a.ecc_dir).expanduser()))


def cmd_knowledge(a):
    if a.sub == "add":
        body = Path(a.body_file).read_text(encoding="utf-8") if a.body_file else (a.body or "")
        # sources: JSON 파일([{url,quote,published_at}]) 이 우선, 없으면 --sources "u1|u2"
        if a.sources_file:
            sources = json.loads(Path(a.sources_file).read_text(encoding="utf-8"))
        else:
            sources = [{"url": u.strip()} for u in (a.sources or "").split("|") if u.strip()]
        dup = [s_["url"] for s_ in sources if s_["url"] in knowledge.seen_urls()]
        if dup and not a.allow_dup:
            print("이미 다른 노트에 적재된 URL (중복 가능성): " + ", ".join(dup) + "  → 확인 후 --allow-dup 으로 재시도")
            return
        p = knowledge.add_note(a.title, a.topic or "general", a.summary or "", body, sources,
                               [k.strip() for k in a.keywords.split(",")] if a.keywords else None,
                               a.confidence or "medium", a.type or "finding", a.lang or "ko")
        print(f"저장됨(미검증): {p}\n→ 검증: knowledge verify \"{p}\"")
    elif a.sub == "verify":
        targets = [Path(a.query)] if a.query else [Path(n["path"]) for n in knowledge.notes() if n.get("status") == "unverified"]
        for t in targets:
            r = knowledge.verify(t)
            print(json.dumps(r, ensure_ascii=False))
        if not targets:
            print("검증할 미검증 노트 없음")
    elif a.sub == "list":
        ns = knowledge.notes()
        print(f"노트 {len(ns)}개 · 인덱스: {knowledge.kdir() / 'KNOWLEDGE.md'}")
        for n in ns:
            print(f"- [{n.get('status','?')}/{n.get('confidence','?')}] {n['title']} ({n.get('fetched_at','?')}→{n.get('verify_by','?')}) — {n['summary'][:80]}")
    elif a.sub == "stale":
        st = knowledge.stale()
        for n in st:
            print(f"- 재검증 필요: {n['title']} (검증기한 {n.get('verify_by')}) {n['path']}")
        if not st:
            print("(없음)")
    elif a.sub == "search":
        for n in knowledge.relevant(a.query or "", k=5, include_unverified=True):
            print(f"- [{n.get('status')}] {n['title']} — {n['summary'][:100]}\n  {n['path']}")
    elif a.sub == "status":
        knowledge.set_status(Path(a.query), a.set); print("ok")
    elif a.sub == "reindex":
        print("wrote", knowledge.rebuild_index())


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
    p = sp.add_parser("knowledge")
    p.add_argument("sub", choices=["add", "verify", "list", "stale", "search", "status", "reindex"])
    p.add_argument("query", nargs="?")
    p.add_argument("--title"); p.add_argument("--topic"); p.add_argument("--summary"); p.add_argument("--body")
    p.add_argument("--body-file"); p.add_argument("--sources", help="URL 들, | 구분")
    p.add_argument("--sources-file", help="JSON [{url, quote, published_at}]"); p.add_argument("--keywords", help="콤마 구분")
    p.add_argument("--confidence", choices=["low", "medium", "high"]); p.add_argument("--type", help="finding|tool|api-change|pricing|howto|opinion")
    p.add_argument("--lang"); p.add_argument("--allow-dup", action="store_true")
    p.add_argument("--set", help="status 값 (verified|unverified|contradicted|superseded)")
    p.set_defaults(f=cmd_knowledge)
    p = sp.add_parser("enforce")
    p.add_argument("sub", choices=["list", "emit", "apply", "remove"])
    p.add_argument("id", nargs="?"); p.add_argument("--event"); p.add_argument("--matcher")
    p.set_defaults(f=cmd_enforce)
    p = sp.add_parser("weekly"); p.add_argument("--apply", action="store_true", help="보관 제안을 실제 적용")
    p.set_defaults(f=cmd_weekly)
    p = sp.add_parser("recommend")
    p.add_argument("--ecc-dir", required=True); p.add_argument("--mine", default=str(data_dir() / "mine.json"))
    p.add_argument("--top", type=int, default=10); p.add_argument("--terms", help="추가 키워드, 콤마 구분")
    p.set_defaults(f=cmd_recommend)
    a = ap.parse_args()
    if not a.cmd:
        a = ap.parse_args(["list"])
    a.f(a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
