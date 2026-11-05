#!/usr/bin/env python3
"""주간 유지보수 리포트 (weekly).

왜 필요한가: 메모리 시스템은 방치하면 두 가지로 썩는다 — (1) 비대화: 안 쓰는 교훈이 컨텍스트를 먹음,
(2) 부패: 틀린/오래된 교훈이 그대로 남음(Claude Code 이슈 #85075 가 정확히 이 문제).
주 1회 15초짜리 리포트로 '지난주 무슨 일이 있었나, 무엇을 버리고 무엇을 강제할까'를 한눈에 보게 한다.

LLM 호출 없음. 보관(archive) 은 제안만 하고, 실제 적용은 `--apply` 를 줄 때만 한다.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta

from common import CANDIDATES, SESSIONS, EPISODES, data_dir, read_jsonl, today
import lessons
import enforce
import curate
import knowledge
import json

ARCHIVE_BELOW = 0.3  # 왜 0.3: 반감기 60일 기준, 증거 1개짜리 교훈이 ~100일 동안 한 번도 안 쓰였을 때의 점수


def _since(days: int) -> str:
    return (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")


def report(apply: bool = False) -> str:
    now = time.time()
    cutoff = _since(7)
    runs = read_jsonl(data_dir() / SESSIONS)
    eps = read_jsonl(data_dir() / EPISODES)
    rows = lessons.load()
    week_runs = [r for r in runs if str(r.get("t", "")) >= cutoff]
    week_eps = [e for e in eps if str(e.get("t", "")) >= cutoff]
    week_prompts = [e for e in week_eps if e.get("kind") == "prompt"]
    week_fail = [e for e in week_eps if e.get("kind") == "tool_failure"]
    active = [l for l in rows if l.get("status", "active") == "active"]
    new_lessons = [l for l in active if l.get("created", "") >= cutoff]
    stale = [l for l in active if lessons.score(l, now) < ARCHIVE_BELOW and not l.get("pinned") and not l.get("enforced")]
    enf_c = enforce.candidates()[:5]
    cand_path = data_dir() / CANDIDATES
    pending = []
    if cand_path.exists():
        try:
            pending = [c for c in json.loads(cand_path.read_text(encoding="utf-8")) if c.get("status") == "pending"]
        except Exception:
            pass

    out = [f"# self-tuner 주간 리포트 ({today()})", ""]
    out.append("## 지난 7일")
    out.append(f"- 세션 프롬프트 {len(week_prompts)}개, 도구 실패 {len(week_fail)}건")
    oc = {"worked": 0.0, "partial": 0.0, "unknown": 0.0, "failed": 0.0}
    for l in active:
        for k_, v_ in (l.get("outcomes") or {}).items():
            oc[k_] = oc.get(k_, 0.0) + v_
    out.append(f"- 교훈 효과 판정(리플렉터, 누적): worked {oc['worked']:.1f} / partial {oc['partial']:.1f} / unknown {oc['unknown']:.1f} / failed {oc['failed']:.1f}")
    out.append(f"- 리플렉션 {len(week_runs)}회 → 교훈 추가 {sum(r.get('added',0) for r in week_runs)} / 병합 {sum(r.get('merged',0) for r in week_runs)}, 오류 {sum(1 for r in week_runs if r.get('error'))}회, 비용 ${sum(r.get('cost_usd',0.0) for r in week_runs):.3f}")
    tp = sum(r.get("hint_tp", 0) for r in runs); fp = sum(r.get("hint_fp", 0) for r in runs); fn = sum(r.get("hint_fn", 0) for r in runs)
    if tp + fp + fn:
        prec = tp / max(1, tp + fp); rec = tp / max(1, tp + fn)
        out.append(f"- 교정 힌트(정규식, 게이트용) 자가 측정: 정밀도 {prec:.2f} / 재현율 {rec:.2f} (n={tp+fp+fn}; 30건↑에서 정밀도<0.7 이면 게이트 자동 제외)")
    provisional = [l for l in active if not lessons.is_confirmed(l) and not l.get("enforced")]
    out.append(f"- 잠정 교훈(한 세션에서만 관찰, rules 미반영) {len(provisional)}개 — 다른 세션에서 다시 나오면 자동 확정")
    if new_lessons:
        out.append("- 이번 주 새 교훈:")
        out += [f"  - {l['text']} [{l['id']}] ({l['scope']})" for l in new_lessons[:10]]
    out.append("")
    out.append(f"## 저장소 상태: 활성 {len(active)} / 보관 {sum(1 for l in rows if l.get('status')=='archived')} / 강제(hook) {len(enforce.enforced())} / 스킬 후보 대기 {len(pending)}")
    out.append("")
    out.append(f"## 보관 제안 (점수 < {ARCHIVE_BELOW}, 오래 안 쓰임) — {len(stale)}개")
    for l in stale[:15]:
        out.append(f"- {l['text']} [{l['id']}] 점수 {lessons.score(l, now):.2f}, 마지막 {l.get('last_seen','')[:10]}")
    if apply and stale:
        for l in stale:
            lessons.set_status(l["id"], "archived")
        out.append(f"→ {len(stale)}개 보관 처리함 (`lessons pin <id>` 로 되살릴 수 있음)")
    out.append("")
    out.append(f"## 훅 강제 후보 (증거 ≥ {enforce.MIN_EVIDENCE}, 반대표 0) — {len(enf_c)}개")
    for l in enf_c:
        ev, entry = enforce.build_hook(l)
        out.append(f"- {l['text']} [{l['id']}] → {ev}" + (f" ({entry['matcher']})" if entry.get("matcher") else "") + f"  · `/self-tuner:enforce apply {l['id']}`")
    out.append("")
    st = knowledge.stale()
    out.append(f"## 지식 노트: 총 {len(knowledge.notes())}개, 재검증 필요(90일 경과) {len(st)}개")
    for n in st[:10]:
        out.append(f"- {n['title']} (검증기한 {n.get('verify_by')}) · `/self-tuner:research --refresh \"{n['title']}\"`")
    out.append("")
    out.append("## 이번 주 할 일 (권장)")
    out.append("- `/skill-doctor` — 한 번도 안 호출된 스킬 제거")
    out.append("- `/doctor prompt-audit` — rules/CLAUDE.md 모순 점검 (self-tuner.md 포함)")
    if pending:
        out.append(f"- `/self-tuner:promote list` — 대기 후보 {len(pending)}개 검토")
    curate.write_rules()
    return "\n".join(out)
