---
name: claude-code-control
description: Use when an orchestrator must control a real Claude Code CLI sub-agent in another workspace. Reads the target agent-card.json, runs an auth/HOME preflight (no hardcoded paths), proves workspace context with a read-only discovery call, delegates bounded `claude -p` work with the correct workdir, and verifies results without trusting self-reports. Never silently substitutes a failed primary control with Hermes-direct execution or delegate_task.
version: 4.3.0
author: AhnSangHun
license: MIT
platforms: [linux, wsl]
metadata:
  hermes:
    tags: [claude-code, subagent, terminal, orchestration, agent-card]
    category: autonomous-ai-agents
    requires_toolsets: [terminal, file]
    related_skills: [codex-cli-control]
---

# Claude Code Control — 진짜 Claude Code 서브에이전트 제어

오케스트레이터가 다른 워크스페이스에 설치된 Claude Code 를 **실제 로컬 CLI 서브에이전트**로
호출·제어하기 위한 스킬이다. 직접 구현자처럼 조용히 일하지 않는다.

> **결정론 로직은 `scripts/` 와 `references/` 로 분리**되어 있다(하네스 분리). 본 문서는 판단·프롬프트 등
> 확률론 부분과 절차 흐름만 담는다. 모든 경로·HOME 은 런타임 값으로 다룬다(하드코딩 금지).
> - 공통 원칙(+A2A TaskState 결과 모델 §K): `skill_view("claude-code-control", "references/common-rules.md")`
> - primary/fallback 무결성 + 원장(9-field): `skill_view("claude-code-control", "references/primary-fallback-policy.md")`
> - 실패 분류(상태축): `skill_view("claude-code-control", "references/failure-codes.md")`
> - 사전위임 triage(무엇을 위임할지): `skill_view("claude-code-control", "references/delegation-triage-gate.md")`
> - turn 예산·grade 위임(scope⊥budget·핸드셰이크·원장): `skill_view("claude-code-control", "references/turn-budget-grades.md")`
> - Gateway 지연 진단(Slack 응답지연 패턴): `skill_view("claude-code-control", "references/gateway-latency-diagnosis.md")`
> - E2E 실전 교훈(계량 증거 + 복구 패턴): `skill_view("claude-code-control", "references/e2e-lessons-learned.md")`

## 1. When to Use
사용한다: 사용자가 다른 워크스페이스의 Claude Code 에게 작업을 지시할 때 / 그 워크스페이스가 자신의
`${CONTEXT_FILE}`·`agent-card.json` 을 실제로 인지하는지 검증해야 할 때 / 그 워크스페이스의 서버 기동·bounded
script 실행을 Claude Code 에게 맡기고 Hermes 가 검수할 때.

사용하지 않는다: Codex CLI 워크스페이스 제어(→ `codex-cli-control`) / 오케스트레이터 내부 병렬 추론
(→ `delegate_task`; 이건 Claude Code 제어가 아니다) / 단순 파일 읽기·검증(→ 직접 `read_file`·`terminal`).

## 2. 절대 규칙 (요약 — 상세는 references)
1. **workdir** 를 항상 명시한다(`cwd` 아님). 틀리면 `${CONTEXT_FILE}` 자동 로드가 깨진다.
2. 본작업 전 **preflight 로 유효 인증 HOME 을 탐지**한다(아래 §3-B). HOME 을 추측해 박지 않는다.
3. **preflight → discovery → action** 순서를 건너뛰지 않는다.
4. **조용한 primary 대체 금지** — `references/primary-fallback-policy.md` 를 따른다. 직접실행/`delegate_task`
   를 primary 성공으로 집계하지 않는다.
5. `null`/`unknown` Card 필드는 4-state sentinel(§common-rules B)로 보고 후 판단한다.

## 3. 표준 실행 흐름
`${HERMES_SKILL_DIR}` = 이 스킬 폴더 절대경로(Hermes 런타임이 치환하는 공식 변수). `${WS}` = 대상 워크스페이스 루트(호출자/Card 에서 결정하는 논리 placeholder — 실제 경로로 치환).
`${CONTEXT_FILE}` = Card `workspace.context_file` 값(런타임에 읽어 치환 — 파일명을 스킬에 하드코딩하지 않는다).

### Step A — Agent Card 직접 읽기
`read_file("${WS}/agent-card.json")` → `manifestType`, `agent_os=="claude-code"`,
`workspace.context_file` 을 `${CONTEXT_FILE}` 로 고정(Claude 가 자동 로드하는 표준 컨텍스트 파일이어야 한다), `skills[].{id,examples,invoke.command,verification}` 확인.
`null`/`unknown` 은 §common-rules B 로 처리.

### Step B — auth/HOME preflight (결정론, D1)
```text
terminal(command="bash ${HERMES_SKILL_DIR}/scripts/preflight_claude_auth.sh <후보HOME들>", workdir="${WS}", timeout=60)
```
- 후보 HOME 들은 배포 환경에 맞게 인자/환경변수(`CLAUDE_HOME_CANDIDATES`)로 준다.
- 출력 `PRIMARY_READY_HOME=<값>` 을 이후 모든 호출의 `env HOME=<값> claude ...` 에 사용한다.
- 실패(exit 3/4)면 `CLAUDE_AUTH_HOME_MISMATCH`/`CLAUDE_CLI_NOT_FOUND` 로 보고하고 중단(반복 호출 금지).

### Step C — read-only discovery call (정체성 증명)
```text
terminal(
  command="env HOME=${PRIMARY_READY_HOME} claude -p '너는 이 워크스페이스의 Claude Code다. 파일 수정/명령 실행 금지. 네 워크스페이스 컨텍스트 파일과 agent-card.json만 읽고 {workspace_name, agent_os, context_file, available_skill_ids, verification, grade_recommended, planned_steps, needs_hitl, rationale} JSON을 반환하라. grade_recommended는 이번 작업 난이도의 self-추천이다(S=정체성증명·L0=완성블럭기동/단일명령·L1=단일파일patch+명령1·L2=산출1단계(recipe/compose/조판)·L3=진단+원인분리 runtime·L4=전략수립+HITL루프; 모르면 unknown).' --allowedTools 'Read' --max-turns 8 --output-format json",
  workdir="${WS}", timeout=120)
```
결과는 `scripts/parse_claude_json.py` 로 검증(`is_error=false`). `workspace_name`/`agent_os`/`context_file`
가 대상과 일치하고 'Not logged in'·엉뚱한 워크스페이스 언급이 없어야 통과.

### Step D — bounded action delegation (확률론 P1)
discovery 통과 후에만 실제 작업을 하달한다. 프롬프트 골격:
```text
너는 <workspace> Claude Code다.
모드: <Runtime | Builder | Eval Run>
먼저 워크스페이스 컨텍스트 파일과 agent-card.json을 따른다.
이번 작업 범위: <구체 작업>
금지: <삭제/재개발/범위 밖>
완료 보고: 실행 명령, 생성/수정 파일, 검증 결과, blocked 여부. 모르는 값은 unknown.
```
호출 예:
```text
terminal(command="env HOME=${PRIMARY_READY_HOME} claude -p '<bounded prompt>' --allowedTools 'Read,Bash,Edit,Write' --max-turns <grade→배분값> --output-format json", workdir="${WS}", timeout=600)
# --max-turns 는 매직상수 아님 — discovery 의 grade_recommended 를 Hermes 가 재평가(grade_assigned)해
# references/turn-budget-grades.md §2 표에서 배분한 max_turns_allocated 값(하한 ≥6). L3/L4 는 background+watchdog.
```
주의: `--dangerously-skip-permissions` 는 격리 워크스페이스 + 명령형 지시 + 삭제 경계 명확 시에만.
read-only discovery 에는 쓰지 않는다. `--max-turns` 는 필수.

### Step E — 결과 검증 (결정론, D2·D3)
- 결과 JSON: `python3 ${HERMES_SKILL_DIR}/scripts/parse_claude_json.py <결과파일>` (exit 0 확인).
- 서버: `bash ${HERMES_SKILL_DIR}/scripts/verify_server.sh <host> <port> [health] [models]` (host:port 는 config 조립).
- 경로 drift 의심 시: `python3 ${HERMES_SKILL_DIR}/scripts/card_drift_check.py "${WS}/agent-card.json" "${WS}"`.
- Card 의 `skills[].verification` 우선. self-report 불신(§common-rules E).

## 4. 서버 기동 정책 (요약)
- **증명 단계**: Claude 에게 runtime 준비상태(serve.command, config의 host/port, /health 검증법, 위험요소)만
  read-only 로 보고시킨다(포트는 config 값만, 추측 금지).
- **실행 단계 옵션 A(권장)**: Claude 가 산출한 명령을 Hermes 가 card 와 대조 후, long-lived 서버는 Hermes
  `terminal(background=true)` 로 잡는다. 보고에 "Claude discovery/validation: passed, server owner: Hermes" 명시.
- **옵션 B(strict demo)**: 사용자가 "Claude 가 직접 띄우는 모습"을 요구할 때만. print-mode 종료 대비
  `nohup`/`setsid`+로그 사용을 Claude 에게 명시시키고, Hermes 가 pid/log/health 직접 확인.
- background 출력 0줄(`BACKGROUND_BUFFERING`)이면 foreground+충분한 timeout 으로 전환.

## 5. Pitfalls (상세: `references/failure-codes.md` 상태축 + `references/delegation-triage-gate.md`)
스킬 미로드 / `cwd` 사용 / HOME 추측 하드코딩 / JSON wrapper 만 보고 성공처리(`completed`≠exit0) / discovery 생략 /
**직접실행·delegate_task 를 primary 성공으로 포장** / 포트 하드코딩 / print-mode 로 daemon 직접 기동 / self-report 맹신 /
**결정론적 배치·복합 다단계 작업을 단일 `claude -p` 에 위임**(turn 소진 — §5.1 게이트 통과 필수). /
**Claude의 turn을 파일 탐색에 낭비** — multi-step 분석·조사 전 Hermes가 사전에 target 파일을 `read_file`로 직접 읽고, 그 구체 데이터(CSV 스냅샷·config 발췌·문서 핵심)를 prompt context에 삽입하라. Claude는 discovery 대신 분석에 집중하고, `--max-turns` 소진으로 인한 타임아웃을 방지한다 (G5: prompt-fed-context). 1회 실패 시 2회차에 바로 적용.

### 5.1 위임 가능성 판단 → 사전위임 triage 게이트 (정본 1곳)
무엇을 위임할지의 판단(결정론 배치 G1 / 멀티라인 CSV `QUOTE_ALL` G2 / 외부 import 사전확인 G3 / 복합 다단계 분할·체크포인트 G4)은
**`references/delegation-triage-gate.md` 한 곳**에 상세화돼 있다. 위임 전 전수 통과한다(불통 → `rejected`/`auth-required` 로 앞단 차단, common-rules §K).
**G4 강화**: 단일 `claude -p` 호출에 2개 이상의 **이질적** 결정론 작업을 묶지 마라(복합 다단계 위임 시 15~27 turn 소비 — `references/e2e-lessons-learned.md` §1 실측). 단, 단일 작업의 turn 예산은 **줄이는 게 아니라** grade→예산표(`references/turn-budget-grades.md` §2, 하한 ≥6)로 충분히 배분한다(scope⊥budget). 추론무거움 L4(전략+HITL)는 억지 원자화하지 않는다(§triage L4 예외). 작업 사이 체크포인트를 Hermes가 검증 후 다음 작업으로 진행한다.
배치를 Hermes 가 직접 실행할 때의 스크립트 레시피(순차 urllib·`QUOTE_ALL`·파일 진행로깅)는 `references/batch-collection-pattern.md`.

### Relay(전화교환원) 패턴 — 사용자↔서브에이전트 실시간 중개

사용자가 "전화교환원이 되어줘"라고 요청할 때, Hermes는 직접 분석·판단하지 않고
**사용자 지시를 서브에이전트에 전달하고, 응답을 사용자에게 relay**하는 중개자로 전환한다.

절차:
1. `preflight → discovery`로 워크스페이스 연결 (동일 세션 내에서는 1회만, 재사용)
2. **G5 prompt-fed-context 사전적용 (필수)**: `claude -p` 호출 전에 필요한 파일들을 Hermes가 `read_file`로 직접 읽고 prompt에 삽입한다. Claude가 파일 탐색에 turn을 낭비하는 것을 방지. 특히 CSV 스냅샷·config 발췌·문서 핵심 본문을 사전에 주입.
3. **relay 호출 방식 선택** — 예상 소요시간 기준:
   - **2분 이하 예상**: foreground `terminal()` + upfront 알림만 ("🔁 작업 중...")
   - **3분 이상 예상**: `terminal(background=true, watch_patterns=['iteration', 'Working'], notify_on_complete=true)` + 진행 후크 중계
4. **진행 후크 패턴 (3분 이상 relay)**: 사용자 메시지를 bounded prompt로 감싸 `claude -p`를 background로 실행하고, `watch_patterns`로 아래 패턴을 감시하여 중간 진행상황을 Slack에 중계:
   ```
   [10:42] 🔁 02 작업 시작... (예상 3~5분, iteration 감시 중)
   [10:44] ⏳ 02 진행: 2분 경과, iter 4/90  ← watch_patterns="iteration" hit 시 자동 Slack 전송
   [10:47] ⏳ 02 진행: 5분 경과, iter 7/90
   [10:55] 📬 02 응답 도착 — relay 시작   ← notify_on_complete 시 Slack 전송
   ```
   → 사용자가 "iteration이 올라가네 → 정상", "iteration 멈췄네 → hang 의심 → 정지" 판단 가능.
5. `process(action='wait')`로 완료 대기 후 응답을 사용자에게 요약 relay. 복잡한 표·분석은 그대로 전달하고, 간단한 응답은 핵심만
6. 사용자가 "일시정지"·"전부 정지"하면 즉시 `process(action='kill')` → relay 중단 → Ouroboros pending 상태로 대기
7. 사용자가 "인지부채 해소"·"풀이해달라"고 하면, relay prompt에 "사용자가 인지부채를 느낀다. 구체적 예시로 풀이하라"는 지시를 추가

Pitfalls:
- relay 중 Hermes가 직접 분석·판단·제안을 끼워넣지 않는다 (사용자가 요청한 relay 외)
- 사용자 지시를 번역·요약하지 말고 원문 그대로 전달. 단 relay prompt에 bounded 제약만 추가
- **Dead Air — 진행 알림만으로 부족**: 단일 "작업 중... (예상 3~5분)" 메시지는 예상보다 relay가 길어질 때(13분) 사용자가 "hang인가?" 의심하게 만든다. 3분 이상 relay는 반드시 `terminal(background=true, watch_patterns=['iteration'])`로 진행 후크를 중계할 것 — iteration이 올라가면 정상, 멈추면 hang.
- **Dead Air — streaming=false 증폭**: `config.yaml`에서 `streaming: enabled: false`면 Hermes의 모든 중간 출력이 Slack에 표시되지 않아 Dead Air가 구조적으로 증폭된다. 게이트웨이는 정상이지만 사용자는 "통신 단절"로 오인. `streaming: enabled: true`로 변경하면 도구 호출 단위로 Slack에 실시간 표시되어 근본적 Dead Air 해소.
- **게이트웨이 로그 자기진단 불신**: 게이트웨이 로그의 "Sending response"는 Slack API 호출 성공만 의미. 실제 사용자 클라이언트 렌더링 여부는 보장하지 않음. Slack 대화내역(쓰레드)과 게이트웨이 로그를 교차검증해야 실제 사용자 체감을 파악 가능. 게이트웨이 로그만 보고 "정상" 판단하지 말 것.
- 동일 세션에서 여러 번 relay 시 preflight/discovery는 재사용, 프롬프트만 새로 발행
- **Turn exhaustion 후 파일 확인**: `claude -p`가 `error_max_turns` 또는 timeout으로 종료되어도 파일이 부분 생성되었을 수 있다. 타임아웃 직후 반드시 `search_files`로 대상 디렉터리를 확인하고, partial success면 재시도하지 않고 생성된 파일을 먼저 검증한다.
- **Partial artifacts + missing response 복구**: 산출물(subset CSV, matrix, plan 등)은 생성됐지만 response/plan 작성 전에 turn이 끝났다면, 무조건 재시도하지 말고 Hermes가 직접 산출물을 읽어 row count·schema·분포 같은 결정론 검증을 수행한다. 산출물이 SDD 요구를 충족하면 누락된 response/plan은 `Hermes recovery record`로 명시해 보완하고, Claude self-report가 아니라 검증한 파일 경로·검증값·timeout 사실을 기록한다. 단, 코드 변경/외부 side effect 성공은 self-report로 보완하지 말고 반드시 실제 파일·명령 결과로 검증한다.
- **`process(action='wait')` timeout 60초 clamp**: Hermes의 `process(action='wait', timeout=N)`은 N이 600이어도 60초로 clamp된다. 장시간(10분+) background 작업(대량 LLM 호출·DB 수집·빌드 등)을 `wait` 한 번으로 완료 대기할 수 없으므로, **`poll` 반복 패턴**을 사용하라: `process(action='poll')`로 uptime_seconds 확인 → 필요 시 `process(action='log')`로 출력 확인 → 충분한 간격으로 재시도. `terminal(background=true, notify_on_complete=true)`와 병행하면 완료 시 자동 알림을 받으므로 수동 poll 횟수를 줄일 수 있다. 이 clamp는 claude-code에만 해당하는 것이 아니라 모든 background `terminal()`에 적용되는 Hermes 런타임 동작이다.
- **Background `uv run` workdir 불안정 (WSL)**: `terminal(background=true, workdir=<path>)`로 `uv run python -m app.serve`를 실행할 때, workdir가 background subshell에서 제대로 적용되지 않아 `ModuleNotFoundError: No module named 'app'`가 발생할 수 있다. foreground `terminal()`에서는 정상 작동. **해결**: 명령어 앞에 `cd <workdir> && `를 명시한다. 예: `terminal(background=true, command="cd /path/to/ws && uv run python -m app.serve 2>&1")`. shell script wrapper(`bash /tmp/script.sh`)로도 해결 가능.
- **WSL Docker Desktop — CIFS 마운트 전파 pitfall**: WSL에서 Docker Desktop을 쓸 때, CIFS NAS 마운트포인트(`/mnt/llm_model` 등)를 `docker compose` 볼륨으로 직접 bind하면 컨테이너 안에서 빈 디렉토리로 보인다(별도 WSL VM의 private propagation). **진단**: `docker run --rm -v <mountpoint>:<container>:ro <image> ls <container>` → 빈 디렉토리면 pitfall 확정. **해결**: 마운트포인트 자식 디렉토리(`<mountpoint>/Model:/app/models/Model:ro`)를 bind한다 — child-traverse로 실제 내용이 보인다. compose 경로와 yaml model path 정합 유지 필수. 상세: `references/e2e-lessons-learned.md` §4.

### 서브에이전트 상담(consultation) 패턴 — `delegate_task` 대체 금지
각 번호 워크스페이스가 자체 `${CONTEXT_FILE}`·`agent-card.json` 을 가진 구조에서는, "서브에이전트 의견 수집"이 단순 추론 위임처럼 보여도 Hermes `delegate_task` 로 대체하지 않는다. 01/02 Claude Code 워크스페이스의 근거 코멘트·read-only evidence consultant·SDD 검토는 이 스킬의 `preflight → discovery → claude -p` 흐름으로 실제 워크스페이스 CLI 를 호출한다. `delegate_task` Sonnet 서브에이전트는 해당 워크스페이스의 인증/HOME/context file/agent-card 를 증명하지 못하므로 primary 상담으로 집계하지 않는다.

## 6. Verification Checklist
- [ ] 이 스킬 로드됨
- [ ] `agent-card.json` 직접 읽음, `agent_os="claude-code"` 확인 / `context_file` 을 `${CONTEXT_FILE}` 로 확정
- [ ] `null`/`unknown` 을 4-state 로 보고/판단
- [ ] preflight 로 `PRIMARY_READY_HOME` 확정 (HOME 하드코딩 안 함)
- [ ] `workdir` 가 대상 워크스페이스 루트
- [ ] read-only discovery 통과 (`parse_claude_json.py` exit 0)
- [ ] action call 에 `--max-turns` + 최소 `--allowedTools`
- [ ] 결과를 Hermes 가 직접 검증 (scripts)
- [ ] 결과를 A2A 원장으로 기록: `task_state`(9-state)·`finality`·`control_plane`/`data_plane`·`failure_code`·`retry_allowed` (common-rules §K, primary-fallback-policy)
- [ ] primary/fallback 을 원장에 기록, fallback 을 성공으로 집계하지 않음
