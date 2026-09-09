#!/usr/bin/env python3
"""결정론 스크립트 회귀 테스트 — codex-cli-control.

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


def test_parse_codex_output_empty():
    assert _run("parse_codex_output.py", "-", stdin="   \n  ") == 2


def test_parse_codex_output_text():
    assert _run("parse_codex_output.py", "-", stdin="Report written to outputs/final.pdf") == 0


def test_parse_codex_output_jsonl_clean():
    jsonl = '{"type":"message","text":"done"}\n{"type":"summary","text":"ok"}'
    assert _run("parse_codex_output.py", "-", stdin=jsonl) == 0


def test_parse_codex_output_jsonl_error():
    jsonl = '{"type":"item.completed","text":"start"}\n{"type":"error","message":"sandbox denied"}'
    assert _run("parse_codex_output.py", "-", stdin=jsonl) == 3


def test_parse_codex_output_jsonl_turn_failed():
    # 공식 이벤트 타입 turn.failed 도 에러로 잡아야 한다
    jsonl = '{"type":"turn.started"}\n{"type":"turn.failed","error":{"message":"timeout"}}'
    assert _run("parse_codex_output.py", "-", stdin=jsonl) == 3


def test_card_drift_detects_missing_and_module():
    with tempfile.TemporaryDirectory() as d:
        card = {
            "workspace": {"serve": {"command": "uv run python -m app.report"}},
            "skills": [{"invoke": {"command": "python scripts/gen.py"}}],
        }
        cpath = os.path.join(d, "agent-card.json")
        with open(cpath, "w", encoding="utf-8") as fh:
            json.dump(card, fh)
        assert _run("card_drift_check.py", cpath, d) == 8


# =====================================================================
# v4.2.0 timeout-budget / grade 위임 적응 — 결정론 문서-핀
# (codex는 --max-turns 없음 → budget=wall-clock timeout. LLM/네트워크 없음.)
# =====================================================================


def _read(rel: str) -> str:
    with open(os.path.join(SKILL_ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


def test_timeout_budget_grades_is_canonical_with_all_grades():
    txt = _read("references/timeout-budget-grades.md")
    for g in ["L0", "L1", "L2", "L3", "L4"]:
        assert re.search(rf"\b{g}\b", txt), f"grade {g} missing in timeout-budget-grades.md"
    assert "scope" in txt and "budget" in txt
    assert "timeout" in txt   # codex budget 축 = wall-clock timeout


def test_failure_codes_timeout_killed_direction():
    txt = _read("references/failure-codes.md")
    assert "TIMEOUT_KILLED" in txt
    assert "CODEX_TRANSPORT_UNREACHABLE" in txt
    assert re.search(r"늘린|증가", txt)
    assert "줄이지 말" in txt          # timeout 축소 금지(방향)
    assert "log-watch" in txt          # hang은 tight timeout 아닌 log-watch로


def test_triage_gate_no_maxturns_tuning_for_codex():
    txt = _read("references/delegation-triage-gate.md")
    # codex는 --max-turns knob이 없다 — 튜닝/오참조 지침 부재여야
    assert not re.search(r"max-turns[^\n]{0,5}는 작게", txt)
    assert not re.search(r"--max-turns.{0,6}넉넉히", txt)
    assert "`--max-turns` 위임" not in txt
    assert "timeout-budget-grades.md" in txt   # 정본 포인터
    assert "grade→" in txt                      # grade 배분 문구(교정어)


def test_skill_md_version_and_budget_pointer():
    txt = _read("SKILL.md")
    assert "version: 4.3.0" in txt
    assert "timeout-budget-grades.md" in txt
    assert "grade_recommended" in txt   # Step C 합승


def test_ledger_timeout_budget_fields_present():
    txt = _read("references/primary-fallback-policy.md")
    for field in ["task_grade", "timeout_allocated_s", "wall_seconds_used", "budget_outcome"]:
        assert field in txt, f"ledger field {field} missing in primary-fallback-policy.md"


def test_common_rules_failed_example_genericized():
    # §K failed-row 예시가 codex에 없는 max_turns를 budget-failure 예로 제시하지 않도록 제네릭화(Option① 완결, 적대재검증 발견).
    txt = _read("references/common-rules.md")
    assert "budget 소진" in txt


def test_removed_tool_dependencies_are_absent_from_control_contract():
    banned = ("head" + "room", "rt" + "k", "ser" + "ena", "878" + "7")
    contract_files = (
        "SKILL.md",
        "references/failure-codes.md",
        "references/timeout-budget-grades.md",
    )
    for rel in contract_files:
        text = _read(rel).lower()
        for token in banned:
            assert token not in text, f"{token} remains in {rel}"

    removed_script = os.path.join(HERE, "check_" + "head" + "room_proxy.sh")
    assert not os.path.exists(removed_script)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} passed")
