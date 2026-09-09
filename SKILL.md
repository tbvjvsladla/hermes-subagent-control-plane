---
name: codex-cli-control
description: Use when an orchestrator must control a real Codex CLI sub-agent in another workspace. Reads the target agent-card.json, runs a CODEX_HOME preflight (no hardcoded paths), proves the card-declared workspace context file with a read-only discovery smoke, invokes `codex exec` with -C/sandbox/model(4-state)/-o output capture, and verifies artifacts without trusting self-reports. Never silently substitutes a failed primary control with Hermes-direct execution or delegate_task.
version: 4.3.0
author: AhnSangHun
license: MIT
platforms: [linux, wsl]
metadata:
  hermes:
    tags: [codex, subagent, terminal, orchestration, document-conversion, agent-card]
    category: autonomous-ai-agents
    requires_toolsets: [terminal, file]
    related_skills: [claude-code-control]
---

# Codex CLI Control — 진짜 Codex CLI 서브에이전트 제어

오케스트레이터가 다른 워크스페이스의 Codex CLI 를 "직접 처리한 것처럼" 대체하지 않고,
**실제 Codex CLI 서브에이전트**로 제어하기 위한 스킬이다.

> **결정론 로직은 `scripts/`·`references/` 로 분리**되어 있다. 본 문서는 판단·프롬프트·절차 흐름만 담는다.
> 경로·CODEX_HOME 은 런타임 값으로 다룬다(하드코딩 금지).
> - 공통 원칙(+A2A TaskState 결과 모델 §K): `skill_view("codex-cli-control", "references/common-rules.md")`
> - primary/fallback 무결성 + 원장(9-field): `skill_view("codex-cli-control", "references/primary-fallback-policy.md")`
> - 실패 분류(상태축): `skill_view("codex-cli-control", "references/failure-codes.md")`
> - 사전위임 triage(무엇을 위임할지): `skill_view("codex-cli-control", "references/delegation-triage-gate.md")`
> - timeout 예산·grade 위임(scope⊥timeout·핸드셰이크·원장): `skill_view("codex-cli-control", "references/timeout-budget-grades.md")`

## 1. When to Use
사용한다: 대상 Codex 워크스페이스에 승인된 SDD 실행을 맡길 때 / 보고서 조판·metric 분석·이미지 자산
등 그 워크스페이스 내부 skill 을 Codex 에게 수행시키고 Hermes 가 검증할 때 / "오케스트레이터 → Codex CLI
서브에이전트 제어"가 실제 동작했는지 증명해야 할 때.

사용하지 않는다: Claude Code 워크스페이스 제어(→ `claude-code-control`) / 단순 파일 읽기·검증(→ 직접
`read_file`·`terminal`) / 질문형 요청("방법이 뭐야?")엔 실행 말고 절차만 설명.

## 2. 절대 규칙 (요약 — 상세는 references)
1. **`-C <workspace>`** 와 Hermes **`workdir`** 를 함께 명시한다(`cwd` 아님).
2. 본작업 전 **preflight 로 유효 CODEX_HOME 을 탐지**한다(§3-B). 추측해 박지 않는다.
3. **preflight → read-only discovery smoke → action** 순서를 건너뛰지 않는다.
4. **조용한 primary 대체 금지** — `references/primary-fallback-policy.md`. 직접실행/`delegate_task` 를 primary 성공으로 집계 금지.
5. `sandbox=unknown`/`model=null` 은 4-state(§common-rules B)로 보고 후 판단. 모델 버전 추측 금지.

## 3. 표준 실행 흐름
`${HERMES_SKILL_DIR}` = 이 스킬 폴더 절대경로(Hermes 런타임이 치환하는 공식 변수). `${WS}` = 대상 워크스페이스 루트(호출자/Card 에서 결정하는 논리 placeholder — 실제 경로로 치환).
`${CONTEXT_FILE}` = Card `workspace.context_file` 값(런타임에 읽어 치환 — 파일명을 스킬에 하드코딩하지 않는다).

### Step A — Agent Card 직접 읽기
`read_file("${WS}/agent-card.json")` → `agent_os=="codex-cli"`, `workspace.context_file` 을 `${CONTEXT_FILE}` 로 고정
(Codex 가 실제로 자동 로드하는 표준 컨텍스트 파일이어야 한다; `CODEX.md` 면 자동 로드되지 않으므로 위험 보고), `workspace.codex.{sandbox,model}`(4-state), `skills[].{invoke.command,timeout_seconds,verification}` 확인.

### Step B — CODEX_HOME preflight (결정론, D1)
```text
terminal(command="bash ${HERMES_SKILL_DIR}/scripts/preflight_codex_home.sh <후보CODEX_HOME들>", workdir="${WS}", timeout=60)
```
출력 `CODEX_HOME_READY=<값>` 을 이후 모든 호출의 `CODEX_HOME=<값> codex exec ...` 에 쓴다.
실패(exit 3/4) → `CODEX_AUTH_HOME_MISMATCH`/`CODEX_CLI_NOT_FOUND` 보고 후 중단.

### Step C — read-only discovery smoke (정체성 증명)
```text
OUT=<임시경로>/codex_discovery.txt
terminal(
  command="CODEX_HOME=${CODEX_HOME_READY} codex exec -C ${WS} -s read-only -o $OUT 'Read your workspace context file and agent-card.json only. Reply with identity, manifest name, agent_os, context_file, sandbox, model, confirm no file changes, and grade_recommended(self-rated task difficulty: S=identity-proof, L0=launch prebuilt block/single cmd, L1=single-file patch+1 cmd, L2=one build step(recipe/report), L3=diagnose+root-cause runtime, L4=strategy+HITL loop; unknown if unsure)/planned_steps/needs_hitl/rationale.'",
  workdir="${WS}", timeout=300)   # S 예산 120~300 (선택: --output-schema 로 grade JSON 강제)
read_file("$OUT")
```
통과: exit 0, Codex 가 대상 정체성·`agent_os=codex-cli`·`context_file=${CONTEXT_FILE}`·sandbox·model 을 Card 와
일치하게 보고, `git status --short` 로 파일 미변경 확인(`scripts/verify_artifacts.sh ${WS}`).

### Step D — bounded action (확률론 P1)
Card skill 선택 후:
```text
CODEX_HOME=${CODEX_HOME_READY} codex exec \
  -C ${WS} \
  -s <workspace.codex.sandbox> \
  [-m <workspace.codex.model>] \      # "default"/null → -m 생략
  -o <임시경로>/codex_result.txt \
  '<skills[].invoke.command + 사용자 범위 + 요구 검증을 합친 프롬프트>'
```
모델: `default` → `-m` 생략 / `null` → 생략하되 미확정 보고 / 명시명 → `-m <model>`. sandbox 는 Card 값,
`unknown` 이면 보고. 디버깅 필요 시 `--json` 추가(JSONL).

**timeout(budget)**: codex 는 `--max-turns` 가 없다 — budget 은 Hermes `terminal(timeout=…)` 뿐이다. discovery 의
`grade_recommended` 를 재평가한 `grade_assigned` → `references/timeout-budget-grades.md` §2 표에서 `timeout_allocated_s`
배분(매직상수 아님). L3/L4 는 `background=true` + log-watch + runtime 상태 확인(선언된 경우) + Hermes 사후 검증을 쓴다. 실패 시 timeout 을 **줄이지
말고 늘린다**(§failure-codes `TIMEOUT_KILLED`).

### Step E — 결과 검증 (결정론, D2·D3)
- 결과: `python3 ${HERMES_SKILL_DIR}/scripts/parse_codex_output.py <결과파일>` (exit 0 확인).
- 산출물: `bash ${HERMES_SKILL_DIR}/scripts/verify_artifacts.sh ${WS} <subpath> "<expected_glob>..."`.
- 경로 drift 의심: `python3 ${HERMES_SKILL_DIR}/scripts/card_drift_check.py "${WS}/agent-card.json" "${WS}"`.
- Card `skills[].verification` 우선. self-report 불신(§common-rules E).

## 4. 작업별 게이트 (요약)
- 후처리 필드(LLM/Agent OS)가 있는 스킬: **결정론 스크립트 성공 ≠ 완료** — `common-rules §E` 도착점 규칙 적용(후처리 필드 검증 전 done 금지).
- 이미지 자산: Card 의 `background`/`notify_on_complete` 반영. 승인 안 된 설치 지시 금지.

## 5. Claude Code ↔ Codex CLI 차이 (요약)
| 항목 | Claude Code | Codex CLI |
|---|---|---|
| One-shot | `claude -p` | `codex exec` |
| `-p` 의미 | print mode | profile (print mode 아님) |
| 컨텍스트 | Card `context_file`(Claude 표준) | Card `context_file`(Codex 표준). `CODEX.md` 는 자동로드 아님 |
| 권한/출력 | `--allowedTools`,`--max-turns`,`--output-format json` | `-s read-only\|workspace-write\|danger-full-access`, `-o`, `--json` |
| 인증 격리 | preflight 로 유효 HOME 탐지 | preflight 로 유효 `CODEX_HOME` 탐지 |

## 6. Pitfalls (상세는 `references/failure-codes.md`)
`cwd` 사용 / `-C` 생략 / CODEX_HOME 추측 하드코딩 / `CODEX.md` 의존 / 모델·sandbox 추측 박기 /
deterministic 성공(exit0)을 `completed` 로 착각(§K — data-plane 검증 전 미완료) / 복합 다단계를 단일 `codex exec` 에 위임(→ `references/delegation-triage-gate.md` G4) /
산출물 미확인 / **직접실행·delegate_task 를 primary 성공으로 포장** /
승인 안 된 설치 지시 / **MCP tool 호출이 "user cancelled MCP tool call"로 취소될 때** — 사용자 Codex 설정 파일(`${CODEX_HOME}` 하위 `config.toml`)에 해당 MCP 서버의 tools 블록별로 `approval_mode = "approve"`가 설정되어 있는지 확인. Ouroboros MCP는 이 설정이 있지만 openai-image 등 다른 MCP는 누락되었을 수 있다. `[mcp_servers.<name>.tools.<tool>] approval_mode = "approve"`.

### 전송 계층 오류
discovery/action에서 connection refused, stream disconnected 등 provider 전송 오류가 나면, proxy·패키지·서비스를 자동 설치하거나 기동하지 않는다. 출력 원문과 `CODEX_TRANSPORT_UNREACHABLE` 상태를 기록하고 사용자에게 보고한다.

### sandbox dot-directory read-only (workspace-write 필수 pitfall)

`codex exec -s workspace-write` 는 워크스페이스 안이라도 **dot-directory 를 read-only 로 마운트**한다.
`.agents/`, `.git/`, `.claude/` 등 점으로 시작하는 디렉토리 전부가 대상이다.

```text
증상  /bin/bash: line 1: .agents/foo.md: Read-only file system
      .git/index.lock: Read-only file system
      (Codex 가 "writing outside of the project; rejected by user approval settings" 로 보고하기도 한다)

실증  동일 세션·동일 sandbox 에서
        printf x > temp/probe.txt     -> exit 0   (일반 디렉토리 OK)
        printf x > .agents/probe.txt  -> exit 1   Read-only file system
```

**해소**: 쓰기가 필요한 dot-directory 를 `--add-dir` 로 명시한다.

```text
codex exec -C ${WS} -s workspace-write \
  --add-dir ${WS}/.agents \      # 헌법·rules·templates·skills 수정 시
  --add-dir ${WS}/.git \         # stage·commit 시 (index.lock 쓰기 필요)
  -o ${OUT} '<prompt>'
```

**비용**: 이걸 모르면 서브에이전트가 작업을 시작했다가 전량 실패한다.
실측 사례 — 헌법 17파일 개정 위임에서 13개가 `.agents/` 하위라 **314,784 토큰을 소모하고
산출물 0건**으로 종료됐다(91분 손실). 별도 사례로 commit 위임이 `.git/index.lock` 쓰기 실패로
staged 0건 종료됐다. 둘 다 `--add-dir` 한 줄로 해소됐다.

**preflight 권고**: 대상 워크스페이스의 쓰기 경로에 dot-directory 가 포함되면
Step B preflight 단계에서 `--add-dir` 목록을 미리 확정한다. 승인 범위나 Card 의
`skills[].invoke.command` 에서 `.` 으로 시작하는 경로를 grep 하면 된다.

**진단 시 배제할 것**: OS 권한(`ls -ld`), symlink 여부, `.gitignore`, `trust_level` 은
이 증상과 무관하다. 전부 정상인데도 실패하면 dot-directory 제약을 의심한다.

### 보고서 아키텍처 다이어그램 품질

Codex가 생성하는 보고서의 시스템 아키텍처 다이어그램은 **스스로 발명하게 두면 형편없다** (사용자 피드백: "너무 후지다"). 관련 워크스페이스의 README.md에 이미 정성 들여 작성된 Mermaid/ASCII 아키텍처 다이어그램이 있다면, **반드시 Codex prompt에 원본 다이어그램을 명시적으로 포함**시켜라.

절차:
1. 관련 워크스페이스의 README.md를 Hermes가 먼저 `read_file`로 읽는다.
2. README에서 Mermaid flowchart나 아키텍처 ASCII 도식을 추출한다.
3. Codex prompt에 다이어그램 원본과 "이 스타일을 SVG로 변환해 보고서에 인라인 삽입하라"는 지시를 포함한다.
4. `mmdc`(mermaid-cli)가 Chromium sandbox 제한으로 실패할 수 있으니 Python fallback SVG 생성도 허용한다.

안티패턴: Codex에게 "시스템 아키텍처 다이어그램을 추가해"라고만 하고 신경 쓰지 않으면, Codex는 외형만 갖춘 저품질 다이어그램이나 전혀 다른 구조의 그림을 생성한다.

### Relay(전화교환원) 패턴 — 사용자↔Codex 서브에이전트 실시간 중개

사용자가 "전화교환원이 되어줘"라고 요청할 때, Hermes는 직접 분석·판단하지 않고
**사용자 지시를 Codex CLI 서브에이전트에 전달하고, 응답을 사용자에게 relay**하는 중개자로 전환한다.

절차:
1. `preflight → discovery smoke`로 워크스페이스 연결 (동일 세션 내에서는 1회만, 재사용)
2. **prompt-fed-context 사전적용 (필수)**: `codex exec` 호출 전에 필요한 파일들을 Hermes가 `read_file`로 직접 읽고 prompt에 삽입한다. Codex가 파일 탐색에 turn을 낭비하는 것을 방지.
3. **relay 호출 방식 선택** — 예상 소요시간 기준:
   - **2분 이하 예상**: `terminal()` foreground + upfront 알림만 ("🔁 작업 중...")
   - **3분 이상 예상**: `terminal(background=true, watch_patterns=['step', 'exec', 'progress'], notify_on_complete=true)` + 진행 후크 중계
4. **진행 후크 패턴 (3분 이상 relay)**:
   ```
   [10:42] 🔁 03 작업 시작... (예상 3~5분, progress 감시 중)
   [10:44] ⏳ 03 진행: 2분 경과  ← watch_patterns hit 시 자동 Slack 전송
   [10:47] ⏳ 03 진행: 5분 경과
   [10:55] 📬 03 응답 도착 — relay 시작   ← notify_on_complete 시 Slack 전송
   ```
   → 사용자가 "progress가 올라가네 → 정상", "progress 멈췄네 → hang 의심 → 정지" 판단 가능.
5. `process(action='wait')`로 완료 대기 후 응답을 사용자에게 요약 relay.
6. 사용자가 "일시정지"·"전부 정지"하면 즉시 `process(action='kill')` → relay 중단.
7. 사용자가 "인지부채 해소"·"풀이해달라"고 하면, relay prompt에 "사용자가 인지부채를 느낀다. 구체적 예시로 풀이하라"는 지시를 추가.

Pitfalls:
- relay 중 Hermes가 직접 분석·판단·제안을 끼워넣지 않는다 (사용자가 요청한 relay 외)
- 사용자 지시를 번역·요약하지 말고 원문 그대로 전달. 단 relay prompt에 bounded 제약만 추가
- **Dead Air — 진행 알림만으로 부족**: 단일 "작업 중... (예상 3~5분)" 메시지는 예상보다 relay가 길어질 때 사용자가 "hang인가?" 의심하게 만든다. 3분 이상 relay는 반드시 `terminal(background=true, watch_patterns=['step', 'exec', 'progress'])`로 진행 후크를 중계할 것.
- **Dead Air — streaming=false 증폭**: `config.yaml`에서 `streaming: enabled: false`면 Hermes의 모든 중간 출력이 Slack에 표시되지 않아 Dead Air가 구조적으로 증폭된다. `streaming: enabled: true`로 변경하면 도구 호출 단위로 Slack에 실시간 표시되어 근본적 Dead Air 해소.
- **게이트웨이 로그 자기진단 불신**: 게이트웨이 로그의 "Sending response"는 Slack API 호출 성공만 의미. 실제 사용자 클라이언트 렌더링 여부는 보장하지 않음.
- 동일 세션에서 여러 번 relay 시 preflight/discovery는 재사용, 프롬프트만 새로 발행
- **`process(action='wait')` timeout 60초 clamp**: Hermes의 `process(action='wait', timeout=N)`은 N이 600이어도 60초로 clamp된다. 장시간 background 작업은 `poll` 반복 패턴을 사용하라. `terminal(background=true, notify_on_complete=true)`로 완료 알림을 병행하면 poll 횟수를 줄일 수 있다. (claude-code-control §5 Pitfalls에도 동일 항목 있음)
- **Background `uv run` workdir 불안정 (WSL)**: `terminal(background=true, workdir=<path>)`로 `uv run` 실행 시 workdir가 background subshell에서 미적용되어 ModuleNotFoundError 발생 가능. 해결: `cd <workdir> && uv run ...` 접두사 사용.

### 서브에이전트 상담(consultation) 패턴 — `delegate_task` 대체 금지
예: `agent_os="codex-cli"`와 자체 `${CONTEXT_FILE}` 를 쓰는 워크스페이스의 근거 코멘트·리포팅/디자인 상담은 Hermes `delegate_task`로 대체하지 않는다. 실제 `CODEX_HOME` preflight와 read-only discovery smoke를 거친 뒤 `codex exec -C <workspace> -s read-only -o <result>`로 호출해야 워크스페이스 정체성, `${CONTEXT_FILE}` 로딩, sandbox/model 상태를 증명할 수 있다. Hermes가 직접 읽어 정리한 fallback은 primary Codex 상담 성공으로 기록하지 않는다.

## 7. Verification Checklist
- [ ] `agent-card.json` 직접 읽음, `agent_os="codex-cli"` 확인 / `context_file` 을 `${CONTEXT_FILE}` 로 확정
- [ ] `sandbox`/`model` 을 4-state 로 해석
- [ ] preflight 로 `CODEX_HOME_READY` 확정 (하드코딩 안 함)
- [ ] read-only discovery smoke 통과 + `git status` 미변경 확인
- [ ] `-C ${WS}` + Hermes `workdir` 동시 사용 (`cwd` 미사용)
- [ ] `model=default/null` 이면 `-m` 생략 / `-s <Card sandbox>` 명시 / `-o` 로 결과 캡처
- [ ] 결과를 `parse_codex_output.py`·`verify_artifacts.sh` 로 직접 검증
- [ ] 결과를 A2A 원장으로 기록: `task_state`(9-state)·`finality`·`control_plane`/`data_plane`·`failure_code`·`retry_allowed` (common-rules §K, primary-fallback-policy)
- [ ] primary/fallback 을 원장에 기록, fallback 을 성공으로 집계하지 않음
