#!/usr/bin/env python3
"""큐레이터: lessons.jsonl → ~/.claude/rules/self-tuner.md (전역 교훈 파일) 재생성.

왜 rules 파일인가: ~/.claude/rules/*.md 는 Claude Code가 모든 프로젝트 세션에 자동 로드한다.
훅으로 매번 주입하는 것보다 (1) 사용자가 눈으로 보고 고칠 수 있고 (2) /doctor prompt-audit 로
CLAUDE.md와의 충돌 검사를 받을 수 있다. 프로젝트 범위 교훈은 SessionStart 훅이 cwd를 보고 주입한다.

왜 '재생성'인데 ACE 위반이 아닌가: 진실의 원본(source of truth)은 lessons.jsonl이고,
rules 파일은 그것의 '뷰'다. LLM은 이 파일을 직접 쓰지 않는다 — 정렬·상위 K개 선택만 코드가 한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import RULES_FILE, claude_home, today  # noqa: E402
import lessons  # noqa: E402

MAX_LINES = 40  # 왜 40줄인가: 공식 가이드가 CLAUDE.md류 파일을 200줄 이하로 권고. 교훈은 그중 일부만 차지해야 한다.

HEADER = """# self-tuner: 세션에서 배운 전역 교훈 (자동 생성, {date})
<!-- 이 파일은 self-tuner 플러그인이 lessons.jsonl 에서 생성한 '뷰'입니다.
     직접 고치려면 /self-tuner:lessons 로 항목을 pin/archive 하거나 lessons.jsonl 을 편집하세요.
     각 줄 끝의 [Lxxxxxxxx] 는 교훈 id — 도움이 됐으면 /self-tuner:lessons good <id>, 틀렸으면 bad <id>. -->
"""

CATEGORY_KO = {
    "preference": "선호", "workflow": "작업 방식", "pitfall": "주의", "tool": "도구",
    "project": "프로젝트", "domain": "도메인 지식",
}


def render(k: int = MAX_LINES - 8) -> str:
    rows = lessons.top(scope_filter={"global"}, k=k)
    lines = [HEADER.format(date=today())]
    if not rows:
        lines.append("_(아직 전역 교훈 없음 — 세션이 쌓이면 Stop 훅의 리플렉터가 채웁니다)_")
        return "\n".join(lines) + "\n"
    by_cat: dict[str, list[dict]] = {}
    for l in rows:
        by_cat.setdefault(l.get("category", "workflow"), []).append(l)
    for cat in ("preference", "workflow", "pitfall", "tool", "domain", "project"):
        if cat not in by_cat:
            continue
        lines.append(f"\n## {CATEGORY_KO.get(cat, cat)}")
        for l in by_cat[cat]:
            lines.append(f"- {l['text']} [{l['id']}]")
    return "\n".join(lines) + "\n"


def write_rules() -> Path:
    rules_dir = claude_home() / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    out = rules_dir / RULES_FILE
    content = render()
    # 왜 변경 없으면 안 쓰나: 파일 mtime 변화가 InstructionsLoaded/FileChanged 류 이벤트를 괜히 깨운다.
    if out.exists() and out.read_text(encoding="utf-8") == content:
        return out
    out.write_text(content, encoding="utf-8")
    return out


if __name__ == "__main__":
    p = write_rules()
    print(f"wrote {p}")
