#!/usr/bin/env bash
# self-tuner 설치: ~/.claude/skills/self-tuner 로 복사하면 다음 세션부터 self-tuner@skills-dir 로 자동 로드된다.
# 왜 심볼릭 링크가 아닌 복사인가: 플러그인 루트가 바뀌어도(=이 저장소를 옮겨도) 설치본이 깨지지 않게.
# 개발 중엔 `claude --plugin-dir "$(pwd)"` 로 복사 없이 로드해 테스트할 수 있다.
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
DST="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills/self-tuner"
command -v python3 >/dev/null || { echo "python3 가 필요합니다"; exit 1; }
command -v claude  >/dev/null || { echo "claude CLI 가 필요합니다"; exit 1; }
mkdir -p "$(dirname "$DST")"
rm -rf "$DST"
# 왜 evals/results 와 .git 을 빼나: 설치본에 실행 결과물·히스토리는 불필요
rsync -a --exclude '.git' --exclude 'evals/results' --exclude '__pycache__' "$SRC/" "$DST/" 2>/dev/null \
  || { cp -R "$SRC" "$DST"; rm -rf "$DST/.git" "$DST/evals/results"; }
chmod +x "$DST"/scripts/*.py
claude plugin validate "$DST" >/dev/null && echo "✓ 설치됨: $DST (다음 세션부터 self-tuner@skills-dir 로 로드)"
echo "  1) 새 세션에서 /self-tuner:mine  ← 과거 기록 마이닝(cold start)"
echo "  2) 평소처럼 쓰기 — Stop 훅이 세션당 1회(haiku) 교훈을 추출해 ~/.claude/rules/self-tuner.md 에 반영"
echo "  3) /self-tuner:lessons 로 👍/👎, /self-tuner:promote 로 스킬 후보 승격(평가 통과 시)"
