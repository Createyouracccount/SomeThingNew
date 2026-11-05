#!/usr/bin/env python3
"""리플렉터 + 큐레이터 (ACE 의 Reflector/Curator 역할). 세션이 끝난 뒤 '비판적 경로 밖에서' 돈다.

흐름:
  1) 이 세션의 episodes(프롬프트/교정/도구 실패) + transcript 의 마지막 assistant 메시지들을 압축한 다이제스트 생성
  2) `claude -p --model haiku` 로 한 번 호출 → JSON 델타 목록 {op: add, text, category, scope, rationale}
  3) lessons.upsert 로 저장소에 합치고(쓰기 시 조정), curate.write_rules 로 rules 뷰 갱신

왜 LLM 호출이 세션당 1회인가: 비용. 왜 haiku 인가: 교훈 추출은 요약 과제라 작은 모델로 충분하고,
Claude Code 자체도 background 작업에 작은 모델을 쓴다.
왜 '중립적 프롬프트'인가: Phantom Guardrails(2026) — "문제를 찾아라"고 하면 없는 문제를 지어낸다.
  그래서 "교훈이 없으면 빈 배열을 내라"를 명시한다.
왜 자식 세션에 SELF_TUNER_CHILD=1 과 CLAUDE_CODE_DISABLE_AUTO_MEMORY=1 을 주나: 훅 재귀 방지,
  그리고 리플렉터가 auto-memory 를 오염시키지 않게.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import EPISODES, SESSIONS, append_jsonl, correction_hint, data_dir, now_iso, read_jsonl, today  # noqa: E402
import curate  # noqa: E402
import lessons  # noqa: E402
import outcomes  # noqa: E402

PROMPT = """당신은 코딩 에이전트 하네스의 '리플렉터'입니다. 아래는 한 Claude Code 세션의 다이제스트입니다.
사용자가 다음 세션에서도 유용하게 쓸 '교훈'을 추출하세요.

규칙:
- 교훈이 없으면 빈 배열 [] 을 내세요. 억지로 만들지 마세요. 대부분의 세션은 교훈이 0~2개입니다.
- 코드베이스에서 읽어낼 수 있는 사실(파일 경로, 아키텍처)은 교훈이 아닙니다. 사용자의 선호, 교정, 반복되는 작업 방식, 도구 함정만 해당합니다.
- 이미 '기존 교훈' 목록에 있는 내용은 다시 내지 마세요.
- 사용자가 '매번', '항상', '또', '내가 말했잖아' 처럼 반복을 언급한 교정은 가장 우선해서 교훈으로 만드세요(scope=global).
- 각 교훈은 한국어 한 문장(최대 120자), 명령형으로. 예: "검색 관련 코드는 BM25와 벡터 하이브리드를 기본 제안한다"
- pitfall 은 "X 하지 말고 Y" 형태의 짧은 금지 규칙으로. (예시 많은 긴 설명보다 안티패턴 한 줄이 더 잘 지켜진다는 2026 벤치마크 결과)
- 근거(rationale)는 다이제스트의 **구체적 사건**(어떤 프롬프트/어떤 실패)을 가리켜야 한다. 일반론("코드 품질을 높여야 한다")은 교훈이 아니다.
- category 는 preference | workflow | pitfall | tool | domain | project 중 하나.
- scope 는 모든 프로젝트에 해당하면 "global", 이 프로젝트에만 해당하면 "project".
- rationale 에는 다이제스트의 어느 부분이 근거인지 10~40자로.
- 출력은 JSON 배열만. 다른 텍스트 금지.

두 번째 과제 — 효과 판정: 아래 '주입된 교훈' 각각에 대해, 그 직후 사용자 턴들을 읽고 라벨을 하나 주세요.
- worked: 사용자가 만족하거나 다른 주제로 넘어갔다 / partial: 일부만 반영됨 / failed: 사용자가 그 교훈과 관련된 내용을 교정했거나 같은 요청을 되풀이했다 / unknown: 판단 근거 없음(기본값).
- 사용자 턴이 교훈 주제와 무관하면 unknown. 감정 표현만으로 판단하지 마세요.

세 번째 과제 — 교정 턴 식별: 다이제스트의 사용자 프롬프트 중 '이전 응답을 바로잡는 교정' 인 것의 번호(1부터)를 모두 적으세요. 없으면 [].

출력 형식(JSON 객체 하나, 다른 텍스트 금지):
{"lessons": [{"text": "...", "category": "...", "scope": "global|project", "rationale": "..."}],
 "outcomes": [{"id": "Lxxxxxxxx", "label": "worked|partial|unknown|failed", "why": "10~30자"}],
 "correction_turns": [2, 5]}

프로젝트: {project}

기존 교훈(중복 금지):
{existing}

세션 다이제스트:
{digest}

주입된 교훈(효과 판정 대상; 없으면 outcomes 는 []):
{injected}
"""


def build_digest(session_id: str, transcript_path: str | None, max_chars: int = 9000) -> tuple[str, dict]:
    eps = [e for e in read_jsonl(data_dir() / EPISODES) if e.get("session") == session_id]
    prompts = [e for e in eps if e.get("kind") == "prompt"]
    failures = [e for e in eps if e.get("kind") == "tool_failure"]

    lines = []
    lines.append(f"- 사용자 프롬프트 {len(prompts)}개, 도구 실패 {len(failures)}건")
    lines.append("\n[사용자 프롬프트 — 시간순, 번호 포함] (교정인지, 만족했는지는 당신이 문맥으로 판단하세요)")
    for i, e in enumerate(prompts[:40], 1):
        lines.append(f"{i}. {e['text'][:300].replace(chr(10), ' ')}")
    if failures:
        lines.append("\n[도구 실패]")
        for e in failures[:15]:
            lines.append(f"- {e['tool']}: {e['input'][:120]} → {e['error'][:120]}")

    # transcript 에서 사용자가 교정한 직후의 assistant 응답 머리만 조금 가져온다(무엇을 고쳤는지 보기 위해)
    if transcript_path and Path(transcript_path).exists():
        tail = []
        try:
            with open(transcript_path, encoding="utf-8") as f:
                for line in f:
                    if '"assistant"' not in line:
                        continue
                    try:
                        o = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if o.get("type") != "assistant" or o.get("isSidechain"):
                        continue
                    for b in o.get("message", {}).get("content", []):
                        if b.get("type") == "text" and len(b.get("text", "")) > 40:
                            tail.append(b["text"][:240].replace("\n", " "))
        except OSError:
            pass
        if tail:
            lines.append("\n[어시스턴트 응답 발췌 — 마지막 6개]")
            lines += [f"- {t}" for t in tail[-6:]]

    digest = "\n".join(lines)
    if len(digest) > max_chars:
        digest = digest[:max_chars] + "\n...(생략)"
    stats = {"prompts": len(prompts), "failures": len(failures)}
    return digest, stats


def call_claude(prompt: str, model: str, timeout: int = 180) -> str:
    env = dict(os.environ)
    env["SELF_TUNER_CHILD"] = "1"                 # 훅 재귀 방지
    env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = "1"  # 리플렉터가 메모리를 오염시키지 않게
    # 왜 --bare 를 안 쓰나: --bare 는 OAuth(Max 플랜) 인증을 읽지 않아 API 키 없는 사용자는 실패한다.
    # 대신 env 가드 + 도구 비허용(--allowedTools 공백)으로 '텍스트만 내는 한 번의 호출'로 만든다.
    cmd = ["claude", "-p", "--model", model, "--output-format", "json",
           "--permission-mode", "dontAsk", "--disallowedTools", "Bash,Edit,Write,WebFetch,WebSearch,Agent,Skill",
           "--no-session-persistence", prompt]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env, cwd=str(Path.home()))
    if r.returncode != 0:
        raise RuntimeError(f"claude -p failed ({r.returncode}): {r.stderr[:400]}")
    # JSON 출력에서 결과 텍스트와 비용을 분리한다. 왜 비용을 기록하나: 백그라운드 요약기가 예산 없이 돌다
    # 649M 토큰(~$580) 을 쓴 사고(claude-mem #2643). 보이지 않는 비용은 반드시 보이게 만든다.
    try:
        o = json.loads(r.stdout)
        call_claude.last_cost = float(o.get("total_cost_usd") or 0.0)
        return o.get("result", "") if isinstance(o, dict) else r.stdout
    except json.JSONDecodeError:
        call_claude.last_cost = 0.0
        return r.stdout


def parse_output(text: str) -> tuple[list[dict], list[dict]]:
    """{"lessons":[...], "outcomes":[...]} 또는 (구버전) [...] 를 받아 (교훈, 라벨) 을 돌려준다."""
    m = re.search(r"\{.*\}|\[.*\]", text, re.S)
    if not m:
        return [], []
    try:
        o = json.loads(m.group(0))
    except json.JSONDecodeError:
        return [], []
    if isinstance(o, list):
        o = {"lessons": o, "outcomes": []}
    les = [d for d in o.get("lessons", []) if isinstance(d, dict) and isinstance(d.get("text"), str)][:6]  # 6개 넘으면 노이즈
    outs = [d for d in o.get("outcomes", []) if isinstance(d, dict)]
    parse_output.correction_turns = [int(x) for x in o.get("correction_turns", []) if str(x).isdigit()]
    return les, outs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", required=True)
    ap.add_argument("--project", default="global")
    ap.add_argument("--transcript", default=None)
    ap.add_argument("--model", default=os.environ.get("SELF_TUNER_MODEL", "haiku"))
    ap.add_argument("--dry-run", action="store_true", help="LLM 호출 없이 다이제스트만 출력")
    args = ap.parse_args()

    digest, stats = build_digest(args.session, args.transcript)
    session_prompts = [e for e in read_jsonl(data_dir() / EPISODES) if e.get("session") == args.session and e.get("kind") == "prompt"][:40]
    if args.dry_run:
        print(digest)
        return 0

    existing = lessons.top(scope_filter={"global", f"project:{args.project}"}, k=40)
    existing_txt = "\n".join(f"- {l['text']}" for l in existing) or "(없음)"
    pend = outcomes.pending_for_labeling(args.session)
    by_id = {l["id"]: l for l in lessons.load()}
    inj_lines = []
    for e in pend:
        for lid in e["lesson_ids"]:
            if lid in by_id:
                inj_lines.append(f"- {lid}: {by_id[lid]['text']} (주입 계기: {e['trigger']}) → 이후 사용자 턴: "
                                 + " | ".join(e["following_user_turns"]) if e["following_user_turns"] else f"- {lid}: {by_id[lid]['text']} → 이후 사용자 턴 없음")
    injected_txt = "\n".join(inj_lines) or "(없음)"
    prompt = (PROMPT.replace("{project}", args.project).replace("{existing}", existing_txt)
              .replace("{digest}", digest).replace("{injected}", injected_txt))

    result = {"t": now_iso(), "session": args.session, "project": args.project, **stats, "added": 0, "merged": 0, "cost_usd": 0.0, "error": None}
    try:
        raw = call_claude(prompt, args.model)
        result["cost_usd"] = round(getattr(call_claude, "last_cost", 0.0), 4)
        deltas, labels = parse_output(raw)
        result["labeled"] = outcomes.apply_llm_labels(args.session, labels) if pend else 0
        # 힌트 정밀도 자가 측정: 정규식 힌트(게이트용) vs 리플렉터가 문맥으로 판정한 교정 턴.
        # 왜: "키워드 힌트는 정밀하다" 는 주장을 문헌 한 편으로 단정하지 않고, 내 데이터로 계속 측정한다.
        # weekly 가 누적 정밀도를 보여주고, 30건 이상 쌓였는데 0.7 미만이면 게이트에서 힌트를 뺀다(on_stop 참조).
        llm_corr = set(getattr(parse_output, "correction_turns", []))
        hinted = {i for i, e in enumerate(session_prompts, 1) if correction_hint(e.get("text", ""))}
        result["hint_tp"] = len(hinted & llm_corr)
        result["hint_fp"] = len(hinted - llm_corr)
        result["hint_fn"] = len(llm_corr - hinted)
        for d in deltas:
            scope = "global" if d.get("scope") == "global" else f"project:{args.project}"
            _, how = lessons.upsert(d["text"], d.get("category", "workflow"), scope,
                                    source=args.session, rationale=d.get("rationale", ""))
            if how in ("added", "merged"):
                result[how] += 1
        curate.write_rules()
    except Exception as e:  # 왜 삼키나: 백그라운드 리플렉터의 실패가 사용자 세션에 영향을 주면 안 된다
        result["error"] = str(e)[:300]
    append_jsonl(data_dir() / SESSIONS, result)
    (data_dir() / "last_reflect.txt").write_text(today(), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
