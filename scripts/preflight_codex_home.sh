#!/usr/bin/env bash
# preflight_codex_home.sh — Codex CLI 인증/CODEX_HOME preflight (D1, 완전 portable)
#
# 목적:
#   어느 CODEX_HOME 에 유효 인증(auth.json)이 있는지 탐지한다.
#   Hermes 가 profile HOME 을 격리하면 기본 ~/.codex 가 가려질 수 있으므로,
#   본작업(codex exec) 전에 'primary 가능한 CODEX_HOME'을 먼저 확정한다.
#
# 비과적합 원칙: 특정 머신 경로를 하드코딩하지 않는다. 후보는 인자/환경변수로 주입.
#
# 입력(우선순위):
#   1) 인자: 후보 CODEX_HOME 경로들.
#   2) 환경변수 CODEX_HOME_CANDIDATES: 콜론(:) 구분.
#   3) 둘 다 없으면 ${CODEX_HOME:-$HOME/.codex} 하나.
#
# 출력: 성공 시 'CODEX_HOME_READY=<경로>' + exit 0.
#   exit 3 = CODEX_AUTH_HOME_MISMATCH (유효 auth.json 없음)
#   exit 4 = CODEX_CLI_NOT_FOUND

set -uo pipefail

if ! command -v codex >/dev/null 2>&1; then
  echo "CODEX_CLI_NOT_FOUND: 'codex' 실행파일을 PATH 에서 찾지 못함" >&2
  echo "PATH=$PATH" >&2
  exit 4
fi

candidates=()
if [ "$#" -gt 0 ]; then
  candidates=("$@")
elif [ -n "${CODEX_HOME_CANDIDATES:-}" ]; then
  IFS=':' read -r -a candidates <<< "${CODEX_HOME_CANDIDATES}"
else
  candidates=("${CODEX_HOME:-$HOME/.codex}")
fi

ready=""
for h in "${candidates[@]}"; do
  [ -z "$h" ] && continue
  auth="$h/auth.json"
  if [ -s "$auth" ]; then
    echo "[OK] CODEX_HOME=$h → auth.json 존재(비어있지 않음)"
    ready="$h"
    break
  else
    echo "[NG] CODEX_HOME=$h → auth.json 없음/빈파일"
  fi
done

if [ -n "$ready" ]; then
  echo "CODEX_HOME_READY=$ready"
  echo "# 참고: 실제 모델 호출 가능 여부는 read-only discovery smoke 로 최종 확인하라." >&2
  exit 0
fi

echo "CODEX_AUTH_HOME_MISMATCH: 모든 후보 CODEX_HOME 에서 유효 auth.json 미발견" >&2
echo "후보=${candidates[*]}" >&2
exit 3
