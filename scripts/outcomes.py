#!/usr/bin/env python3
"""결과 기반 채점 (outcomes) — "주입한 교훈이 실제로 도움이 됐나"를 사람 투표 없이 추정한다.

근거(2026-11 조사):
- 다음 사용자 턴의 암묵 피드백: 교정("아니, …")·같은 요청 반복(rephrase)은 정밀도가 높은 '실패' 신호
  (EMNLP 2025 피드백 분류: 정밀도 100%/재현율 69%; WildFeedback DSAT 정밀도 83%). 감성(sentiment)만으로는 판단하지 않는다.
- 테스트 통과는 결정론적 '성공' 신호(lessons-learned 평가 하네스, TokenEconomizer).
- roampal-core 의 라벨/델타(worked +0.20, partial +0.05, unknown -0.05, failed -0.30)를 차용. 단 '주 모델에게 점수를 묻는' 대신
  결정론 규칙만 쓴다. 왜: LLM 심판은 피드백 기반 수정을 체계적으로 놓친다(arXiv 2609.02859).

구현:
- 훅이 교훈을 주입할 때마다 episodes 에 {kind:"inject", lesson_ids, prompt_index} 를 남긴다.
- 세션 끝 리플렉터(LLM, 비동기)가 '주입된 교훈 + 그 뒤 사용자 턴' 을 읽고 worked/partial/unknown/failed 라벨을 준다.
  (이전 버전의 정규식·키워드 겹침 판정은 오탐이 많아 제거)
- PostToolUse(Bash) 테스트 명령 성공: 최근 주입 교훈 → worked. PostToolUseFailure 테스트 실패 + 겹침 → failed.
- 교훈의 outcomes 카운터는 점수에 반영: +0.2·worked − 0.3·failed. 다중 주입 턴은 델타를 나눠 희석한다.
"""
from __future__ import annotations

import re

from common import EPISODES, append_jsonl, data_dir, now_iso, read_jsonl
import lessons

TEST_CMD = re.compile(r"\b(pytest|python -m pytest|npm (run )?test|pnpm test|yarn test|go test|cargo test|claude plugin eval|make test|tox|jest|vitest)\b")
DELTA = {"worked": 0.20, "partial": 0.05, "unknown": -0.05, "failed": -0.30}
WINDOW = 3  # 왜 3: 교훈의 효과는 바로 다음 1~3턴에 드러난다. 그 뒤는 다른 요인이 섞인다.


def log_injection(session: str | None, lesson_ids: list[str], trigger: str) -> None:
    if not session or not lesson_ids:
        return
    append_jsonl(data_dir() / EPISODES, {"t": now_iso(), "kind": "inject", "session": session,
                                          "lesson_ids": lesson_ids, "trigger": trigger,
                                          "prompt_index": _prompt_count(session)})


def _prompt_count(session: str) -> int:
    return sum(1 for e in read_jsonl(data_dir() / EPISODES) if e.get("session") == session and e.get("kind") == "prompt")


def recent_injections(session: str, window: int = WINDOW) -> list[dict]:
    eps = read_jsonl(data_dir() / EPISODES)
    cur = sum(1 for e in eps if e.get("session") == session and e.get("kind") == "prompt")
    scored = {(e.get("prompt_index"), tuple(e.get("lesson_ids", []))) for e in eps
              if e.get("session") == session and e.get("kind") == "inject_scored"}
    return [e for e in eps if e.get("session") == session and e.get("kind") == "inject"
            and cur - e.get("prompt_index", -99) <= window
            and (e.get("prompt_index"), tuple(e.get("lesson_ids", []))) not in scored]


def previous_prompt(session: str) -> str:
    ps = [e for e in read_jsonl(data_dir() / EPISODES) if e.get("session") == session and e.get("kind") == "prompt"]
    return ps[-2]["text"] if len(ps) >= 2 else ""


def apply(lesson_ids: list[str], label: str, why: str, session: str | None) -> None:
    rows = lessons.load()
    share = 1.0 / max(1, len(lesson_ids))  # 다중 주입이면 공로/책임을 나눈다
    for l in rows:
        if l["id"] in lesson_ids:
            oc = l.setdefault("outcomes", {"worked": 0.0, "partial": 0.0, "unknown": 0.0, "failed": 0.0})
            oc[label] = round(oc.get(label, 0.0) + share, 3)
            l.setdefault("outcome_log", []).append({"t": now_iso(), "label": label, "why": why[:80], "session": session})
            l["outcome_log"] = l["outcome_log"][-20:]
    lessons.save(rows)


def score_bonus(l: dict) -> float:
    oc = l.get("outcomes") or {}
    return sum(DELTA[k] * oc.get(k, 0.0) for k in DELTA)


def pending_for_labeling(session: str) -> list[dict]:
    """리플렉터에게 넘길 '아직 채점 안 된 주입' 과 그 뒤의 사용자 턴들."""
    eps = read_jsonl(data_dir() / EPISODES)
    prompts = [e for e in eps if e.get("session") == session and e.get("kind") == "prompt"]
    scored = {(e.get("prompt_index"), tuple(e.get("lesson_ids", []))) for e in eps
              if e.get("session") == session and e.get("kind") == "inject_scored"}
    out = []
    for e in eps:
        if e.get("session") != session or e.get("kind") != "inject":
            continue
        if (e.get("prompt_index"), tuple(e.get("lesson_ids", []))) in scored:
            continue
        idx = e.get("prompt_index", 0)
        following = [p_["text"][:300] for p_ in prompts[idx: idx + WINDOW]]
        out.append({"lesson_ids": e.get("lesson_ids", []), "trigger": e.get("trigger"), "prompt_index": idx, "following_user_turns": following})
    return out


def apply_llm_labels(session: str, labels: list[dict]) -> int:
    """리플렉터가 돌려준 [{id, label, why}] 를 반영한다. label ∉ {worked,partial,unknown,failed} 는 무시.
    왜 LLM 에 맡기나: 교정/재요청/만족은 문맥 판단이다. 정규식은 오탐이 많았다(제거됨).
    왜 기본값이 unknown 인가: 심판이 확신 없을 때 점수를 거의 건드리지 않게(−0.05)."""
    n = 0
    for lab in labels:
        if lab.get("label") in DELTA and lab.get("id"):
            apply([lab["id"]], lab["label"], "reflector: " + str(lab.get("why", ""))[:60], session)
            n += 1
    for e in pending_for_labeling(session):
        _mark_scored({"session": session, "prompt_index": e["prompt_index"], "lesson_ids": e["lesson_ids"]})
    return n


def on_test_result(session: str, command: str, passed: bool, error: str = "") -> list[str]:
    inj = recent_injections(session)
    if not inj:
        return []
    notes = []
    for e in inj:
        ids = e.get("lesson_ids", [])
        if passed:
            apply(ids, "worked", f"test passed: {command[:40]}", session); notes.append(f"worked(test):{ids}")
            _mark_scored(e)
        else:
            # 테스트 실패를 교훈 탓으로 돌리는 건 키워드로 판단할 수 없다 → 리플렉터에 맡긴다(여기선 기록만)
            notes.append(f"test-failed(left for reflector):{ids}")
    return notes


def _mark_scored(entry: dict) -> None:
    """같은 주입을 두 번 채점하지 않도록 표시. episodes 는 append-only 이므로 '채점됨' 이벤트를 덧붙인다."""
    append_jsonl(data_dir() / EPISODES, {"t": now_iso(), "kind": "inject_scored", "session": entry.get("session"),
                                          "prompt_index": entry.get("prompt_index"), "lesson_ids": entry.get("lesson_ids")})
