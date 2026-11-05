#!/usr/bin/env python3
"""self-tuner 공용 유틸.

왜 별도 모듈인가: 훅 스크립트 6개가 모두 같은 데이터 디렉터리, 같은 JSONL 입출력,
같은 '재진입 방지' 규칙을 써야 한다. 한 곳에 두지 않으면 훅마다 미묘하게 달라져
데이터가 깨진다(ACE 논문이 말하는 'context collapse'의 파일시스템 버전).
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# 경로
# ---------------------------------------------------------------------------
# 왜 CLAUDE_PLUGIN_DATA 우선인가: 플러그인 업데이트 시 CLAUDE_PLUGIN_ROOT는 바뀌지만
# CLAUDE_PLUGIN_DATA(~/.claude/plugins/data/<id>/)는 유지된다. 학습 데이터는 여기 둔다.
# 훅이 아닌 곳(스킬에서 Bash로 실행)에서는 env가 없으므로 같은 규칙으로 직접 계산한다.
def data_dir() -> Path:
    d = os.environ.get("CLAUDE_PLUGIN_DATA") or os.environ.get("SELF_TUNER_DATA")
    if not d:
        d = str(Path.home() / ".claude" / "plugins" / "data" / "self-tuner")
    p = Path(d).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    return p


def claude_home() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude")).expanduser()


LESSONS = "lessons.jsonl"       # 교훈 저장소(append-only + 상태 갱신)
EPISODES = "episodes.jsonl"     # 세션 중 포착한 원시 신호(프롬프트, 교정, 실패)
SESSIONS = "sessions.jsonl"     # 세션별 요약 통계
CANDIDATES = "skill_candidates.json"  # 반복 패턴 → 스킬 후보
RULES_FILE = "self-tuner.md"    # ~/.claude/rules/ 에 쓰는 전역 교훈 파일


# ---------------------------------------------------------------------------
# 재진입 방지
# ---------------------------------------------------------------------------
# 왜 필요한가: Stop 훅에서 `claude -p`(리플렉터)를 띄우면 그 자식 세션에도 같은
# 플러그인 훅이 걸린다 → 무한 재귀. 자식에게 SELF_TUNER_CHILD=1 을 넘기고
# 모든 훅은 이 값이 있으면 즉시 종료한다.
def is_child_session() -> bool:
    return os.environ.get("SELF_TUNER_CHILD") == "1"


def bail_if_child() -> None:
    if is_child_session():
        sys.exit(0)


# ---------------------------------------------------------------------------
# JSONL
# ---------------------------------------------------------------------------
def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # 왜 무시하나: 훅 동시 실행으로 깨진 한 줄이 전체를 망치면 안 된다
    return out


def append_jsonl(path: Path, obj: dict) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    tmp.replace(path)  # 왜 원자적 교체인가: 쓰는 도중 다른 훅이 읽어도 반쪽 파일을 보지 않게


def read_hook_input() -> dict:
    try:
        return json.load(sys.stdin)
    except Exception:
        return {}


def emit(obj: dict) -> None:
    # 훅 JSON 출력은 stdout 한 덩어리여야 한다
    sys.stdout.write(json.dumps(obj, ensure_ascii=False))
    sys.stdout.flush()


# ---------------------------------------------------------------------------
# 프로젝트 식별
# ---------------------------------------------------------------------------
def project_key(cwd: str | None) -> str:
    """Claude Code의 auto-memory와 같은 단위(=git 루트)로 프로젝트를 식별한다.

    왜 git 루트인가: 같은 저장소의 worktree/하위 폴더에서 배운 교훈은 하나로 모여야 한다.
    """
    if not cwd:
        return "global"
    p = Path(cwd)
    for parent in [p, *p.parents]:
        if (parent / ".git").exists():
            return parent.name
    return p.name or "global"


# ---------------------------------------------------------------------------
# 고정밀 교정 힌트 (게이트·샘플링 전용 — 판정에는 쓰지 않음)
# ---------------------------------------------------------------------------
# 경위: 1차 버전은 "말고/다시/왜 이렇게" 같은 넓은 패턴을 쓰고 그 결과로 교훈 점수까지 깎았다 → "이거 말고도" 오탐.
#       2차에서 통째로 제거했다 → 리플렉터가 교훈 없는 세션에도 돌고, mine 이 교정 샘플을 못 보여줬다(과잉 교정).
# 근거: 좌절 탐지 연구(arXiv 2411.17437)에서 키워드 방식은 정밀도 100%·재현율 1%. 즉 '잡은 건 맞지만 대부분 놓친다'.
#       그런 신호의 올바른 용도는 **비용 게이트와 샘플링**이지 판정이 아니다.
# 규칙: 아래 함수는 (1) on_stop 의 리플렉터 실행 우선순위, (2) mine_history 의 샘플 선별에만 쓴다.
#       교훈 점수·효과 라벨·주입 여부 결정에 쓰면 안 된다(그건 리플렉터 LLM 의 일).
_STRICT_CORRECTION = [
    r"^(아니|아냐|아니야)[,.\s]",          # 문두의 부정만. "아니면" 은 제외(아래 negative 참조)
    r"그게 아니(라|야|고|지)|그거 말고\b(?!도)",       # "말고도"(=besides) 제외
    r"틀렸|잘못 (했|됐|짰)",
    r"하지 ?마(?!요\?)",                   # 요청형 "하지 마요?" 는 제외
    r"내가 (말한|말했|시킨|요청한|부탁한) ?(거|건|것|대로)",
    r"\b(that'?s wrong|not what i asked|don'?t do that|i said)\b",
]
_STRICT_NEG = re.compile(r"^(아니면|아니라도|아닐까|아니지만)")
_STRICT = [re.compile(p, re.IGNORECASE) for p in _STRICT_CORRECTION]


def correction_hint(text: str) -> bool:
    """고정밀·저재현 교정 힌트. True 는 '교정일 가능성이 높다' 지 '교정이다' 가 아니다. 게이트/샘플링 전용."""
    head = text.strip()[:160]
    if _STRICT_NEG.match(head):
        return False
    return any(r.search(head) for r in _STRICT)


# ---------------------------------------------------------------------------
# 간단 토크나이저 / 키워드 (교훈 검색용)
# ---------------------------------------------------------------------------
_STOP = set("""
the a an and or of to in on for with is are be this that it as at by from
그리고 그래서 그런데 하지만 이거 그거 저거 이것 그것 좀 약간 그냥 진짜 정말 너무 같은 같이 거든 거야 건데
해줘 해주세요 해봐 해봐요 할까 할래 하자 하고 하는 해서 한다 했어 했는데 있어 있는 없어 없는 되게 되는 돼
내가 네가 우리 나는 너는 그게 이게 저게 뭐 어떤 어떻게 왜 언제 어디 누가 좀더 더 덜 많이 조금 바로 지금
싸은데 싶은데 싶어 싶다 하나 해야 하긴 그러면 그럼 아예 하겟다 하겠다 해줘야 되는건데 된다라 일단 이거는 이것들 그런 이런 저런 여기 거기
진행 진행해 진행해줘 확인 확인해 확인해봐 해봐 해볼 해보고 봐줘 알려줘 말해 보여줘 같은데 같아 되게 때문에 그래서 근데 그리고 또
https http github.com www com
""".split())


def keywords(text: str, limit: int = 12) -> list[str]:
    """한국어/영어 혼용 텍스트에서 거친 키워드를 뽑는다.

    용도는 두 가지로 **제한**한다: (1) mine_history 의 빈도 통계, (2) 같은 교훈이 두 번 저장되는 것을 막는 병합 휴리스틱.
    교훈 주입이나 효과 판정 같은 '의미 판단' 에는 쓰지 않는다 — 문맥을 모르는 토큰 겹침은 오탐이 많다.
    형태소 분석기를 안 쓰는 이유: 훅은 추가 설치 없이 어떤 머신에서도 돌아야 한다.
    """
    toks = re.findall(r"[A-Za-z][A-Za-z0-9_\-\.]{1,}|[가-힣]{2,}", text)
    out: list[str] = []
    for t in toks:
        t = t.lower()
        # 흔한 조사 제거 (은/는/이/가/을/를/에서/으로/로/의/도/만/께/에게)
        t = re.sub(r"(에서|으로|에게|까지|부터|처럼|보다|이랑|하고|은|는|이|가|을|를|로|의|도|만|에)$", "", t) if re.match(r"[가-힣]", t) else t
        if re.match(r"[가-힣]", t):
            # 구어 어미 제거(간이) — 왜: "진행하고/진행해서/진행하면" 이 전부 다른 키워드로 세어지면 빈도가 흩어진다
            t = re.sub(r"(해보고|해보면|해봐|하는데|되는데|하면서|해서|하고|하면|되면|했는데|한데|인데)$", "", t)
        if len(t) < 2 or t in _STOP:
            continue
        if t not in out:
            out.append(t)
        if len(out) >= limit:
            break
    return out


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


def today() -> str:
    return time.strftime("%Y-%m-%d", time.localtime())


# ---------------------------------------------------------------------------
# 자기 기록 파일 위생
# ---------------------------------------------------------------------------
_INVISIBLE = re.compile(r"[\u200b-\u200f\u2028-\u202e\u2060-\u206f\ufeff]")
_TAGISH = re.compile(r"</?\s*(system-reminder|system|assistant|user|tool_result|function_calls|invoke|antml[^>]*)\s*>", re.I)


def sanitize(text: str, limit: int = 400) -> str:
    """교훈/노트에 쓰기 전 정리. 왜: 리플렉터(LLM) 가 쓴 텍스트가 다음 세션의 컨텍스트에 들어간다.
    보이지 않는 문자나 시스템 태그 흉내가 섞이면 프롬프트 인젝션 통로가 된다
    (Claude Code v2.1.284 가 MEMORY.md 에 같은 중화를 적용; EvoMal·SkillMisevo 논문의 경고)."""
    t = _INVISIBLE.sub("", text)
    t = _TAGISH.sub(lambda m: m.group(0).replace("<", "<\\"), t)
    t = re.sub(r"[ \t]+", " ", t).strip()
    return t[:limit]
