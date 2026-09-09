# 실패 분류표 — Codex CLI 제어

> 증상을 코드로 분류하고 정해진 조치를 취한다. 추측 진행(모킹) 금지.
> 경로·CODEX_HOME 은 런타임 값으로 다룬다(하드코딩 금지).

| 코드 | 판정 기준 | 조치 |
|---|---|---|
| `SKILL_NOT_LOADED` | 이 스킬을 로드하지 않고 일반 답변/직접실행함 | `codex-cli-control` 명시 호출. profile external_dirs 확인 |
| `CODEX_CLI_NOT_FOUND` | `codex` 실행파일이 PATH 에 없음 (`preflight_codex_home.sh` exit 4) | `command -v codex` 확인, PATH 보고 |
| `CODEX_AUTH_HOME_MISMATCH` | 후보 CODEX_HOME 에 유효 `auth.json` 없음 (preflight exit 3) | preflight 가 찾은 `CODEX_HOME_READY` 사용. 후보를 환경/인자로 보강. 대안: `codex exec` 한정 `CODEX_API_KEY` 인라인 |
| `WRONG_WORKDIR_OR_C` | Codex 가 엉뚱한 워크스페이스 기준 실행 / 컨텍스트 파일 미인지 | terminal `workdir` + `codex -C <workspace>` 동시 명시 |
| `CONTEXT_FILE_NOT_AUTOLOADED` | `CODEX.md` 의존 — 자동 로드 안 됨 | 컨텍스트를 Card `context_file`(Codex 표준) 로 정렬하거나 `@file` 로 명시 주입 |
| `CARD_MISSING_OR_STALE` | agent-card 없음/스키마 불일치/null·unknown | 사용자 보고 후 Card 작성·갱신 제안 |
| `CARD_DRIFT_DETECTED` | 카드 선언 경로가 실제 FS 에 없음 (`card_drift_check.py` exit 8) | 실제 경로 재확인 후 실행 |
| `CODEX_OUTPUT_EMPTY` | `-o` 결과 파일이 비어있음 (`parse_codex_output.py` exit 2) | 출력 캡처(`-o`)·sandbox·프롬프트 확인. 산출 실패로 간주 |
| `CODEX_OUTPUT_ERROR` | JSONL 에 `error` 또는 `turn.failed` 이벤트 (`parse_codex_output.py` exit 3) | 이벤트 원문 보고, 본작업 중단 |
| `TIMEOUT_KILLED` | terminal `timeout` 도달로 `codex exec` 가 완수 전 kill (codex 는 `--max-turns` 없음 — budget=wall-clock timeout) | **timeout 을 줄이지 말 것**(하강나선). 두 축 진단 — ①범위 2개↑ → 쪼갠다 ②완수 전 kill → context 주입 + **timeout 증가**. hang 은 tight timeout 아닌 **log-watch + 선언된 runtime 상태 + Hermes 사후 검증**으로 분리. terminal → 새 control_attempt(더 큰 timeout). 정본: `references/timeout-budget-grades.md` §5 |
| `CODEX_TRANSPORT_UNREACHABLE` | discovery/action에서 connection refused, stream disconnected 등 provider 전송 오류 | proxy·패키지·서비스를 자동 설치·기동하지 않는다. 오류 원문을 보존해 사용자에게 보고하고, 사용자 지시가 있을 때만 별도 환경 진단을 수행한다. |
| `SANDBOX_UNKNOWN` | Card `workspace.codex.sandbox` 가 `unknown` | 추측해 박지 말고 사용자 보고 후 판단(§common-rules B) |
| `MODEL_UNRESOLVED` | `codex.model` 이 `null`(미확정) | `-m` 생략은 가능하나 미확정 보고. 특정 버전 추측 금지 |
| `ARTIFACT_MISSING` | expected 산출물 매칭 0건 (`verify_artifacts.sh` exit 2) | '완료' 보고 금지. 로그·sandbox 확인 |
| `POSTPROCESS_SKIPPED` | deterministic script 성공인데 Agent OS 후처리 필드 비어있음 | `common-rules §E`(결정론 성공 ≠ 완료) 적용 — 후처리 필드 검증 전 done 금지 |
| `INSTALL_WITHOUT_APPROVAL` | 승인 안 된 MCP/플러그인 설치 지시 | 워크스페이스 검수 게이트 위반. 중단·보고 |
| `SILENT_FALLBACK` | primary 실패를 직접실행/`delegate_task` 로 조용히 대체해 성공 집계 | **금지.** `references/primary-fallback-policy.md` 적용 |

## 상태축 매핑 (common-rules §K — 원장 `task_state`)
각 코드를 A2A TaskState 로 분류한다. Hermes 는 이걸로 `finality`·`retry_allowed`·처방을 정한다.

| state | finality | 코드 |
|---|---|---|
| `rejected` (시작 전 거부) | terminal | `CODEX_CLI_NOT_FOUND`, `WRONG_WORKDIR_OR_C`, `CONTEXT_FILE_NOT_AUTOLOADED`, `CARD_DRIFT_DETECTED`, `SKILL_NOT_LOADED`, `INSTALL_WITHOUT_APPROVAL`, `CODEX_TRANSPORT_UNREACHABLE`, (triage G1/G3 차단) |
| `auth-required` (인증 미준비) | interrupted | `CODEX_AUTH_HOME_MISMATCH` |
| `failed` (시작 후 에러) | terminal | `CODEX_OUTPUT_ERROR`, `TIMEOUT_KILLED` |
| `unknown` (판정 불가→재질의/fallback) | 제어불가 | `CARD_MISSING_OR_STALE`, `CODEX_OUTPUT_EMPTY`, `SANDBOX_UNKNOWN`, `MODEL_UNRESOLVED` |
| `completed` 아님(미검증=`working`) | active | `POSTPROCESS_SKIPPED`, `ARTIFACT_MISSING` (data-plane 산출물 검증 미통과 = 미완료, `completed`/`failed` 아님 — §E/§K. claude `SELF_REPORT_UNVERIFIED` 와 대칭) |
| (무결성) | — | `SILENT_FALLBACK` → `primary_execution_status=failure` |
