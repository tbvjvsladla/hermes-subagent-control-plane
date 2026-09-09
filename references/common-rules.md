# 공통 규칙 — 로컬 CLI 서브에이전트 제어 (Claude Code / Codex CLI 공유)

> 이 파일은 `claude-code-control`·`codex-cli-control` 두 스킬이 공유하는 공통 원칙이다.
> Hermes 스킬 모델상 reference 는 **각 스킬 자기 폴더 기준**으로 로드되므로, 이 파일은
> 두 스킬의 `references/` 에 **각각 사본**으로 존재한다. 로드는
> `skill_view("<skill>", "references/common-rules.md")` 로 한다.
> (스킬 바깥 공유 경로를 `skill_view` 로 부르지 않는다 — 도달하지 못한다.)

## 0. 비과적합(Portable) 원칙
- 머신 종속 절대경로(예: 특정 사용자 홈, 특정 워크스페이스 절대경로)를 본문에 하드코딩하지 않는다.
- 경로는 런타임 변수(`${HERMES_SKILL_DIR}`, 호출자 주입 인자, agent-card/config 값)로 다룬다.
- HOME·인증 위치·포트·모델·branch 는 '탐지'하거나 '설정에서 조립'한다. 추측해 박지 않는다.

## A. Agent Card 기반 Capability Discovery
모든 서브에이전트 제어는 Agent Card 읽기로 시작한다. Card 는 "A2A 영감 로컬 capability manifest"이지 A2A 정식 스펙이 아니다.
1. `read_file("<workspace_root>/<agent_name>/agent-card.json")` — Card 로드
2. `agent_os` 확인 → `"claude-code"` 또는 `"codex-cli"`
3. `skills[]` 에서 요청과 매칭되는 skill 탐색 (`examples` → `tags` → `name` → `description` 순)
4. 매칭 skill 의 `invoke.command`, `verification` 추출
5. `workspace` 객체에서 런타임 정보(`runtime`, `serve`, `codex`) 추출

## B. 4-state sentinel 소비 계약 (모킹 차단 — 최우선)
| 값 | 의미 | 처리 |
|---|---|---|
| `"none"` | 의도적 부재(정답) | 그대로 진행 |
| `"default"` | 기본 위임(정답) | 그대로 진행. 예: `codex.model="default"` → `-m` 생략 |
| `null` | 미확정·결정 필요 | **보고 후 판단** (silent 진행 금지) |
| `"unknown"` | 확인 불가 | **보고 후 판단** (silent 진행 금지) |

`null`/`"unknown"` 또는 **Card 자체가 없으면**: ①사실을 사용자에게 보고 ②판단(대안/부분실행/질의) ③추측 기본값으로 가짜 진행(모킹) 금지 ④무조건 중단도 아님.

> A2A 정합: 제어 **결과축**에서 판정 불가는 §K `unknown` 상태(재질의/fallback)에 대응한다 — Card 필드값 sentinel(여기 §B)과 결과 state(§K)는 같은 "추측 금지" 규율을 공유한다.

## C. 스키마 잠금 인지 (Hermes 소유)
- Agent Card 구조(필드)는 Hermes 소유다. 서브에이전트가 필드를 가감했다면 규약 위반이므로 신뢰 전에 보고한다.
- Hermes 는 Card 를 **읽기만** 한다(서브에이전트만 자신의 Card 갱신).

## D. 작업 디렉토리 분리 원칙 (스킬 위치 ≠ 작업 대상)
- 제어 대상 작업공간은 Hermes `terminal` 의 `workdir` 로 **항상 명시**한다. `cwd` 는 인자명이 아니다.
- CLI 자체에도 작업공간 인자를 함께 준다(예: Codex `-C <workspace>`).
- 컨텍스트 파일(Card `workspace.context_file`)은 작업 디렉토리 기준 자동 로드되므로 루트를 정확히 둔다.

## E. self-report 불신 검증 (필수)
CLI 에이전트가 "완료"라 해도 맹신하지 않는다. Hermes 가 직접 확인한다.
- 파일 산출물: `ls -lh`, `file`, `git diff --stat` 로 존재·크기·형식 확인
- 서버/산출물: host:port 를 config 에서 조립 → `curl` 또는 산출물 존재 확인 (본 스킬의 `scripts/verify_*.sh`)
- CLI 출력: 내부 필드/에러 파싱 (본 스킬의 `scripts/parse_*.py`)
- exit code 확인. Card 의 `skills[].verification` 우선 사용.
- **결정론 단계 성공 ≠ 완료**: 위임한 스킬이 결정론 스크립트 + LLM/Agent OS 후처리를 모두 가지면, 후처리 필드가 채워지고 검증되기 전엔 '완료'가 아니다(빈 문자열·원시 상태 = 미완료). 선언된 산출물 집합을 재귀 검증하되(manifest/index/control 파일 제외), Hermes 가 검증기를 독립 재실행해 빈 필드 count 를 직접 확인한다. 다운스트림이 교정 전 파일을 소비했으면 재생성·반영을 확인한다.

> A2A 정합: §K `completed` 는 **검증된 비즈니스 결과**를 뜻한다 — 결정론 스크립트 exit 0 은 `working`(또는 미검증)이지 `completed` 가 아니다. data-plane(산출물) 검증 통과 전에는 terminal `completed` 로 보고하지 않는다.

## F. Plan A/B/C 우선순위
| Plan | 전략 | 적합 상황 |
|------|------|-----------|
| 🥇 A | 대상 OS별 primary 제어 경로 | Claude: discovery+`claude -p` / Codex: discovery+`codex exec` |
| 🥈 B | OS별 디버깅/대체 출력 경로 | JSON 파싱, `--json`, 제한 tool/sandbox 조정 |
| 🥉 C | Hermes 직접 실행 fallback | CLI 제어가 막혔지만 산출이 필요할 때 — **반드시 fallback 라벨** |

> **폴백 ≠ 가짜 성공**: 폴백은 "다른 실행 경로"이지 "모르는 값 추측"이 아니다. primary/fallback 판정은 `references/primary-fallback-policy.md` 를 따른다.

## G. health check / 실행 실패 폴백 (가짜 성공 금지)
서버 기동·검증 실패 시: ①"성공" 보고 금지 ②백그라운드 로그 tail ③포트 점유는 `lsof -i :<조립 port>` ④원인·로그 보고 후 다음 판단 제안.

## H. 명령형/질문형 구분
- 명령형("기동해줘","변환해서 보내줘")일 때만 직접 실행.
- 질문형("어떻게 해?")엔 실행하지 않고 단계 안내만(인지부채 방지).

## I. 환경 격리 / CLI 인증 (Portable preflight)
- Hermes terminal 이 profile 별 HOME 을 격리하면 CLI 인증정보(`~/.claude`, `~/.codex`)를 못 찾을 수 있다.
- **해결은 하드코딩이 아니라 탐지다.** 본작업 전 preflight 스크립트로 '유효 인증 HOME'을 찾는다:
  - Claude: `scripts/preflight_claude_auth.sh "<후보HOME들>"` → `PRIMARY_READY_HOME` 획득 후 `env HOME=<그 값> claude ...`
  - Codex: `scripts/preflight_codex_home.sh "<후보CODEX_HOME들>"` → 유효 `CODEX_HOME` 획득
- `claude -p` 는 exit 0 이어도 JSON 내부 `is_error=true`/`Not logged in` 일 수 있으므로 내부 필드를 파싱한다.
- 후보 목록은 배포 환경마다 다르므로 인자/환경변수로 주입한다.
- 공식 override: Claude=`CLAUDE_CONFIG_DIR`(Linux/Win 자격증명 디렉터리), Codex=`codex exec` 한정 `CODEX_API_KEY` 인라인. Linux 는 `~/.claude/.credentials.json`·`$CODEX_HOME/auth.json` 가 HOME/CODEX_HOME 기준 확장되므로 preflight 의 후보 탐지로 충분.

## J. Agent Card → CLI 호출 매핑
| Agent Card 필드 | 사용처 |
|---|---|
| `agent_os` | Claude Code / Codex CLI 분기 |
| `workspace.runtime` | 사전 명령 선택 (`unknown`이면 §B 보고) |
| `workspace.serve.command` | Plan A 서버 기동 명령 (`null`이면 서버 없음) |
| `workspace.serve.*_config_path` | host:port 를 **런타임 조립**할 설정 경로 (포트 하드코딩 금지) |
| `workspace.codex.sandbox` | Codex `-s` (`unknown`이면 §B 보고) |
| `workspace.codex.model` | Codex `-m`. `"default"`/`null` → `-m` 생략 |
| `skills[].invoke.command` | CLI 로 감싸 실행 |
| `skills[].verification` | self-report 불신 검증 방법 |
| `skills[].allowed_tools` / `max_turns` | Claude `--allowedTools` / `--max-turns` (Codex 무시) |
| `skills[].invoke.timeout_seconds` | `terminal(timeout=...)` |

## K. A2A TaskState 결과 모델 (제어 성공/실패 정본)
> 이 스킬은 A2A-inspired(§A). 제어 결과는 binary success/failure 가 아니라 아래 **9-state** 로 분류해 보고한다.
> 목적: "어느 단계에서 깨졌는가"(시작 전 거부 vs 인증 미준비 vs 시작 후 실패 vs 미검증)를 Hermes 가 구분해 **처방을 고른다**.
> (A2A 공식 enum 중 `rejected`/`auth-required` 는 A2A-inspired 확장 — §A 의 "정식 스펙 아님" 선언과 정합.)
> **계약 식별자**: `model: a2a-taskstate-v1` — producer(agent-card `statusReporting.model`)와 consumer(이 모델)가 이 문자열로 정합한다.

| finality | state | 제어 의미 |
|---|---|---|
| active | `submitted` → `working` | 위임 접수(보통 즉시 `working` 으로 흡수 — 단독 기록 불요) → 실제 작업 중 |
| interrupted | `auth-required` | preflight HOME/인증 미준비 — 작업 **시작 전** 차단 |
| interrupted | `input-required` | 서브에이전트가 추가정보 필요해 멈춤(입력 후 `working` 복귀) |
| terminal | `completed` | **검증된 비즈니스 결과**(단순 exit 0 아님 — §E). ⟺ 기존 `primary_success` |
| terminal | `failed` | 작업이 **시작된 뒤** 에러(budget 소진[claude max_turns / codex timeout]·출력에러·health 실패 등) |
| terminal | `rejected` | 작업이 **시작조차 거부**(정체성·정책·triage 차단) |
| terminal | `canceled` | 명시적 중단 |
| 제어불가 | `unknown` | 판정 불가 → 재질의/fallback(추측 금지). §B 와 동치 |

규칙:
- **terminal 은 final**: `completed`/`failed`/`rejected`/`canceled` 도달 후 자동 재시도·재개 금지(=`retry_allowed=false`). 교정은 **새 control_attempt** 로(§primary-fallback-policy 실패 시 HITL).
- **state → failure_code**: `failed`/`rejected` 의 구체 코드는 `references/failure-codes.md`(상태축 컬럼)에서 1:N 매핑.
- **control-plane vs data-plane 분리**: state 전이(제어가 돌았나)는 `parse_*` 로, `completed` 판정(결과물이 맞나)은 `verify_*` 산출물 검증으로 정한다. 둘은 별개 축이다.
- 호출별 원장 기록 계약(`task_state`/`finality`/`control_plane`/`data_plane`/`failure_code`/`retry_allowed` …)은 `references/primary-fallback-policy.md` §원장.
- **budget 축 (additive)**: 위 원장에 `task_grade`·budget 배분/실측·`budget_outcome` 를 함께 기록한다(필드 추가만 — 계약식별자 `a2a-taskstate-v1` 유지, rename 아님). **budget 단위·필드명은 스킬별**: claude=`max_turns_allocated`/`max_turns_used`(turns via `--max-turns`), codex=`timeout_allocated_s`/`wall_seconds_used`(seconds via `timeout`). grade→예산 배분·discovery 합승 핸드셰이크 정본: 각 스킬 `references/*-budget-grades.md`(claude `turn-budget-grades.md` / codex `timeout-budget-grades.md`).
