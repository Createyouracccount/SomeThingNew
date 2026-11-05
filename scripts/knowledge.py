#!/usr/bin/env python3
"""지식 노트 저장소 (knowledge) — 리서치 서브에이전트가 찾아온 외부 정보를 담는 곳.

교훈(lessons)과 다른 점:
- 교훈은 '나의 선호·방식'(짧고, 매 세션 로드). 지식은 '세상의 사실'(길고, 필요할 때만 읽음).
- 그래서 auto-memory 와 같은 구조: 한 줄 인덱스(KNOWLEDGE.md) + 토픽 파일. 인덱스만 검색하고 본문은 Read 로.

환각 방지 (근거: arXiv 2604.03173 — 딥리서치 에이전트 URL 10.7% 환각, URL 헬스체크 도구로 <1% 로 감소;
arXiv 2605.06635 — URL 이 살아 있어도 인용 페이지가 주장을 실제로 뒷받침하는 비율은 39~77%):
- 출처 URL 없는 노트는 저장 거부.
- 각 출처에 verbatim quote(≤40단어) 를 붙일 수 있고, `verify` 가 URL 을 다시 열어 (1) 응답 코드 (2) quote 포함 여부를 확인한다.
- status: unverified(기본) → verified / contradicted / superseded. 프롬프트 시 자동 주입(relevant) 은 verified 또는
  confidence=high 인 노트만 쓴다. 미검증 노트는 인덱스에만 보인다.
- fetched_at / verify_by (기본 90일, api-change·pricing 류는 30일). 오래된 사실은 weekly 가 재검증을 제안.
- seen.jsonl 로 URL 중복 적재 방지, log.md 에 모든 적재·검증을 추가 기록(append-only).
"""
from __future__ import annotations

import json
import re
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path

from common import append_jsonl, data_dir, keywords, now_iso, read_jsonl, today

VERIFY_DAYS = {"api-change": 30, "pricing": 30, "default": 90}
SHORT_LIVED = {"api-change", "pricing", "tool"}


def kdir() -> Path:
    d = data_dir() / "knowledge"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _log(msg: str) -> None:
    with (kdir() / "log.md").open("a", encoding="utf-8") as f:
        f.write(f"- {now_iso()} {msg}\n")


def _slug(title: str) -> str:
    s = re.sub(r"[^0-9A-Za-z가-힣]+", "-", title.strip()).strip("-").lower()
    return (s[:60] or "note") + "-" + today()


def seen_urls() -> set[str]:
    return {r.get("url") for r in read_jsonl(kdir() / "seen.jsonl")}


def add_note(title: str, topic: str, summary: str, body: str, sources: list[dict],
             kws: list[str] | None = None, confidence: str = "medium", ntype: str = "finding",
             lang: str = "ko", status: str = "unverified") -> Path:
    """sources: [{"url":..., "quote": "...", "published_at": "..."}]"""
    sources = [s for s in sources if s.get("url")]
    if not sources:
        raise SystemExit("출처(sources) 없는 노트는 저장하지 않습니다 — 최소 1개 URL 필요")
    kws = kws or keywords(title + " " + summary, limit=12)
    # 증거 기준: 독립 출처 2개 미만이면 high 를 허용하지 않는다(논문 1편 = 근거 1개). 호출자가 high 를 줘도 내린다.
    hosts = {s_["url"].split("/")[2] if "//" in s_["url"] else s_["url"] for s_ in sources}
    if len(hosts) < 2 and confidence == "high":
        confidence = "medium"
    if len(sources) < 2:
        confidence = "low" if confidence != "medium" else "medium"
    days = VERIFY_DAYS.get(ntype, VERIFY_DAYS["default"]) if ntype in SHORT_LIVED or ntype in VERIFY_DAYS else VERIFY_DAYS["default"]
    verify_by = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
    path = kdir() / (_slug(title) + ".md")
    fm = ["---", f"title: {title}", f"topic: {topic}", f"type: {ntype}", f"lang: {lang}",
          f"fetched_at: {today()}", f"verify_by: {verify_by}", f"confidence: {confidence}", f"status: {status}",
          "keywords: [" + ", ".join(kws) + "]", "sources:"]
    for s in sources:
        fm.append(f"  - url: {s['url']}")
        if s.get("quote"):
            fm.append(f"    quote: {json.dumps(s['quote'], ensure_ascii=False)}")
        if s.get("published_at"):
            fm.append(f"    published_at: {s['published_at']}")
    fm += ["---", "", f"# {title}", "", f"**요약**: {summary}", "", body.strip(), "", "## 출처"]
    fm += [f"- {s['url']}" + (f' — "{s["quote"]}"' if s.get("quote") else "") for s in sources]
    path.write_text("\n".join(fm) + "\n", encoding="utf-8")
    for s in sources:
        if s["url"] not in seen_urls():
            append_jsonl(kdir() / "seen.jsonl", {"url": s["url"], "first_seen": today(), "note": path.name})
    _log(f"ingest `{path.name}` ({len(sources)} sources, {status}, {confidence})")
    rebuild_index()
    return path


def _parse(p: Path) -> dict:
    out = {"path": str(p), "title": p.stem, "keywords": [], "summary": "", "sources": []}
    try:
        txt = p.read_text(encoding="utf-8")
    except OSError:
        return out
    m = re.match(r"---\n(.*?)\n---\n(.*)", txt, re.S)
    if not m:
        return out
    cur = None
    for line in m.group(1).splitlines():
        if line.startswith("  - url:"):
            cur = {"url": line.split("url:", 1)[1].strip()}; out["sources"].append(cur)
        elif line.startswith("    ") and cur is not None and ":" in line:
            k, v = line.strip().split(":", 1)
            v = v.strip()
            cur[k] = json.loads(v) if v.startswith('"') else v
        elif ":" in line and not line.startswith(" "):
            k, v = line.split(":", 1); v = v.strip()
            if k == "keywords":
                out["keywords"] = [x.strip() for x in v.strip("[]").split(",") if x.strip()]
            elif k != "sources":
                out[k.strip()] = v
    sm = re.search(r"\*\*요약\*\*:\s*(.+)", m.group(2))
    if sm:
        out["summary"] = sm.group(1).strip()
    return out


def notes() -> list[dict]:
    return [_parse(p) for p in sorted(kdir().glob("*.md")) if p.name not in ("KNOWLEDGE.md", "log.md")]


def rebuild_index() -> Path:
    idx = kdir() / "KNOWLEDGE.md"
    lines = ["# 지식 노트 인덱스 (self-tuner, 자동 생성)",
             "<!-- 한 줄 = 노트 하나. 본문은 필요할 때 Read 로 연다. [status/confidence] -->", ""]
    for n in notes():
        lines.append(f"- [{n['title']}]({Path(n['path']).name}) [{n.get('status','?')}/{n.get('confidence','?')}] — "
                     f"{n['summary'][:110]} (수집 {n.get('fetched_at','?')}, 검증기한 {n.get('verify_by','?')}) #{' #'.join(n['keywords'][:6])}")
    idx.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return idx


def stale() -> list[dict]:
    t = today()
    return [n for n in notes() if n.get("verify_by", "9999") < t and n.get("status") != "superseded"]


def relevant(text: str, k: int = 2, include_unverified: bool = False) -> list[dict]:
    """프롬프트와 키워드가 겹치는 노트. 기본은 verified 또는 confidence=high 만 — 미검증 사실을 자동 주입하지 않기 위해."""
    kws = set(keywords(text, limit=12))
    if not kws:
        return []
    scored = []
    for n in notes():
        if not include_unverified and not (n.get("status") == "verified" or n.get("confidence") == "high"):
            continue
        if n.get("status") in ("superseded", "contradicted"):
            continue
        ov = len(kws & set(n["keywords"]))
        if ov:
            scored.append((ov, n))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [n for _, n in scored[:k]]


def _fetch(url: str, timeout: int = 20) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (self-tuner knowledge verify)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(1_500_000).decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:
        return 0, ""


def _norm(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).lower()


def verify(path: Path) -> dict:
    """URL 재조회 + quote 포함 확인. 결과를 frontmatter 의 status/confidence/verified_at 에 반영한다."""
    n = _parse(path)
    results, ok_urls, ok_quotes, quotes = [], 0, 0, 0
    for s in n["sources"]:
        code, html = _fetch(s["url"])
        alive = 200 <= code < 400
        ok_urls += alive
        q_ok = None
        if s.get("quote"):
            quotes += 1
            q_ok = alive and _norm(s["quote"])[:120] in _norm(html)
            ok_quotes += bool(q_ok)
        results.append({"url": s["url"], "http": code, "quote_found": q_ok})
    if ok_urls == 0:
        status, conf = "unverified", "low"
    elif quotes and ok_quotes == 0:
        status, conf = "contradicted", "low"      # URL 은 살아있지만 인용이 없음 → 가장 위험한 경우
    elif quotes and ok_quotes >= 1 and ok_urls >= 2:
        status, conf = "verified", "high"
    elif ok_quotes >= 1 or ok_urls >= 2:
        status, conf = "verified", "medium"
    else:
        status, conf = "unverified", "low"
    txt = path.read_text(encoding="utf-8")
    txt = re.sub(r"^status: .*$", f"status: {status}", txt, count=1, flags=re.M)
    txt = re.sub(r"^confidence: .*$", f"confidence: {conf}", txt, count=1, flags=re.M)
    if "verified_at:" in txt:
        txt = re.sub(r"^verified_at: .*$", f"verified_at: {today()}", txt, count=1, flags=re.M)
    else:
        txt = txt.replace("\n---\n", f"\nverified_at: {today()}\n---\n", 1)
    path.write_text(txt, encoding="utf-8")
    _log(f"verify `{path.name}` → {status}/{conf} ({ok_urls}/{len(n['sources'])} urls alive, {ok_quotes}/{quotes} quotes found)")
    rebuild_index()
    return {"path": str(path), "status": status, "confidence": conf, "results": results}


def set_status(path: Path, status: str) -> None:
    txt = path.read_text(encoding="utf-8")
    txt = re.sub(r"^status: .*$", f"status: {status}", txt, count=1, flags=re.M)
    path.write_text(txt, encoding="utf-8")
    _log(f"status `{path.name}` → {status}")
    rebuild_index()
