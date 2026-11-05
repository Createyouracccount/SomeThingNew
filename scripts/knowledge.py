#!/usr/bin/env python3
"""지식 노트 저장소 (knowledge) — 리서치 서브에이전트가 찾아온 외부 정보를 담는 곳.

교훈(lessons)과 다른 점:
- 교훈은 '나의 선호·방식'(짧고, 매 세션 로드). 지식은 '세상의 사실'(길고, 필요할 때만 읽음).
- 그래서 지식은 auto-memory 와 같은 구조를 쓴다: 한 줄짜리 인덱스(KNOWLEDGE.md) + 토픽 파일.
  인덱스만 검색하고, 본문은 Claude 가 Read 로 필요할 때 연다(점진 공개 → 컨텍스트 절약).
- 모든 노트는 fetched_at / verify_by 를 가진다. 왜: 외부 사실은 썩는다. 90일 지나면 weekly 가 재검증을 제안한다.
- 모든 주장에는 출처 URL 이 붙어야 한다. 왜: 리서치 에이전트의 환각을 막는 최소 장치.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path

from common import data_dir, keywords, today

VERIFY_DAYS = 90


def kdir() -> Path:
    d = data_dir() / "knowledge"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _slug(title: str) -> str:
    s = re.sub(r"[^0-9A-Za-z가-힣]+", "-", title.strip()).strip("-").lower()
    return (s[:60] or "note") + "-" + today()


def add_note(title: str, topic: str, summary: str, body: str, sources: list[str],
             kws: list[str] | None = None, confidence: str = "medium") -> Path:
    if not sources:
        raise SystemExit("출처(sources) 없는 노트는 저장하지 않습니다 — 최소 1개 URL 필요")
    kws = kws or keywords(title + " " + summary, limit=12)
    verify_by = (datetime.now() + timedelta(days=VERIFY_DAYS)).strftime("%Y-%m-%d")
    path = kdir() / (_slug(title) + ".md")
    fm = [
        "---", f"title: {title}", f"topic: {topic}", f"fetched_at: {today()}", f"verify_by: {verify_by}",
        f"confidence: {confidence}", "keywords: [" + ", ".join(kws) + "]",
        "sources:", *[f"  - {u}" for u in sources], "---", "",
        f"# {title}", "", f"**요약**: {summary}", "", body.strip(), "",
        "## 출처", *[f"- {u}" for u in sources], "",
    ]
    path.write_text("\n".join(fm), encoding="utf-8")
    rebuild_index()
    return path


def _parse_frontmatter(p: Path) -> dict:
    out = {"path": str(p), "title": p.stem, "keywords": [], "summary": ""}
    try:
        txt = p.read_text(encoding="utf-8")
    except OSError:
        return out
    m = re.match(r"---\n(.*?)\n---\n(.*)", txt, re.S)
    if not m:
        return out
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith(" "):
            k, v = line.split(":", 1)
            v = v.strip()
            if k == "keywords":
                out["keywords"] = [x.strip() for x in v.strip("[]").split(",") if x.strip()]
            else:
                out[k.strip()] = v
    sm = re.search(r"\*\*요약\*\*:\s*(.+)", m.group(2))
    if sm:
        out["summary"] = sm.group(1).strip()
    return out


def notes() -> list[dict]:
    return [_parse_frontmatter(p) for p in sorted(kdir().glob("*.md")) if p.name != "KNOWLEDGE.md"]


def rebuild_index() -> Path:
    idx = kdir() / "KNOWLEDGE.md"
    lines = ["# 지식 노트 인덱스 (self-tuner, 자동 생성)", "<!-- 한 줄 = 노트 하나. 본문은 필요할 때 Read 로 연다. -->", ""]
    for n in notes():
        lines.append(f"- [{n['title']}]({Path(n['path']).name}) — {n['summary'][:120]} (수집 {n.get('fetched_at','?')}, 검증기한 {n.get('verify_by','?')}) #{' #'.join(n['keywords'][:6])}")
    idx.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return idx


def stale() -> list[dict]:
    t = today()
    return [n for n in notes() if n.get("verify_by", "9999") < t]


def relevant(text: str, k: int = 2) -> list[dict]:
    kws = set(keywords(text, limit=12))
    if not kws:
        return []
    scored = []
    for n in notes():
        ov = len(kws & set(n["keywords"]))
        if ov:
            scored.append((ov, n))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [n for _, n in scored[:k]]
