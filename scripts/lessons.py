#!/usr/bin/env python3
"""교훈(lesson) 저장소 – ACE 논문의 '아이템화된 델타 업데이트' 구현.

핵심 규칙 (왜):
- 교훈은 id가 있는 한 줄 단위다. LLM이 전체 파일을 다시 쓰는 일은 절대 없다.
  → ACE가 보고한 'context collapse'(18k 토큰 → 122 토큰으로 붕괴) 방지.
- helpful / harmful 카운터를 가진다(ExpeL의 UPVOTE/DOWNVOTE). 점수 = 증거 + 도움 − 2×해악.
  해악에 2배 가중을 두는 이유: 잘못된 교훈 하나가 맞는 교훈 둘보다 비용이 크다(Misevolution 논문).
- 시간 감쇠: 오래 안 쓰인 교훈은 순위가 내려가고, 결국 보관(archived)된다.
- 쓰기 시 조정(Mem0): 새 교훈이 기존 교훈과 키워드가 크게 겹치면 새로 추가하지 않고
  기존 항목의 evidence를 올리고 문장을 갱신한다.
"""
from __future__ import annotations

import hashlib
import math
import time
from pathlib import Path

from common import LESSONS, data_dir, keywords, now_iso, read_jsonl, sanitize, write_jsonl

VALID_CATEGORIES = {"preference", "workflow", "pitfall", "tool", "project", "domain"}


def _id(text: str) -> str:
    return "L" + hashlib.sha1(text.strip().lower().encode("utf-8")).hexdigest()[:8]


def load() -> list[dict]:
    return read_jsonl(data_dir() / LESSONS)


def save(rows: list[dict]) -> None:
    write_jsonl(data_dir() / LESSONS, rows)


def score(l: dict, now: float | None = None) -> float:
    now = now or time.time()
    try:
        last = time.mktime(time.strptime(l.get("last_seen", l["created"])[:19], "%Y-%m-%dT%H:%M:%S"))
    except Exception:
        last = now
    age_days = max(0.0, (now - last) / 86400)
    # 왜 반감기 60일인가: 개인 선호는 느리게 변하므로 분 단위 감쇠는 과하고, 영구 유지는 stale을 만든다.
    decay = math.pow(0.5, age_days / 60.0)
    base = l.get("evidence", 1) + l.get("helpful", 0) - 2 * l.get("harmful", 0)
    # 결과 기반 보너스(outcomes.py): 주입 뒤 사용자가 넘어갔거나 테스트가 통과하면 +, 교정·재요청·테스트 실패면 −
    oc = l.get("outcomes") or {}
    base += 0.20 * oc.get("worked", 0) + 0.05 * oc.get("partial", 0) - 0.05 * oc.get("unknown", 0) - 0.30 * oc.get("failed", 0)
    pinned = 100 if l.get("pinned") else 0
    return pinned + base * decay


def _overlap(a: list[str], b: list[str]) -> float:
    """작은 집합 기준 겹침 비율. 왜 Jaccard 가 아닌가: '기존 교훈 + 조건 하나 추가' 같은
    REFINE 은 합집합이 커져 Jaccard 가 떨어진다. 짧은 쪽이 거의 포함되면 같은 교훈으로 본다."""
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    return len(sa & sb) / min(len(sa), len(sb))


def distinct_sessions(l: dict) -> int:
    """서로 다른 세션에서 몇 번 관찰됐나. 왜: 한 세션 안의 반복은 그 작업의 맥락일 뿐이고,
    '다른 날 다른 작업에서 다시 나온' 교훈만 믿을 만하다(reSolve 의 '독립 재현', Treude&Baltes 의 회고 노이즈 결과)."""
    return len({s for s in l.get("sources", []) if s and s != "manual"}) + (1 if "manual" in l.get("sources", []) else 0)


def is_confirmed(l: dict) -> bool:
    """rules 뷰(항상 로드)에 실릴 자격: 사람이 직접 넣었거나(pinned/manual), 2개 이상 세션에서 독립 관찰."""
    return bool(l.get("pinned")) or l.get("origin") == "manual" or distinct_sessions(l) >= 2


def upsert(text: str, category: str, scope: str, source: str, rationale: str = "", origin: str = "reflector") -> tuple[str, str]:
    """교훈을 추가하거나 기존 항목에 합친다. 반환: (id, 'added'|'merged')."""
    text = sanitize(text.strip().rstrip(".").strip(), limit=200)
    if len(text) < 8:
        return ("", "skipped")
    if category not in VALID_CATEGORIES:
        category = "workflow"
    rows = load()
    kws = keywords(text, limit=10)
    for l in rows:
        if l.get("scope") != scope or l.get("status") == "archived":
            continue
        # 왜 0.75인가: 짧은 쪽 키워드의 3/4 이상이 포함되면 사실상 같은 교훈(REFINE)이다.
        if l["id"] == _id(text) or _overlap(kws, l.get("keywords", [])) >= 0.75:
            l["evidence"] = l.get("evidence", 1) + 1
            l["last_seen"] = now_iso()
            l.setdefault("sources", []).append(source)
            l["sources"] = l["sources"][-10:]
            # 더 긴/구체적인 문장으로 갱신(REFINE 연산). 짧아지는 쪽(brevity bias)으로는 안 바꾼다.
            if len(text) > len(l["text"]):
                l["text"] = text
                l["keywords"] = kws
            save(rows)
            return (l["id"], "merged")
    rows.append({
        "id": _id(text), "text": text, "category": category, "scope": scope,
        "keywords": kws, "rationale": sanitize(rationale, 300), "origin": origin,
        "evidence": 1, "helpful": 0, "harmful": 0, "status": "active",
        "created": now_iso(), "last_seen": now_iso(), "sources": [source],
    })
    save(rows)
    return (rows[-1]["id"], "added")


def vote(lesson_id: str, good: bool) -> bool:
    rows = load()
    for l in rows:
        if l["id"] == lesson_id:
            l["helpful" if good else "harmful"] = l.get("helpful" if good else "harmful", 0) + 1
            l["last_seen"] = now_iso()
            # 왜 자동 보관인가: 해악 3표 이상이고 점수가 0 이하면 사용자가 지우기 전에 스스로 물러난다.
            if l["harmful"] >= 3 and score(l) <= 0:
                l["status"] = "archived"
            save(rows)
            return True
    return False


def set_status(lesson_id: str, status: str) -> bool:
    rows = load()
    for l in rows:
        if l["id"] == lesson_id:
            l["status"] = status
            if status == "pinned":
                l["pinned"] = True
                l["status"] = "active"
            save(rows)
            return True
    return False


def top(scope_filter: set[str] | None = None, k: int = 20, min_score: float = 0.5) -> list[dict]:
    now = time.time()
    rows = [l for l in load() if l.get("status", "active") == "active"]
    if scope_filter is not None:
        rows = [l for l in rows if l.get("scope") in scope_filter]
    rows = [l for l in rows if score(l, now) >= min_score]
    rows.sort(key=lambda l: score(l, now), reverse=True)
    return rows[:k]
