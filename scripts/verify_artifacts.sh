#!/usr/bin/env bash
# verify_artifacts.sh — Codex 산출물 self-report 불신 검증 (D3, portable)
#
# 목적:
#   Codex 가 "완료"라 해도 믿지 않고, git 변경과 산출 파일을 직접 확인한다.
#
# 비과적합 원칙: 워크스페이스 루트·대상 경로를 인자로 받는다. 하드코딩 금지.
#
# 사용:
#   verify_artifacts.sh <workspace_root> [target_subpath] [expected_glob ...]
#   예) verify_artifacts.sh /path/to/workspace outputs "outputs/final_report/*.pdf"
#
# 출력: git status/diff 요약 + expected_glob 별 매칭 개수.
# 종료코드:
#   0 = 정상 수행(진단 출력)
#   2 = expected_glob 가 주어졌는데 매칭 0건 (산출 실패 의심)

set -uo pipefail

WS="${1:?workspace_root 인자 필요}"
SUB="${2:-}"
shift || true
shift || true  # 남은 인자 = expected globs

if ! command -v git >/dev/null 2>&1; then
  echo "GIT_NOT_FOUND(경고): git 없이 파일 존재만 확인" >&2
else
  echo "== git status (${SUB:-전체}) =="
  git -C "$WS" status --short -- ${SUB:+"$SUB"} 2>&1 | head -40 || true
  echo "== git diff --stat (${SUB:-전체}) =="
  git -C "$WS" diff --stat -- ${SUB:+"$SUB"} 2>&1 | tail -20 || true
fi

rc=0
if [ "$#" -gt 0 ]; then
  for g in "$@"; do
    # glob 확장(워크스페이스 기준)
    shopt -s nullglob
    matches=( "$WS"/$g )
    shopt -u nullglob
    cnt="${#matches[@]}"
    echo "== expected: $g → ${cnt}건 =="
    for m in "${matches[@]}"; do
      printf '   %s' "$m"; command -v file >/dev/null 2>&1 && printf '  [%s]' "$(file -b "$m")"; echo
    done
    [ "$cnt" -eq 0 ] && { echo "ARTIFACT_MISSING: $g 매칭 0건" >&2; rc=2; }
  done
fi
exit "$rc"
