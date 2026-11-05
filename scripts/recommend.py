#!/usr/bin/env python3
"""ECC(또는 임의의 스킬 모음) 에서 '나에게 맞는 스킬만' 추천 (recommend).

왜 필요한가: ECC 는 스킬 314개를 담고 있고 설명만 ~100KB 가 매 세션 컨텍스트에 상시 로드된다.
사용 기록(mine.json 의 의도 분포·키워드)과 각 SKILL.md 의 description 을 키워드로 대조해
상위 N개만 고르고, 복사 명령을 만들어 준다. LLM 호출 없음.

점수 = (의도 매핑 가중) + (사용자 프롬프트 키워드 ∩ 스킬 설명 키워드) 의 가중합.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from common import keywords

# 사용자 요청 유형 → ECC 스킬 이름에 들어있을 법한 토큰. 왜 수동 매핑: 의도 라벨은 한국어, 스킬 이름은 영어라
# 키워드 겹침만으로는 연결이 안 된다. 사용자 분야(AI/검색) 를 조금 더 무겁게 둔다.
INTENT_TOKENS = {
    "검색/조사": ["research", "search", "retrieval", "scout", "documentation-lookup", "deep-research", "exa"],
    "코드작성": ["patterns", "tdd", "contract-first", "api-design"],
    "디버깅": ["debug", "verification", "error-handling", "regression", "introspection"],
    "리팩터/개선": ["refine", "code-quality", "performance", "simplif", "optimization"],
    "설명/리뷰": ["review", "code-tour", "onboarding", "explain", "change-impact"],
    "설정/환경": ["hookify", "configure", "config", "mcp-server", "harness", "skill-"],
    "AI/검색시스템": ["agent", "eval", "prompt", "rag", "retriev", "recsys", "llm", "benchmark", "iterative-retrieval", "search-first", "cost-aware", "prompt-caching", "token"],
    "문서/정리": ["docs", "documentation", "living-docs", "article", "writing"],
    "git/배포": ["git-workflow", "github-ops", "deployment", "conventional-commit", "delivery"],
}


def read_skills(ecc_dir: Path) -> list[dict]:
    out = []
    for sk in sorted((ecc_dir / "skills").glob("*/SKILL.md")):
        try:
            head = sk.read_text(encoding="utf-8", errors="ignore")[:2500]
        except OSError:
            continue
        m = re.search(r"^description:\s*(.+?)(?=\n\S|\Z)", head, re.S | re.M)
        desc = re.sub(r"\s+", " ", m.group(1)).strip().strip('"') if m else ""
        out.append({"name": sk.parent.name, "desc": desc[:400], "path": str(sk.parent)})
    return out


def recommend(ecc_dir: Path, mine_json: Path | None, top: int = 10, extra_terms: list[str] | None = None) -> list[dict]:
    skills = read_skills(ecc_dir)
    intents, user_kw = {}, set()
    if mine_json and mine_json.exists():
        m = json.loads(mine_json.read_text(encoding="utf-8"))
        intents = dict(m.get("intents", []))
        user_kw = {k for k, _ in m.get("keywords", [])[:80]}
    user_kw |= set(extra_terms or [])
    total = sum(intents.values()) or 1
    # 키워드 희소성(IDF) — 왜: "agent", "prompt" 처럼 스킬 수백 개에 다 들어가는 단어는 변별력이 없다.
    # 전체 스킬 중 몇 개에 등장하는지 세어, 많이 등장할수록 가중치를 낮춘다.
    import math
    desc_kws = {s["name"]: set(keywords(s["desc"], limit=40)) | set(s["name"].lower().split("-")) for s in skills}
    df: dict[str, int] = {}
    for kws in desc_kws.values():
        for k in kws:
            df[k] = df.get(k, 0) + 1
    n = max(1, len(skills))
    scored = []
    for s in skills:
        name_l = s["name"].lower()
        desc_l = s["desc"].lower()
        score, why = 0.0, []
        for intent, cnt in intents.items():
            w = cnt / total
            toks = INTENT_TOKENS.get(intent, [])
            # 이름에 있으면 강하게(3), 설명에만 있으면 약하게(1) — 이름은 저자가 고른 핵심어라서
            if any(t in name_l for t in toks):
                score += 3 * w; why.append(intent)
            elif any(t in desc_l for t in toks):
                score += 1 * w; why.append(intent)
        overlap = user_kw & desc_kws[s["name"]]
        if overlap:
            idf = sum(math.log(n / df.get(k, 1)) for k in overlap)
            score += 0.3 * idf
            top_terms = sorted(overlap, key=lambda k: df.get(k, 1))[:4]
            why.append("키워드:" + ",".join(top_terms))
        if score > 0:
            scored.append({**s, "score": round(score, 2), "why": sorted(set(why))})
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top]


def render(recs: list[dict], ecc_dir: Path, dest: str = "~/.claude/skills") -> str:
    if not recs:
        return "(추천할 스킬이 없습니다 — mine.json 이 비어 있거나 ECC 경로가 틀렸을 수 있음)"
    lines = ["| 스킬 | 점수 | 이유 | 설명 |", "|---|---|---|---|"]
    for r in recs:
        lines.append(f"| `{r['name']}` | {r['score']} | {' / '.join(r['why'])[:60]} | {r['desc'][:90]} |")
    lines.append("")
    lines.append("복사 명령 (필요한 것만 골라서):")
    lines.append("```bash")
    for r in recs:
        lines.append(f"cp -r \"{Path(r['path'])}\" {dest}/")
    lines.append("```")
    lines.append(f"참고: 통째 설치 대신 이렇게 고르는 이유 — ECC 스킬 설명 전체(~100KB)가 매 세션 상시 로드되기 때문. 한 달 뒤 `/skill-doctor` 로 안 쓴 것은 제거.")
    return "\n".join(lines)
