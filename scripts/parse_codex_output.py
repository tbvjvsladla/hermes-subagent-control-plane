#!/usr/bin/env python3
"""parse_codex_output.py — codex exec 결과(-o 파일) 파싱 (D2, portable, stdlib only).

배경:
    `codex exec -o <file>`(= `--output-last-message`)는 최종 에이전트 메시지를 파일에 쓴다(stdout 에도 출력).
    `--json` 을 주면 JSONL(줄당 JSON 이벤트)이 된다. 공식 이벤트 타입:
    thread.started / turn.started|completed|failed / item.started|completed / error.
    어느 형식이든 '비어있음/에러'를 기계적으로 판정해 self-report 불신을 보조한다.
    (출처: developers.openai.com/codex/noninteractive)

사용:
    parse_codex_output.py <결과파일>
    cat out.txt | parse_codex_output.py -

출력: format / lines / last_message_head / error_seen 를 key=value 로.
종료코드:
    0 = 비어있지 않고 명시적 에러 이벤트 없음
    2 = 비어있음 (산출 실패 의심)
    3 = JSONL 에서 error 류 이벤트 발견
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
        print("usage: parse_codex_output.py <file|->", file=sys.stderr)
        return 64

    raw = _read_source(sys.argv[1]).strip()
    if not raw:
        print("format=empty")
        print("CODEX_OUTPUT_EMPTY: 결과가 비어있음", file=sys.stderr)
        return 2

    lines = raw.splitlines()
    # JSONL 여부 판단: 줄 다수가 JSON 객체로 파싱되면 JSONL
    json_objs = []
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        try:
            json_objs.append(json.loads(ln))
        except json.JSONDecodeError:
            json_objs = []
            break

    if json_objs:
        def _is_err(o: dict) -> bool:
            t = str(o.get("type", "")).lower()
            return t == "error" or t.endswith(".failed")  # 공식: error, turn.failed

        error_seen = any(_is_err(o) for o in json_objs)
        # 마지막 메시지성 이벤트 추출
        last_msg = ""
        for o in reversed(json_objs):
            for key in ("message", "text", "content", "result"):
                if isinstance(o.get(key), str) and o[key].strip():
                    last_msg = o[key]
                    break
            if last_msg:
                break
        print("format=jsonl")
        print(f"lines={len(json_objs)}")
        print(f"last_message_head={last_msg[:500]}")
        print(f"error_seen={error_seen}")
        return 3 if error_seen else 0

    print("format=text")
    print(f"lines={len(lines)}")
    print(f"last_message_head={raw[:500]}")
    print("error_seen=False")
    return 0


if __name__ == "__main__":
    sys.exit(main())
