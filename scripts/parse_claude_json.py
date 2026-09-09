#!/usr/bin/env python3
"""parse_claude_json.py — claude -p JSON 결과 파싱 (D2, portable, stdlib only).

목적:
    `claude -p ... --output-format json` 은 exit 0 이어도 wrapper 내부에
    is_error=true, result="Not logged in ..." 를 담을 수 있다.
    JSON wrapper만 보고 성공 처리하는 실수를 막기 위해 내부 필드를 기계적으로 추출한다.

사용:
    parse_claude_json.py <결과파일.json>
    cat result.json | parse_claude_json.py -

출력(표준출력):
    is_error / subtype / num_turns / total_cost_usd / errors / result_head 를 key=value 로.
    (공식 result message 필드: is_error·subtype·num_turns·result·total_cost_usd·errors·permission_denials 등.
     출처: code.claude.com/docs agent-sdk result message)
종료코드:
    0 = is_error 가 false 이고 errors 비어있음 이고 permission_denials 없음 (정상)
    2 = is_error 가 true / errors 비어있지 않음 / result 가 비어있음 (claude 내부 에러)
    3 = 위 조건은 정상이나 permission_denials 가 비어있지 않음(도구가 allowlist 에 막혔으나 산문
        result 로 종료 — 조용히 성공 처리하면 미완료 작업을 성공으로 보고하게 된다. §failure-codes.md
        의 --allowedTools 조정 트리아지를 발동시킨다)
    5 = JSON 파싱 실패
"""
from __future__ import annotations

import json
import sys


def _read_source(arg: str) -> str:
    if arg == "-":
        return sys.stdin.read()
    with open(arg, encoding="utf-8") as fh:
        return fh.read()


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: parse_claude_json.py <file.json|->", file=sys.stderr)
        return 64

    raw = _read_source(sys.argv[1])
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"CLAUDE_JSON_PARSE_FAILED: {exc}", file=sys.stderr)
        return 5

    is_error = bool(data.get("is_error"))
    subtype = data.get("subtype")
    num_turns = data.get("num_turns")
    cost = data.get("total_cost_usd")
    result = data.get("result") or ""
    errors = data.get("errors") or []
    permission_denials = data.get("permission_denials") or []

    print(f"is_error={is_error}")
    print(f"subtype={subtype}")
    # num_turns 는 원장 max_turns_used(<int|null>)의 소스 — 부재를 JSON-null 로 명시(풀백 금지: 그럴듯한 값 fill 안 함).
    print(f"num_turns={num_turns if num_turns is not None else 'null'}")
    print(f"total_cost_usd={cost}")
    print(f"errors={errors}")
    print(f"permission_denials={permission_denials}")
    print(f"result_head={result[:500]}")

    if is_error or errors or not str(result).strip():
        return 2
    if permission_denials:
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
