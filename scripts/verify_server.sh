#!/usr/bin/env bash
# verify_server.sh — 서버 health/model self-report 불신 검증 (D3, portable)
#
# 목적:
#   서브에이전트의 "서버 떴다" 자기보고를 믿지 않고 Hermes가 직접 HTTP로 확인한다.
#
# 비과적합 원칙:
#   host/port/엔드포인트를 하드코딩하지 않는다. 모두 인자로 받는다.
#   (host:port 는 호출자가 agent-card / config 에서 '런타임 조립'해서 넘긴다.)
#
# 사용:
#   verify_server.sh <host> <port> [health_path] [models_path]
#   예) verify_server.sh 127.0.0.1 8000 /health /v1/models
#   기본 health_path=/health, models_path=/v1/models
#
# 출력: 각 엔드포인트의 HTTP 상태코드와 본문 일부.
# 종료코드:
#   0 = health 가 200 이고 models 도 200
#   6 = health 가 200 아님 (기동 실패로 간주, '성공' 보고 금지)
#   7 = curl 없음
#   9 = health 는 200 이지만 models 가 200 아님 ('model self-report 불신 검증' 미통과 — 프로필
#       누락/서빙 오류 가능성. 부분 성공을 0 으로 뭉개지 않는다)

set -uo pipefail

if ! command -v curl >/dev/null 2>&1; then
  echo "CURL_NOT_FOUND: curl 이 필요합니다" >&2
  exit 7
fi

HOST="${1:?host 인자 필요}"
PORT="${2:?port 인자 필요}"
HEALTH_PATH="${3:-/health}"
MODELS_PATH="${4:-/v1/models}"

# bind 가 0.0.0.0 이어도 health 는 루프백으로 확인
base="http://${HOST}:${PORT}"

# LAST_PROBE_CODE 로 상태코드를 돌려준다(command substitution 파이프에 태우면 아래 echo/printf 가
# 표준출력에 도달하지 못하고 삼켜진다 — M4 회귀 pin. 반드시 probe() 를 직접 호출하고 그 출력이
# 그대로 stdout 에 나가게 한다).
LAST_PROBE_CODE=""
probe() {
  local url="$1"
  local body code
  body="$(curl -s -m 15 -o - -w $'\n%{http_code}' "$url" 2>/dev/null)" || true
  code="$(printf '%s' "$body" | tail -n1)"
  body="$(printf '%s' "$body" | sed '$d')"
  echo "GET $url -> ${code:-000}"
  printf '  body: %s\n' "$(printf '%s' "$body" | head -c 300)"
  LAST_PROBE_CODE="${code:-000}"
}

echo "== health =="
probe "${base}${HEALTH_PATH}"
hcode="$LAST_PROBE_CODE"

echo "== models =="
probe "${base}${MODELS_PATH}"
mcode="$LAST_PROBE_CODE"

if [ "$hcode" != "200" ]; then
  echo "SERVER_HEALTH_FAILED: ${base}${HEALTH_PATH} 가 200 이 아님(code=${hcode}). '기동 성공'으로 보고 금지." >&2
  exit 6
fi
if [ "$mcode" != "200" ]; then
  echo "SERVER_MODELS_FAILED: ${base}${MODELS_PATH} 가 200 이 아님(code=${mcode}). 'model self-report 불신 검증' 미통과 — health 만으로 성공 보고 금지." >&2
  exit 9
fi
exit 0
