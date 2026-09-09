# Primary / Fallback 무결성 정책 (조용한 대체 금지)

> 이 스킬의 존재 이유는 **대상 워크스페이스의 '진짜' 로컬 CLI 서브에이전트**를 제어하는 것이다.
> Claude 측 primary = `claude -p` 로 그 워크스페이스의 Claude Code 를 호출하는 것.
> (Codex 측 primary = `codex exec -C <workspace>` — `codex-cli-control` 동일 정책.)

## 1. 핵심 규칙 (단일 측정 가능 규칙)
> **다음 중 어느 것도 primary 성공으로 집계할 수 없다:**
> Hermes 직접 실행 / `delegate_task`(Hermes 내부 위임) / mock / 그 밖의 fallback 경로.
>
> 이들이 발생하면 `primary_execution_status = failure` 로 기록하고,
> 어떤 `primary_success` 수용기준(acceptance criterion)도 충족하지 못한다.
> fallback 은 **"primary 실패 + fallback"** 으로 라벨링할 때에만 허용되며,
> **절대 '성공'으로 보고하지 않는다.**

## 2. 왜 이 규칙이 있는가 (실패 사례)
과거 E2E 에서 `claude -p` 가 HOME 격리로 'Not logged in' 실패하자,
①Hermes 가 그 워크스페이스의 실행 스크립트를 직접 돌리고(직접 실행),
②`delegate_task` 로 내부 서브에이전트에 위임한 뒤,
이 둘을 **"✅ 성공"으로 집계**했다. primary 제어는 한 번도 일어나지 않았는데 성공처럼 보고된 것 —
이것이 가장 큰 실패였다. 본 정책은 그 조용한 대체를 구조적으로 차단한다.

## 3. 실행 원장 (기계적 기록)
모든 제어 시도에 대해 다음을 기록한다(로그/response 양쪽):

```
control_attempt:
  target_workspace: <경로>
  intended_primary: "claude -p"            # 또는 "codex exec"
  preflight_primary_ready: <true|false>    # scripts/preflight_*.sh 결과
  primary_invoked: <true|false>            # 실제 claude -p 가 호출됐는가
  # --- A2A TaskState 결과축 (common-rules §K) ---
  task_state: <submitted|working|input-required|auth-required|completed|failed|rejected|canceled|unknown>
  finality: <terminal|interrupted|active>           # task_state 에서 파생
  control_plane: {is_error: <bool>, exit_code: <int>}   # 제어가 돌았나 (scripts/parse_claude_json.py)
  data_plane: {verified: <bool>, paths: [...]}          # 결과물이 맞나 (scripts/verify_*.sh / 산출물)
  failure_code: <failed/rejected 시 references/failure-codes.md 코드 | null>
  retry_allowed: <false if finality==terminal>          # terminal 은 final(자동 재시도 금지)
  # --- 무결성(기존 유지) ---
  primary_execution_status: <success|failure>           # success ⟺ task_state==completed
  fallback_used: <none|hermes_direct|delegate_task|other>
  reported_as: <primary_success|primary_failure+fallback>   # 'primary_success' 는 위 규칙 충족 시에만
  # --- turn-budget 축 (v4.3.0 신규, additive — rename 아님, a2a-taskstate-v1 유지) ---
  task_grade: {recommended: <S|L0|L1|L2|L3|L4|null>, assigned: <L0|L1|L2|L3|L4>}   # recommended=discovery 합승, assigned=Hermes 재평가
  max_turns_allocated: <int>            # assigned grade → references/turn-budget-grades.md §2 배분
  max_turns_used: <int|null>            # 결과 JSON num_turns (scripts/parse_claude_json.py; 부재 시 null)
  budget_outcome: <ok|exhausted>        # error_max_turns & used>=allocated → exhausted (다음 재시도 예산↑, 축소 금지)
  evidence_paths: [<결과파일/로그/health 출력 경로>...]
```

`primary_execution_status=success`(= `task_state=completed`, finality=terminal) 는 다음을 모두 만족할 때만:
- `preflight_primary_ready=true` 이고 (아니면 `auth-required`)
- `primary_invoked=true` 이고 (아니면 `rejected`)
- control-plane: 결과 JSON `is_error=false` (scripts/parse_claude_json.py exit 0) 이고
- data-plane: Hermes 의 self-report 불신 검증(산출물/health/CSV)이 통과 (미검증이면 `working`/미완료, `completed` 아님 — common-rules §E·§K).

## 4. E2E 통과 기준 (Level 3)
모듈/Full 테스트 보고서는 다음을 모두 명시해야 통과(Lv3):
1. 알려진 실패 4종 무재발: HOME/profile 로그인 격리 · 경로/branch drift · background buffering · OPC layout 회귀.
2. 로그에 **primary 가 실제 실행됐는지 vs fallback 인지**가 §3 원장 형태로 명시.
3. fallback 이 성공으로 집계되지 않았음.
4. 각 항목의 1급 증빙(실행 명령·exit code·raw I/O 발췌·파일 경로) 첨부.

## 5. 실패 시
자동 수정 재시도 금지. 즉시 원인 분류(`references/failure-codes.md`)와 **재현 명령**을 사용자에게 보고하고 중단(HITL).
