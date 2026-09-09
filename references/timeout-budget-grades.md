# Timeout 예산 · Grade 위임 — 정본 (scope ⊥ timeout) — Codex CLI

> 위임(`codex exec`) 시 **얼마의 wall-clock timeout 을 배분하고 어떤 sandbox·제어패턴으로 돌릴지**의 **유일한
> 상세 위치**다. SKILL.md·다른 reference 는 한 줄 포인터만 둔다(중복 금지). 로드:
> `skill_view("codex-cli-control", "references/timeout-budget-grades.md")`.
>
> **codex 는 `--max-turns` 가 없다**(CLI `--help` 실측: turn-cap flag 0건). claude 의 turn-budget 을 codex 에 그대로
> 옮기지 않는다 — codex 의 유일한 caller-visible budget knob 은 **wall-clock `timeout`**(Hermes `terminal(timeout=…)`
> 래퍼)이다. 이 파일은 claude `turn-budget-grades.md` 의 codex 대응이며, 축은 turn 이 아니라 **timeout(초)**다.

## 1. North Star — 두 축 분리 (scope ⊥ timeout)

작업 **크기(scope)**와 **timeout 예산(budget)**은 **직교하는 두 개념**이다. codex 를 tight timeout 으로 감싸 완수
전에 kill 하면, "더 쪼개고 timeout 도 줄여라"로 오처방해 `실패 → 범위축소 → timeout축소 → 완수 전 kill → 반복
실패`의 **하강나선**에 빠진다(claude 의 max-turns 하강나선과 동형 — `commission_26070714`).

| 축 | 규율 | 실패(timeout-kill) 시 방향 |
|---|---|---|
| **축1 — scope** | `1 위임 = 1 결정론 작업`(유지). 이질적 작업을 한 프롬프트에 묶지 않는다. | 2개 이상 결합이면 → **쪼갠다** |
| **축2 — budget(timeout)** | timeout 은 그 1작업의 **기계적 완수 wall-clock**(codex 내부 추론·도구실행·산출·검증)을 덮어야 한다. 유형별 스케일업. | 완수 전 kill 이면 → context 주입 + **timeout 증가**(축소 금지) |

**hang 은 tight timeout 으로 잡지 않는다.** hang/폭주는 background 실행 + **log-watch**(`process poll/log`, `watch_patterns`)
+ Card에 선언된 runtime 상태 + Hermes post-verify 로 분리 감지한다. timeout 은
비용/완수 여유 knob 이지 hang knob 이 아니다.

## 2. Grade 분류표 (prior — timeout + sandbox 축)

grade 는 timeout 만이 아니라 **sandbox 와 제어패턴**까지 정한다. **codex 는 실측 timeout 데이터가 없어(codex
e2e-lessons 부재) 아래 수치는 순수 prior** — Layer 2(§7)가 `wall_seconds_used` 실측으로 보정한다. (현행 SKILL.md
discovery `timeout=300` 과 정합.)

| grade | 대응 작업 | 기본 timeout(s) | sandbox | 제어 패턴 |
|---|---|---:|---|---|
| **S** (scoping smoke) | read-only 정체성 + grade 회신 (discovery 합승) | 120~300 | `read-only` | 핸드셰이크(§3) |
| **L0** | 완성 런타임블럭 기동 · 단일 명령 | 180~300 | `read-only`/`workspace-write` | bounded + post-verify |
| **L1** | 단일 파일 생성/patch + 명령 1개 | 300~600 | `workspace-write` | bounded + 산출물 검증 |
| **L2** | recipe generate / 보고서 조판 등 산출 1단계 | 600~1200 | `workspace-write` | bounded + 산출물 검증 |
| **L3** | 진단 + 원인분리 포함 runtime action | 1200~1800 | `workspace-write` | **background + log-watch + 선언된 runtime 상태 + post-verify** |
| **L4** | full E2E 자율 · **전략수립 + HITL 루프** | background(고정 timeout 금지) | `workspace-write` | **relay/HITL 루프** + watchdog |

**부류 매핑**(portable — 특정 워크스페이스명 하드코딩 금지, common-rules §0): 완성 런타임블럭 기동 → L0 / 보고서
조판·metric 분석 같은 산출 1단계 → L2 / 진단 포함 runtime → L3.

> **L4 원자화 예외**: 추론이 무거운 전략작업(전략+HITL)은 억지 원자화하지 않는다 — 매 호출 컨텍스트 재수립 비용만
> 낭비. `1위임=1작업`(축1)은 *이질적 결정론 작업 결합*을 막는 규율이지 한 추론작업 내부를 쪼개라는 게 아니다.

## 3. discovery 합승 grade 핸드셰이크 (codex)

codex Step C discovery smoke(`codex exec -C ${WS} -s read-only -o $OUT`)가 이미 무조건 들어가므로, grade 추천을
그 회신에 **합승**시킨다 → 추가 왕복 0회. **codex 이점**: `--output-schema <FILE>` 로 grade JSON 스키마를 강제할
수 있다(freeform 보다 견고).

| 단계 | 동작 |
|---|---|
| **Step C (discovery, S timeout 120~300, `-s read-only`)** | 정체성 + `grade_recommended(S/L0~L4)`·`planned_steps`·`needs_hitl`·`rationale` 회신(선택 `--output-schema`). codex 는 정확한 wall-clock 은 못 맞춰도 **grade 는 coarse 해서 자기평가 가능**. |
| **Step C→D (Hermes 배분)** | `grade_recommended` 재평가 → `grade_assigned` → §2 표에서 `timeout_allocated_s` 배분(terminal timeout). `needs_hitl` 이면 relay 패턴. |
| **Step D (action)** | Hermes `terminal(timeout = timeout_allocated_s)`(매직상수 아님). L3/L4 는 `background=true` + log-watch + 선언된 runtime 상태 + Hermes 사후 검증. |

## 4. 원장 budget 필드 (primary-fallback-policy §원장 에 additive)

```yaml
  task_grade: {recommended: <S|L0|L1|L2|L3|L4|null>, assigned: <L0|L1|L2|L3|L4>}
  timeout_allocated_s: <int>          # assigned grade → §2 배분 (codex budget = wall-clock)
  wall_seconds_used: <int|null>       # Hermes 측정(terminal 시작→종료). codex 출력엔 없음 → 미측정 시 null
  budget_outcome: <ok|timeout_killed> # terminal timeout 도달로 kill → timeout_killed
```

claude 와 대칭(claude=`max_turns_*`/`ok|exhausted`). 공통 계약 = `common-rules §K`(단위 중립). rename 없음(additive)
→ Base-Layer Invariant 미발동.

## 5. TIMEOUT_KILLED 실패 방향 (하강나선 차단)

terminal timeout 으로 `codex exec` 가 완수 전 kill 되면 **timeout 을 줄이지 않는다.** 두 축으로 진단한다:

1. **범위가 2개 이상이었나?** → 쪼갠다(축1).
2. **완수 전 kill 이었나(진행 로그는 살아있었나)?** → context 주입 + **timeout 을 늘린다**(축2).
3. hang(진짜 멈춤) vs 느림 구분은 **log-watch + 선언된 runtime 상태 + Hermes 사후 검증**으로 한다(tight timeout 아님).
4. `TIMEOUT_KILLED` = terminal → 자동 재시도 금지. 교정은 **새 control_attempt**(더 큰 timeout).

(전송 계층 오류 조치는 `references/failure-codes.md` 의 `CODEX_TRANSPORT_UNREACHABLE` 행을 따른다.)

## 6. 위임 전 예산 체크

- [ ] discovery 로 `grade_recommended` 를 받았는가(합승)? Hermes 가 `grade_assigned` 로 재평가했는가?
- [ ] `timeout_allocated_s` 를 §2 표에서 배분했는가(매직상수 아님)?
- [ ] L3/L4 는 background + log-watch + 선언된 runtime 상태 + Hermes 사후 검증을 붙였는가(hang 은 tight timeout 으로 안 잡음)?
- [ ] L4(전략+HITL)는 relay 패턴으로 갔는가?
- [ ] 원장 budget 4필드(§4)를 기록했는가?

## 7. Layer 2 청사진 (미구현 — 설계만)

정적 §2 표는 cold-start prior 다(codex 실측 없음). 실데이터 축적 후 별도 사이클.
- **저장**: Hermes 측 전역 codex-timeout-calibration(대상 워크스페이스 아님 — 교차보정).
- **스키마(1줄/기록)**: `<ts> <workspace> <grade_assigned> alloc_s=<n> used_s=<n> outcome=<ok|timeout_killed>`.
- **decay**: `(workspace, grade)` 키당 최근 ~20줄 FIFO(키별 cap).
- **calibration**: 키별 `wall_seconds_used` p90(성공 기록)으로 §2 prior 보정 → `max(prior, p90×여유계수)`.
- **연료**: 본 버전(v4.2.0)이 원장에 `wall_seconds_used` 를 기록하므로 이때부터 데이터가 쌓인다.
