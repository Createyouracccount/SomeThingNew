#!/usr/bin/env python3
"""부트스트랩: 기존 Claude Code 기록(~/.claude/projects/**/*.jsonl, memory/)을 뒤져
'내가 자주 하는 말', '교정 패턴', '자주 쓰는 도구', '프로젝트별 주제'를 뽑는다.

왜 이 스크립트가 먼저인가: 사용자가 "메모리에서 뒤져보면 주로 하는 말들이 있을 것"이라 했다.
자가 개선 루프는 빈 상태에서 시작하면 수십 세션이 지나야 쓸 만해진다(cold start).
과거 로그를 한 번 훑어 초기 교훈과 스킬 후보를 만들어 두면 첫날부터 효과가 난다
(AWM의 'offline induction' 단계에 해당).

사용법:
  python3 mine_history.py                 # 요약 리포트를 stdout에 마크다운으로
  python3 mine_history.py --json out.json # 스킬 후보/통계를 JSON으로도 저장
  python3 mine_history.py --days 90       # 최근 90일만
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import claude_home, keywords, looks_like_correction  # noqa: E402


def iter_user_prompts(jsonl: Path):
    """transcript에서 '사람이 직접 친' 프롬프트만 뽑는다.

    왜 tool_result를 거르나: user 타입 레코드의 대부분은 도구 결과(tool_result)다.
    content가 문자열이거나 text 블록만 있고, isSidechain(서브에이전트)이 아니고,
    promptSource/turnOrigin이 사람인 것만 '내 말'이다.
    """
    try:
        with jsonl.open(encoding="utf-8") as f:
            for line in f:
                try:
                    o = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if o.get("type") != "user" or o.get("isSidechain"):
                    continue
                if o.get("turnOrigin") not in (None, "human"):
                    continue
                msg = o.get("message", {})
                c = msg.get("content")
                if isinstance(c, list):
                    texts = [b.get("text", "") for b in c if b.get("type") == "text"]
                    if not texts or any(b.get("type") == "tool_result" for b in c):
                        continue
                    c = "\n".join(texts)
                if not isinstance(c, str):
                    continue
                c = c.strip()
                # 왜 system-reminder/명령 확장을 빼나: 사람이 친 말이 아니다
                if not c or c.startswith("<") or c.startswith("/") and len(c) < 40:
                    continue
                yield {
                    "text": c,
                    "ts": o.get("timestamp"),
                    "cwd": o.get("cwd"),
                    "session": o.get("sessionId"),
                    "project": jsonl.parent.name,
                }
    except OSError:
        return


def iter_tool_uses(jsonl: Path):
    try:
        with jsonl.open(encoding="utf-8") as f:
            for line in f:
                if '"tool_use"' not in line:
                    continue
                try:
                    o = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if o.get("type") != "assistant":
                    continue
                for b in o.get("message", {}).get("content", []):
                    if b.get("type") == "tool_use":
                        yield b.get("name", "?")
    except OSError:
        return


def read_auto_memory(projects_dir: Path) -> dict[str, list[str]]:
    """auto-memory 디렉터리(MEMORY.md + 토픽 파일)를 읽는다. 이미 Claude가 적어둔 교훈은
    중복 추출하지 않기 위한 '기존 지식'으로 쓴다."""
    out = {}
    for mem in projects_dir.glob("*/memory/*.md"):
        try:
            out.setdefault(mem.parent.parent.name, []).append(f"[{mem.name}] " + mem.read_text(encoding="utf-8")[:1500])
        except OSError:
            pass
    return out


# 의도(intent) 라벨링: 자주 하는 '질문 유형'을 거칠게 분류한다.
# 왜 규칙 기반인가: 수천 개 프롬프트를 LLM에 넣으면 비싸고, 여기서는 '어떤 유형이 많은가'만 알면 된다.
INTENTS = {
    "검색/조사": r"(검색|조사|찾아|알아봐|리서치|research|search|논문|paper|최신|trend)",
    "코드작성": r"(만들어|구현|작성|짜|코드|함수|클래스|implement|build|write|create|add)",
    "디버깅": r"(에러|오류|버그|안 ?돼|실패|fix|error|bug|crash|debug|왜 안)",
    "리팩터/개선": r"(리팩|개선|최적화|정리|refactor|optimi|clean|simplif|성능)",
    "설명/리뷰": r"(설명|리뷰|분석|이해|어떻게 동작|explain|review|analy|what does)",
    "설정/환경": r"(설정|환경|설치|config|install|setup|환경변수|hook|plugin|skill|mcp)",
    "AI/검색시스템": r"(rag|임베딩|embedding|벡터|vector|llm|프롬프트|prompt|에이전트|agent|파인튠|fine-?tun|검색 ?엔진|elastic|retriev|rerank)",
    "문서/정리": r"(문서|readme|정리해|요약|summar|doc|markdown|보고서|report)",
    "git/배포": r"(커밋|commit|push|pr|머지|merge|배포|deploy|release)",
}
_INTENTS = {k: re.compile(v, re.IGNORECASE) for k, v in INTENTS.items()}


def label_intents(text: str) -> list[str]:
    head = text[:400]
    return [k for k, r in _INTENTS.items() if r.search(head)] or ["기타"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=0, help="최근 N일만 (0=전체)")
    ap.add_argument("--json", type=Path, help="후보/통계를 JSON으로 저장")
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--projects-dir", type=Path, default=claude_home() / "projects")
    args = ap.parse_args()

    cutoff = None
    if args.days:
        cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)

    prompts, tools = [], collections.Counter()
    sessions = set()
    for jsonl in sorted(args.projects_dir.glob("*/*.jsonl")):
        for p in iter_user_prompts(jsonl):
            if cutoff and p["ts"]:
                try:
                    if datetime.fromisoformat(p["ts"].replace("Z", "+00:00")) < cutoff:
                        continue
                except ValueError:
                    pass
            prompts.append(p)
            sessions.add(p["session"])
        for t in iter_tool_uses(jsonl):
            tools[t] += 1

    memory = read_auto_memory(args.projects_dir)

    # --- 통계 ---
    by_project = collections.Counter(p["project"] for p in prompts)
    intents = collections.Counter()
    kw = collections.Counter()
    corrections = []
    for p in prompts:
        for i in label_intents(p["text"]):
            intents[i] += 1
        kw.update(keywords(p["text"], limit=8))
        if looks_like_correction(p["text"]):
            corrections.append(p)

    # --- 스킬 후보: 같은 의도 + 같은 상위 키워드가 여러 세션에 걸쳐 반복되면 후보 ---
    # 왜 '여러 세션'을 조건으로 두나: 한 세션 안에서 반복된 말은 그 작업의 맥락일 뿐,
    # 세션을 넘어 반복되는 요청이야말로 스킬로 굳힐 가치가 있다(AWM 논문의 핵심 조건).
    bucket: dict[tuple, dict] = {}
    for p in prompts:
        ks = keywords(p["text"], limit=6)
        if not ks:
            continue
        for i in label_intents(p["text"]):
            key = (i, ks[0])
            b = bucket.setdefault(key, {"intent": i, "keyword": ks[0], "count": 0, "sessions": set(), "examples": []})
            b["count"] += 1
            b["sessions"].add(p["session"])
            if len(b["examples"]) < 3:
                b["examples"].append(p["text"][:160].replace("\n", " "))
    candidates = [
        {**b, "sessions": len(b["sessions"])}
        for b in bucket.values()
        if b["count"] >= 3 and len(b["sessions"]) >= 2
    ]
    candidates.sort(key=lambda b: (b["sessions"], b["count"]), reverse=True)

    # --- 리포트 ---
    out = []
    out.append(f"# Claude Code 사용 기록 마이닝 리포트\n")
    out.append(f"- 스캔 디렉터리: `{args.projects_dir}`")
    out.append(f"- 사람 프롬프트 {len(prompts)}개 / 세션 {len(sessions)}개 / 프로젝트 {len(by_project)}개"
               + (f" / 최근 {args.days}일" if args.days else ""))
    out.append(f"- 교정으로 보이는 프롬프트: {len(corrections)}개 ({(len(corrections)/len(prompts)*100 if prompts else 0):.1f}%)\n")
    out.append("## 프로젝트별 프롬프트 수")
    for k, v in by_project.most_common(15):
        out.append(f"- {k}: {v}")
    out.append("\n## 요청 유형 분포")
    for k, v in intents.most_common():
        out.append(f"- {k}: {v}")
    out.append("\n## 자주 등장하는 키워드")
    out.append(", ".join(f"{k}({v})" for k, v in kw.most_common(args.top)))
    out.append("\n## 자주 쓰인 도구")
    out.append(", ".join(f"{k}({v})" for k, v in tools.most_common(15)))
    out.append("\n## 스킬 후보 (여러 세션에 걸쳐 반복된 요청)")
    if not candidates:
        out.append("- (아직 없음: 세션이 더 쌓이면 다시 실행)")
    for c in candidates[:15]:
        out.append(f"- **{c['intent']} / {c['keyword']}** — {c['count']}회, {c['sessions']}세션")
        for e in c["examples"]:
            out.append(f"  - 예: {e}")
    out.append("\n## 교정 프롬프트 샘플 (교훈 추출 대상)")
    for p in corrections[:15]:
        out.append(f"- [{p['project']}] {p['text'][:140].replace(chr(10),' ')}")
    if memory:
        out.append("\n## 이미 auto-memory에 기록된 내용 (중복 추출 금지)")
        for proj, items in memory.items():
            out.append(f"- {proj}: {len(items)}개 파일")
    print("\n".join(out))

    if args.json:
        args.json.write_text(json.dumps({
            "generated": datetime.now().isoformat(timespec="seconds"),
            "prompts": len(prompts), "sessions": len(sessions),
            "intents": intents.most_common(), "keywords": kw.most_common(50),
            "tools": tools.most_common(), "candidates": candidates[:30],
            "corrections": [{"project": p["project"], "text": p["text"][:300]} for p in corrections[:60]],
            "memory_projects": list(memory.keys()),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
