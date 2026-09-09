# 실패 분류표 — Claude Code 제어

> 증상을 코드로 분류하고 정해진 조치를 취한다. 추측 진행(모킹) 금지.
> 경로·HOME 은 모두 런타임 값으로 다룬다(하드코딩 금지).

| 코드 | 판정 기준 | 조치 |
|---|---|---|
| `SKILL_NOT_LOADED` | 이 스킬을 로드하지 않고 일반 답변/직접실행함 | 다음 turn 에서 `claude-code-control` 명시 호출. profile external_dirs 확인 |
| `CLAUDE_CLI_NOT_FOUND` | `claude` 실행파일이 PATH 에 없음 (`scripts/preflight_claude_auth.sh` exit 4) | `command -v claude` 확인, profile shell init/PATH 보고 |
| `CLAUDE_AUTH_HOME_MISMATCH` | 모든 후보 HOME 에서 Not logged in (preflight exit 3). Linux 자격증명은 `~/.claude/.credentials.json` (HOME 기준 확장) | preflight 가 찾은 유효 HOME 사용. 공식 override 는 `CLAUDE_CONFIG_DIR`(Linux/Win). 후보를 환경/인자로 보강. 없으면 사용자 보고 |
| `WRONG_WORKDIR` | Claude 가 엉뚱한 워크스페이스를 언급/컨텍스트 파일 미인지 | terminal `workdir` 수정. `cwd` 사용 금지 |
| `CARD_MISSING_OR_STALE` | agent-card 없음/스키마 불일치/null·unknown | 사용자 보고 후 Card 작성·갱신 제안 |
| `CARD_DRIFT_DETECTED` | 카드 선언 경로가 실제 FS 에 없음 (`scripts/card_drift_check.py` exit 8) | 실제 경로 재확인 후 실행. SDD 박힌 경로 맹신 금지 |
| `CLAUDE_JSON_ERROR` | exit 0 이지만 JSON `is_error=true` (`scripts/parse_claude_json.py` exit 2) | result 를 에러로 취급, 본작업 중단 |
| `CLAUDE_JSON_PARSE_FAILED` | 결과가 JSON 으로 파싱 안 됨 (parse exit 5) | 출력 캡처 방식·`--output-format json` 확인 |
| `MAX_TURNS_EXHAUSTED` | `--max-turns` 한도 도달로 `is_error=true` (정확한 `subtype` 값은 공식문서 미정의 → `is_error`/`errors`로 판정) | **max-turns 를 줄이지 말 것**(하강나선). 두 축 진단 — ①범위 2개↑ → 쪼갠다 ②budget 굶음/탐색낭비 → G5 주입 + **max-turns 증가**. hang 은 timeout/log watchdog 으로 분리 감지. terminal → 새 control_attempt(더 큰 예산). 정본: `references/turn-budget-grades.md` §5 |
| `PERMISSION_OR_TOOL_DENIED` | Claude 가 도구 권한 부족 보고 (JSON `permission_denials` 배열) | `--allowedTools` 조정. 위험 도구는 사용자 승인 |
| `SERVER_HEALTH_FAILED` | health 가 200 아님 (`scripts/verify_server.sh` exit 6) | 로그 tail, 포트 점유 확인. '기동 성공' 보고 금지 |
| `BACKGROUND_BUFFERING` | 장시간 LLM 작업을 background 로 돌려 출력 0줄 | foreground + 충분한 timeout 으로 재실행(또는 unbuffered) |
| `SELF_REPORT_UNVERIFIED` | 완료라 했지만 산출물/health 없음 | 실패로 보고. 다음 단계 진행 금지 |
| `SILENT_FALLBACK` | primary 실패를 직접실행/`delegate_task` 로 조용히 대체해 성공 집계 | **금지.** `references/primary-fallback-policy.md` 적용 — primary_failure 로 기록 |

## 상태축 매핑 (common-rules §K — 원장 `task_state`)
각 코드를 A2A TaskState 로 분류한다. Hermes 는 이걸로 `finality`·`retry_allowed`·처방을 정한다.

| state | finality | 코드 |
|---|---|---|
| `rejected` (시작 전 거부) | terminal | `CLAUDE_CLI_NOT_FOUND`, `WRONG_WORKDIR`, `CARD_DRIFT_DETECTED`, `SKILL_NOT_LOADED`, (triage G1/G3 차단) |
| `auth-required` (인증 미준비) | interrupted | `CLAUDE_AUTH_HOME_MISMATCH` |
| `failed` (시작 후 에러) | terminal | `MAX_TURNS_EXHAUSTED`, `CLAUDE_JSON_ERROR`, `SERVER_HEALTH_FAILED`, `PERMISSION_OR_TOOL_DENIED` |
| `unknown` (판정 불가→재질의/fallback) | 제어불가 | `CARD_MISSING_OR_STALE`, `CLAUDE_JSON_PARSE_FAILED`, `BACKGROUND_BUFFERING` |
| `completed` 아님(미검증=`working`) | active | `SELF_REPORT_UNVERIFIED` (data-plane 검증 전 `completed` 금지) |
| (무결성) | — | `SILENT_FALLBACK` → `primary_execution_status=failure` |
