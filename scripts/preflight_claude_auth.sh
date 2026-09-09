#!/usr/bin/env bash
# preflight_claude_auth.sh — Claude CLI 인증/HOME preflight (D1, 완전 portable)
#
# 목적:
#   어느 HOME에 '유효한 Claude 자격증명'이 있는지 기계적으로 탐지한다.
#   Hermes가 profile별 HOME을 격리하면 $HOME/.claude 에 자격증명이 없을 수 있으므로,
#   본작업(claude -p) 전에 'primary(진짜 서브에이전트 제어)가 가능한 HOME'을 먼저 확정한다.
#
# 비과적합 원칙:
#   - 특정 머신 경로(/home/...)를 하드코딩하지 않는다.
#   - 후보 HOME 목록은 인자 또는 환경변수로 주입한다(배포 환경마다 다름).
#
# 입력(우선순위):
#   1) 명령행 인자: 후보 HOME 경로들. 예) preflight_claude_auth.sh "$HOME" /alt/home
#   2) 환경변수 CLAUDE_HOME_CANDIDATES: 콜론(:) 구분 후보 목록.
#   3) 둘 다 없으면 현재 $HOME 하나만 검사.
#
# 출력:
#   성공: 표준출력에 'PRIMARY_READY_HOME=<경로>' 1줄, exit 0
#   실패: 후보별 결과를 출력하고 분류코드와 함께 비정상 종료
#     exit 3  = CLAUDE_AUTH_HOME_MISMATCH (모든 후보에서 Not logged in)
#     exit 4  = CLAUDE_CLI_NOT_FOUND     (claude 실행파일 없음)
#
# 검증 통과 기준: 'env HOME=<후보> claude auth status' 가 exit 0 이고 'Not logged in' 미포함.

set -uo pipefail

TIMEOUT_BIN="$(command -v timeout || true)"
AUTH_TIMEOUT="${CLAUDE_AUTH_TIMEOUT:-20}"

if ! command -v claude >/dev/null 2>&1; then
  echo "CLAUDE_CLI_NOT_FOUND: 'claude' 실행파일을 PATH에서 찾지 못함" >&2
  echo "PATH=$PATH" >&2
  exit 4
fi

# 후보 HOME 목록 구성
candidates=()
if [ "$#" -gt 0 ]; then
  candidates=("$@")
elif [ -n "${CLAUDE_HOME_CANDIDATES:-}" ]; then
  IFS=':' read -r -a candidates <<< "${CLAUDE_HOME_CANDIDATES}"
else
  candidates=("${HOME:-}")
fi

run_auth() {
  # $1 = HOME 후보. auth status 실행(타임아웃 보호).
  local h="$1"
  if [ -n "$TIMEOUT_BIN" ]; then
    env HOME="$h" "$TIMEOUT_BIN" "$AUTH_TIMEOUT" claude auth status --text 2>&1
  else
    env HOME="$h" claude auth status --text 2>&1
  fi
}

ready=""
for h in "${candidates[@]}"; do
  [ -z "$h" ] && continue
  out="$(run_auth "$h")"
  rc=$?
  if [ "$rc" -eq 0 ] && ! printf '%s' "$out" | grep -qi 'Not logged in'; then
    echo "[OK] HOME=$h → 인증됨"
    ready="$h"
    break
  else
    # 자격증명 파일 존재 여부도 진단에 포함(하드코딩 아님: 후보 기준 상대)
    cred="$h/.claude/.credentials.json"
    have_cred="no"; [ -f "$cred" ] && have_cred="yes"
    echo "[NG] HOME=$h → rc=$rc, credentials.json=$have_cred"
  fi
done

if [ -n "$ready" ]; then
  echo "PRIMARY_READY_HOME=$ready"
  exit 0
fi

echo "CLAUDE_AUTH_HOME_MISMATCH: 모든 후보 HOME에서 유효 인증을 찾지 못함" >&2
echo "후보=${candidates[*]}" >&2
exit 3
