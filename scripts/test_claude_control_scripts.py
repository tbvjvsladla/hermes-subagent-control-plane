#!/usr/bin/env python3
"""결정론 스크립트 회귀 테스트 — claude-code-control.

exit-code 계약을 고정한다(LLM/네트워크 없음). pytest 또는 `python3 test_scripts.py` 로 실행.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)  # scripts/ 의 부모 = 스킬 루트


def _run(script: str, *args: str, stdin: str | None = None) -> int:
    cmd = [sys.executable, os.path.join(HERE, script), *args]
    return subprocess.run(cmd, input=stdin, text=True, capture_output=True).returncode


def test_parse_claude_json_success():
    assert _run("parse_claude_json.py", "-", stdin='{"is_error":false,"result":"OK"}') == 0


def test_parse_claude_json_is_error():
    assert _run("parse_claude_json.py", "-", stdin='{"is_error":true,"result":"Not logged in"}') == 2


def test_parse_claude_json_empty_result():
    assert _run("parse_claude_json.py", "-", stdin='{"is_error":false,"result":""}') == 2


def test_parse_claude_json_bad_json():
    assert _run("parse_claude_json.py", "-", stdin="not json") == 5


def test_parse_claude_json_errors_array():
    # 공식 result message 의 errors 배열이 비어있지 않으면 실패로 본다
    assert _run("parse_claude_json.py", "-", stdin='{"is_error":false,"result":"x","errors":["api 500"]}') == 2


def test_card_drift_detects_missing_and_module():
    with tempfile.TemporaryDirectory() as d:
        card = {
            "workspace": {"serve": {"command": "uv run python -m app.serve",
                                     "port_config_path": "envs/config.yaml"}},
            "skills": [{"invoke": {"command": "python scripts/run.py"}}],
        }
        cpath = os.path.join(d, "agent-card.json")
        with open(cpath, "w", encoding="utf-8") as fh:
            json.dump(card, fh)
        # 아무 파일도 만들지 않음 → 모듈/스크립트/config 전부 MISSING
        assert _run("card_drift_check.py", cpath, d) == 8


def test_card_drift_clean():
    with tempfile.TemporaryDirectory() as d:
        card = {"workspace": {"serve": {"command": "uv run python -m app.serve"}}}
        cpath = os.path.join(d, "agent-card.json")
        with open(cpath, "w", encoding="utf-8") as fh:
            json.dump(card, fh)
        os.makedirs(os.path.join(d, "app"))
        open(os.path.join(d, "app", "serve.py"), "w").close()
        assert _run("card_drift_check.py", cpath, d) == 0


# =====================================================================
# v4.3.0 turn-budget / grade 위임 개선 — 결정론 문서-핀 + num_turns 핀
# (LLM/네트워크 없음. 위험문구 재발·정본 포인터·grade표·원장·실패방향을 고정.)
# =====================================================================


def _read(rel: str) -> str:
    """스킬 루트 기준 상대경로 파일을 읽는다(references/*.md, SKILL.md)."""
    with open(os.path.join(SKILL_ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


def _run_out(script: str, *args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    cmd = [sys.executable, os.path.join(HERE, script), *args]
    return subprocess.run(cmd, input=stdin, text=True, capture_output=True)


def test_turn_budget_grades_is_canonical_with_all_grades():
    txt = _read("references/turn-budget-grades.md")
    for g in ["L0", "L1", "L2", "L3", "L4"]:
        assert re.search(rf"\b{g}\b", txt), f"grade {g} missing in turn-budget-grades.md"
    # 두 축 원칙(scope ⊥ budget) + 하한 ≥6
    assert "scope" in txt and "budget" in txt
    assert "≥6" in txt  # 하한을 리터럴로 핀('6'은 날짜·범위·헤더에 편재 → vacuous)


def test_failure_codes_max_turns_direction_reversed():
    txt = _read("references/failure-codes.md")
    # 하강나선을 조장하던 위험 문구 제거
    assert "더 작게 쪼개고 재시도" not in txt
    # 교정: 예산 증가 방향 + 축소 금지 + hang 은 watchdog/timeout
    assert re.search(r"늘린|증가", txt)
    assert "줄이지 말" in txt   # 방향 핀: '줄이'만으론 반대방향 '줄이고'도 통과
    assert "watchdog" in txt   # 'timeout'은 BACKGROUND_BUFFERING 행에도 있어 vacuous → 고유어 watchdog 핀


def test_triage_gate_g4_budget_wording_fixed():
    txt = _read("references/delegation-triage-gate.md")
    # 위험: "max-turns 는 작게" (백틱 허용). 단, 정당한 "단계는 작게"(scope)는 건드리지 않음.
    assert not re.search(r"max-turns[^\n]{0,5}는 작게", txt)
    assert "turn-budget-grades.md" in txt          # 정본 포인터
    assert "충분" in txt   # 'grade'는 'turn-budget-grades.md'의 부분문자열 → 교정어 '충분히' 자체를 핀


def test_skill_md_version_and_budget_pointer():
    txt = _read("SKILL.md")
    assert "version: 4.3.0" in txt
    assert "turn-budget-grades.md" in txt
    assert "단일 작업 3~6 turn" not in txt          # P5: 낡은 turn 표현 제거
    # Step C/D 예산 흐름의 실제 구조 변경을 핀(위 negative 만으론 커버 못 함)
    assert "--max-turns 3 --output-format" not in txt   # Step C 예산 3→8
    assert "grade→배분값" in txt                          # Step D 매직상수 15→배분값


def test_e2e_lessons_714_data_and_caveats():
    txt = _read("references/e2e-lessons-learned.md")
    # 714 실측: 단일 Bash 가 max-turns 2/4 실패, 6 성공
    assert re.search(r"max-turns 2|--max-turns 2|2/4", txt)
    # P4: KV clamp 수치 스코프 caveat
    assert "전용 예제" in txt
    # 축2: 3~6 은 budget 하한이 아님
    assert "하한이 아" in txt
    # §6 복구트리·§7 체크리스트의 구 하강나선 숫자 회귀 가드(적대재검증 발견)
    assert "진단 15" not in txt
    assert "단일 작업 6~8" not in txt


def test_ledger_turn_budget_fields_present():
    txt = _read("references/primary-fallback-policy.md")
    for field in ["task_grade", "max_turns_allocated", "max_turns_used", "budget_outcome"]:
        assert field in txt, f"ledger field {field} missing in primary-fallback-policy.md"


def test_parse_surfaces_num_turns_present():
    p = _run_out("parse_claude_json.py", "-",
                 stdin='{"is_error":false,"result":"OK","num_turns":6}')
    assert p.returncode == 0
    assert "num_turns=6" in p.stdout


def test_parse_surfaces_num_turns_absent_as_null():
    # 풀백 금지 — 부재를 그럴듯한 값으로 채우지 않고 원장 <int|null> 계약대로 null 표면화.
    p = _run_out("parse_claude_json.py", "-",
                 stdin='{"is_error":false,"result":"OK"}')
    assert p.returncode == 0
    assert "num_turns=null" in p.stdout


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} passed")
