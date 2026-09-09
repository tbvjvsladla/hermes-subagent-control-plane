# Primary / Fallback 무결성 정책 (조용한 대체 금지) — Codex CLI

> 이 스킬의 존재 이유는 **대상 워크스페이스의 '진짜' Codex CLI 서브에이전트**를 제어하는 것이다.
> Codex 측 primary = `codex exec -C <workspace>` 로 그 워크스페이스의 Codex 를 호출하는 것.
> (Claude 측 primary = `claude -p` — `claude-code-control` 동일 정책. 두 스킬 대칭 적용.)

## 1. 핵심 규칙 (단일 측정 가능 규칙)
> **다음 중 어느 것도 primary 성공으로 집계할 수 없다:**
> Hermes 직접 실행 / `delegate_task`(Hermes 내부 위임) / mock / 그 밖의 fallback 경로.
>
> 발생 시 `primary_execution_status = failure` 로 기록하고, 어떤 `primary_success` 수용기준도
> 충족하지 못한다. fallback 은 **"primary 실패 + fallback"** 으로 라벨링할 때만 허용되며,
> **절대 '성공'으로 보고하지 않는다.**

## 2. 실행 원장 (기계적 기록)
```
control_attempt:
  target_workspace: <경로>
  intended_primary: "codex exec -C <workspace>"
  preflight_primary_ready: <true|false>     # scripts/preflight_codex_home.sh (CODEX_HOME_READY)
  primary_invoked: <true|false>             # 실제 codex exec 가 호출됐는가
  # --- A2A TaskState 결과축 (common-rules §K) ---
  task_state: <submitted|working|input-required|auth-required|completed|failed|rejected|canceled|unknown>
  finality: <terminal|interrupted|active>            # task_state 에서 파생
  control_plane: {is_error: <bool>, exit_code: <int>}   # 제어가 돌았나 (scripts/parse_codex_output.py)
  data_plane: {verified: <bool>, paths: [...]}          # 결과물이 맞나 (scripts/verify_artifacts.sh / git diff)
  failure_code: <failed/rejected 시 references/failure-codes.md 코드 | null>
  retry_allowed: <false if finality==terminal>          # terminal 은 final(자동 재시도 금지)
  # --- 무결성(기존 유지) ---
  primary_execution_status: <success|failure>           # success ⟺ task_state==completed
  fallback_used: <none|hermes_direct|delegate_task|other>
  reported_as: <primary_success|primary_failure+fallback>
  # --- budget 축 (v4.2.0 신규, additive — rename 아님, a2a-taskstate-v1 유지) ---
  task_grade: {recommended: <S|L0|L1|L2|L3|L4|null>, assigned: <L0|L1|L2|L3|L4>}   # recommended=discovery 합승, assigned=Hermes 재평가
  timeout_allocated_s: <int>            # assigned grade → references/timeout-budget-grades.md §2 배분 (codex budget = wall-clock)
  wall_seconds_used: <int|null>         # Hermes 측정(terminal 시작→종료; codex 출력엔 없음). 미측정 시 null
  budget_outcome: <ok|timeout_killed>   # terminal timeout 도달로 kill → timeout_killed (다음 재시도 timeout↑, 축소 금지)
  evidence_paths: [<-o 결과파일/로그/git diff/산출물 경로>...]
```

`primary_execution_status=success` 는 다음을 모두 만족할 때만:
- `preflight_primary_ready=true` (유효 CODEX_HOME) 이고 (아니면 `auth-required`)
- `primary_invoked=true` 이고 (아니면 `rejected`)
- read-only discovery smoke 통과(Codex 가 자기 컨텍스트 파일·agent-card 를 실제 인지) 이고
- control-plane: `-o` 결과 파싱(`scripts/parse_codex_output.py`)에 에러 없음 이고
- data-plane: Hermes 의 self-report 불신 검증(git diff/status·산출물 존재/형식)이 통과 (미검증이면 `working`/미완료, `completed` 아님 — common-rules §E·§K).

## 3. E2E 통과 기준 (Level 3)
모듈/Full 테스트 보고서는 다음을 모두 명시해야 통과:
1. 알려진 실패 무재발: CODEX_HOME 격리 · 경로/branch drift · background buffering · OPC layout 회귀.
2. 로그에 primary(진짜 `codex exec`) vs fallback 이 §2 원장 형태로 명시.
3. fallback 이 성공으로 집계되지 않음. 4. 1급 증빙 첨부.

## 4. 실패 시
자동 수정 재시도 금지. 원인 분류(`references/failure-codes.md`)와 **재현 명령**을 보고하고 중단(HITL).
