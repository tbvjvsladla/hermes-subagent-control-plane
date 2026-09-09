#!/usr/bin/env python3
"""card_drift_check.py — agent-card 선언 경로 vs 실제 파일시스템 drift 탐지 (D4, portable, stdlib only).

배경:
    E2E 실패 사례에서 agent-card 가 가리키던 script 경로(scripts/)가 실제로는 app/ 로
    이전되어 있었고 branch 도 바뀌어 있었다. SDD/스킬에 박힌 경로를 맹신하면 깨진다.
    본 스크립트는 카드가 '선언한' 경로가 실제로 존재하는지 기계적으로 대조한다.

비과적합 원칙:
    카드 경로·워크스페이스 루트를 인자로 받는다. 특정 머신 경로를 하드코딩하지 않는다.

사용:
    card_drift_check.py <agent-card.json> [workspace_root]
    workspace_root 생략 시 카드 파일이 있는 디렉터리를 루트로 본다.

검사 대상(존재하면):
    - workspace.serve.command / skills[].invoke.command 안의 파일 토큰(.py/.yaml 등)
    - 모듈 실행 구문 `python -m a.b.c` → `a/b/c.py` 로 환산해 검사 (E2E §4.2 모듈 drift 대응)
    - workspace.serve.*_config_path

출력: 선언 경로별 [OK]/[MISSING]. 종료코드 0=drift 없음, 8=MISSING 1건 이상, 5=파싱 실패.
주의: 셸 변수/동적 경로는 정적 검증 불가. 검사 가능한 토큰이 0개면 그 사실을 명시한다(거짓 'OK' 금지).
"""
from __future__ import annotations

import json
import os
import re
import sys

PATHLIKE = re.compile(r"[\w./-]+\.(?:py|yaml|yml|json|toml|sh|md|cfg|ini)\b")
MODULE = re.compile(r"-m\s+([A-Za-z_][\w.]+)")


def _tokens_from_command(cmd: str) -> list[str]:
    out = list(PATHLIKE.findall(cmd))
    # 모듈 구문 `python -m a.b.c` → 후보 파일경로 a/b/c.py (확장자 없는 entrypoint drift 포착)
    for mod in MODULE.findall(cmd):
        out.append(mod.replace(".", "/") + ".py")
    return out


def _candidate_paths(card: dict) -> list[str]:
    out: list[str] = []
    ws = card.get("workspace", {}) or {}
    serve = ws.get("serve", {}) or {}
    if isinstance(serve.get("command"), str):
        out += _tokens_from_command(serve["command"])
    for key, val in serve.items():
        if key.endswith("config_path") and isinstance(val, str) and val:
            out.append(val)
    for skill in card.get("skills", []) or []:
        inv = (skill or {}).get("invoke", {}) or {}
        cmd = inv.get("command")
        if isinstance(cmd, str):
            out += _tokens_from_command(cmd)
    # 중복 제거(순서 보존)
    seen, uniq = set(), []
    for p in out:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


def main() -> int:
    if not 2 <= len(sys.argv) <= 3:
        print("usage: card_drift_check.py <agent-card.json> [workspace_root]", file=sys.stderr)
        return 64

    card_path = sys.argv[1]
    root = sys.argv[2] if len(sys.argv) == 3 else os.path.dirname(os.path.abspath(card_path))

    try:
        with open(card_path, encoding="utf-8") as fh:
            card = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"CARD_PARSE_FAILED: {exc}", file=sys.stderr)
        return 5

    paths = _candidate_paths(card)
    if not paths:
        print("정적 검증 가능한 경로 토큰 0개(예: 셸변수/동적경로). drift '없음'이 아니라 '미검증' — 에이전트가 실제 entrypoint를 별도 확인할 것.")
        return 0

    missing = 0
    for rel in paths:
        abs_p = rel if os.path.isabs(rel) else os.path.join(root, rel)
        if os.path.exists(abs_p):
            print(f"[OK]      {rel}")
        else:
            print(f"[MISSING] {rel}  (기준 root={root})")
            missing += 1

    if missing:
        print(f"CARD_DRIFT_DETECTED: {missing}건 누락. agent-card 와 실제 파일시스템 불일치.", file=sys.stderr)
        return 8
    return 0


if __name__ == "__main__":
    sys.exit(main())
