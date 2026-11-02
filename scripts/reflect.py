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
from common import EPISODES, SESSIONS, append_jsonl, data_dir, now_iso, read_jsonl, today  # noqa: E402
import curate  # noqa: E402
import lessons  # noqa: E402

PROMPT = """당신은 코딩 에이전트 하네스의 '리플렉터'입니다. 아래는 한 Claude Code 세션의 다이제스트입니다.
사용자가 다음 세션에서도 유용하게 쓸 '교훈'을 추출하세요.

규칙:
- 교훈이 없으면 빈 배열 [] 을 내세요. 억지로 만들지 마세요. 대부분의 세션은 교훈이 0~2개입니다.
- 코드베이스에서 읽어낼 수 있는 사실(파일 경로, 아키텍처)은 교훈이 아닙니다. 사용자의 선호, 교정, 반복되는 작업 방식, 도구 함정만 해당합니다.
- 이미 '기존 교훈' 목록에 있는 내용은 다시 내지 마세요.
- 사용자가 '매번', '항상', '또', '내가 말했잖아' 처럼 반복을 언급한 교정은 가장 우선해서 교훈으로 만드세요(scope=global).
- 각 교훈은 한국어 한 문장(최대 120자), 명령형으로. 예: "검색 관련 코드는 BM25와 벡터 하이브리드를 기본 제안한다"
- category 는 preference | workflow | pitfall | tool | domain | project 중 하나.
- scope 는 모든 프로젝트에 해당하면 "global", 이 프로젝트에만 해당하면 "project".
- rationale 에는 다이제스트의 어느 부분이 근거인지 10~40자로.
- 출력은 JSON 배열만. 다른 텍스트 금지.

출력 형식:
[{"text": "...", "category": "...", "scope": "global|project", "rationale": "..."}]

프로젝트: {project}

기존 교훈(중복 금지):
{existing}

세션 다이제스트:
{digest}
"""


def build_digest(session_id: str, transcript_path: str | None, max_chars: int = 9000) -> tuple[str, dict]:
    eps = [e for e in read_jsonl(data_dir() / EPISODES) if e.get("session") == session_id]
    prompts = [e for e in eps if e.get("kind") == "prompt"]
    corrections = [e for e in prompts if e.get("correction")]
    failures = [e for e in eps if e.get("kind") == "tool_failure"]

    lines = []
    lines.append(f"- 사용자 프롬프트 {len(prompts)}개, 교정으로 보이는 프롬프트 {len(corrections)}개, 도구 실패 {len(failures)}건")
    lines.append("\n[사용자 프롬프트 — 시간순]")
    for e in prompts[:40]:
        flag = " (교정?)" if e.get("correction") else ""
        lines.append(f"- {e['text'][:300].replace(chr(10), ' ')}{flag}")
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
    stats = {"prompts": len(prompts), "corrections": len(corrections), "failures": len(failures)}
    return digest, stats


def call_claude(prompt: str, model: str, timeout: int = 180) -> str:
    env = dict(os.environ)
    env["SELF_TUNER_CHILD"] = "1"                 # 훅 재귀 방지
    env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = "1"  # 리플렉터가 메모리를 오염시키지 않게
    # 왜 --bare 를 안 쓰나: --bare 는 OAuth(Max 플랜) 인증을 읽지 않아 API 키 없는 사용자는 실패한다.
    # 대신 env 가드 + 도구 비허용(--allowedTools 공백)으로 '텍스트만 내는 한 번의 호출'로 만든다.
    cmd = ["claude", "-p", "--model", model, "--output-format", "text",
           "--permission-mode", "dontAsk", "--disallowedTools", "Bash,Edit,Write,WebFetch,WebSearch,Agent,Skill",
           "--no-session-persistence", prompt]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env, cwd=str(Path.home()))
    if r.returncode != 0:
        raise RuntimeError(f"claude -p failed ({r.returncode}): {r.stderr[:400]}")
    return r.stdout


def parse_deltas(text: str) -> list[dict]:
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        return []
    try:
        arr = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    out = []
    for d in arr if isinstance(arr, list) else []:
        if isinstance(d, dict) and isinstance(d.get("text"), str):
            out.append(d)
    return out[:6]  # 왜 6개 상한: 한 세션에서 6개 넘게 '교훈'이 나오면 대부분 노이즈다


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", required=True)
    ap.add_argument("--project", default="global")
    ap.add_argument("--transcript", default=None)
    ap.add_argument("--model", default=os.environ.get("SELF_TUNER_MODEL", "haiku"))
    ap.add_argument("--dry-run", action="store_true", help="LLM 호출 없이 다이제스트만 출력")
    args = ap.parse_args()

    digest, stats = build_digest(args.session, args.transcript)
    if args.dry_run:
        print(digest)
        return 0

    existing = lessons.top(scope_filter={"global", f"project:{args.project}"}, k=40)
    existing_txt = "\n".join(f"- {l['text']}" for l in existing) or "(없음)"
    prompt = PROMPT.replace("{project}", args.project).replace("{existing}", existing_txt).replace("{digest}", digest)

    result = {"t": now_iso(), "session": args.session, "project": args.project, **stats, "added": 0, "merged": 0, "error": None}
    try:
        raw = call_claude(prompt, args.model)
        deltas = parse_deltas(raw)
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
