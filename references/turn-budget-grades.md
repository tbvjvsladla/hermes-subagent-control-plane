# Turn 예산 · Grade 위임 — 정본 (scope ⊥ budget)

> 위임(`claude -p`) 시 **얼마의 turn 예산을 배분하고 어떤 제어패턴으로 돌릴지**의 **유일한 상세 위치**다.
> SKILL.md·다른 reference 는 한 줄 포인터만 둔다(중복 금지). 로드:
> `skill_view("claude-code-control", "references/turn-budget-grades.md")`.
>
> 계기: 라이브 E2E(easy_vllm_simulator, 2026-07-07)에서 `--max-turns 2/4`가 Bash 한 줄조차 마무리 못 하고
> 소진됐다(6에서 성공). 그런데 스킬 문서는 실패 시 "작업을 더 작게 쪼개고 재시도"(=예산도 축소)라고 지시해
> `실패 → 범위 축소 → max-turns 축소 → tool_use 중단 → 반복 실패`의 **하강나선**을 조장했다.
> 상세 계량: `references/e2e-lessons-learned.md`(714 실측). 실패코드 조치: `references/failure-codes.md`.

## 1. North Star — 두 축 분리 (scope ⊥ budget)

작업 **크기(scope)**와 turn **예산(budget)**은 **직교하는 두 개념**이다. 낮은 turn 수를 "tight 범위의 신호"로만
읽고 turn 소진을 범위 문제로만 진단하면, 예산 부족까지 "더 쪼개라 + 예산도 줄여라"로 오처방한다.

| 축 | 규율 | 실패 시 방향 |
|---|---|---|
| **축1 — scope** | `1 위임 = 1 결정론 작업`(유지). 이질적 작업을 한 프롬프트에 묶지 않는다. | 2개 이상 결합이면 → **쪼갠다** |
| **축2 — budget** | max-turns 는 그 1작업의 **기계적 완수비용**(tool call → output 수신 → 판단 → evidence 작성 → 최소 자기수습)을 덮어야 한다. 실측 하한 **≥6**, 유형별 스케일업. | budget 굶음/탐색낭비면 → **G5 주입 + 예산 증가**(축소 금지) |

**hang 은 max-turns 로 잡지 않는다.** hang/폭주는 `timeout` + 진행 로그 감시(`process poll/log`, Docker 상태
`Up`/`Exited`/restart loop, 동일 traceback 반복, 5~10분 로그 무변화) + health/logs 교차검증 + Hermes post-verify 로
분리 감지한다. max-turns 는 **비용/범위 knob**이지 hang knob 이 아니다.

## 2. Grade 분류표 (cold-start prior)

grade 는 예산만이 아니라 **제어패턴**(bounded shot / background+watchdog / relay+HITL)까지 정한다. 수치는
`references/e2e-lessons-learned.md` §1·§1.1 실측(창작 금지). Layer 2(§7)가 `(workspace,grade)`별 실측으로 이 prior 를 보정한다.

| grade | 대응 작업 | 기본 max-turns | 제어 패턴 |
|---|---|---:|---|
| **S** (scoping call) | read-only 정체성 증명 + grade 회신 (discovery 합승) | 8~12 고정 | 핸드셰이크(§3) |
| **L0** | 완성 런타임블럭 기동 · 단일 Bash 실행 | 6~10 | bounded shot + post-verify |
| **L1** | 단일 파일 생성/patch + 명령 1개 | 12~20 | bounded shot + post-verify |
| **L2** | recipe generate / compose up 등 산출 1단계 | 20~30 | bounded + 산출물 검증 |
| **L3** | 진단 + 원인분리 포함 runtime action | 30~50 | background + timeout/log watchdog |
| **L4** | full E2E 자율 · **전략수립 + HITL 루프** | 50~80 또는 background | **relay/HITL 루프**(§SKILL relay) + watchdog |

**부류 매핑**(portable — 특정 워크스페이스명 하드코딩 금지, common-rules §0):
- 완성된 런타임블럭을 단순 기동만 하는 워크스페이스(사전 빌드된 서버를 `serve` 명령으로 띄우는 번호 워크스페이스 등) → **L0**. Hermes 가 바로 확정.
- 지시는 단순하나 전략수립 + HITL 이 강제되는 novel 프로젝트(예: 서빙 시뮬레이터 부트스트랩) → **L4**. bounded 단일 shot 이 아니라 relay 로 중개.

> **L4 원자화 예외**: 본질적으로 추론이 무거운 전략작업(L4)은 억지로 원자화하지 않는다 — 매 shot 컨텍스트
> 재수립 비용만 낭비. `1위임=1작업`(축1)은 *이질적 결정론 작업 결합*을 막는 규율이지, 한 추론작업 내부를
> 쪼개라는 게 아니다. (triage-gate G4 의 예외 스코프와 동치.)

## 3. discovery 합승 grade 핸드셰이크

물리적으로 `claude -p` 는 매번 별도 프로세스라 상시 소켓이 없다. "서브가 grade 회신"은 read-only 호출 1회다.
스킬 흐름엔 **discovery(SKILL.md Step C)가 이미 무조건 들어가므로**, grade 추천을 그 회신에 **합승**시킨다 →
추가 왕복 0회. 모든 작업이 공짜로 self-grade 를 남겨 학습루프(§7) 연료가 된다.

| 단계 | 동작 |
|---|---|
| **Step C (discovery, S 예산 8~12)** | read-only 로 `{정체성 + grade_recommended(S/L0~L4) + planned_steps + needs_hitl + rationale}` 반환. 서브는 정확한 turn 수는 못 맞춰도 **grade 는 coarse 해서 자기평가 가능**. |
| **Step C→D (Hermes 배분)** | `grade_recommended` 재평가 → `grade_assigned` 확정 → §2 표에서 `max_turns_allocated` 배분. `needs_hitl=true` 면 bounded shot 대신 relay 패턴 선택. |
| **Step D (action)** | `--max-turns := max_turns_allocated`(매직상수 아님). L4 는 relay/background + watchdog. |

## 4. 원장 기록 (A2A 9-field 에 additive)

`references/primary-fallback-policy.md §3` control_attempt 원장에 아래 4필드를 additive 로 기록(rename 없음,
`a2a-taskstate-v1` 유지). `common-rules.md §K` 와 동치 축.

```yaml
  task_grade: {recommended: <S|L0|L1|L2|L3|L4|null>, assigned: <L0|L1|L2|L3|L4>}
  max_turns_allocated: <int>          # assigned grade → §2 표 배분
  max_turns_used: <int|null>          # 결과 JSON num_turns (scripts/parse_claude_json.py)
  budget_outcome: <ok|exhausted>      # error_max_turns & used>=allocated → exhausted
```

두 신호는 이미 파싱하는 JSON 봉투에서 기계추출된다: `grade_recommended` ← discovery JSON, `max_turns_used`
← action 결과 JSON `num_turns`. (`num_turns` 부재 시 `parse_claude_json.py` 는 `null` 로 표면화 — 풀백 금지.)

## 5. MAX_TURNS_EXHAUSTED 실패 방향 (하강나선 차단)

`--max-turns` 소진 시 **예산을 줄이지 않는다.** 두 축으로 진단한다:

1. **범위가 2개 이상이었나?** → 쪼갠다(축1).
2. **budget 이 굶었나 / 탐색에 turn 을 낭비했나?** → **G5 prompt-fed-context 주입 + max-turns 를 늘린다**(축2).
3. hang 은 timeout/log watchdog 으로 분리 감지(§1).
4. `MAX_TURNS_EXHAUSTED` = `failed`/terminal → 자동 재시도 금지. 교정은 **새 control_attempt**(더 큰 예산).

정정 패턴: `실패 → 범위 축소 → max-turns 충분히 유지/증가 → hang 은 timeout/log 로 감시`.
(조치 정본은 `references/failure-codes.md` MAX_TURNS_EXHAUSTED 행이 본 절을 가리킨다.)

## 6. 위임 전 예산 체크

- [ ] discovery 로 `grade_recommended` 를 받았는가(합승)? Hermes 가 `grade_assigned` 로 재평가했는가?
- [ ] `max_turns_allocated` 를 §2 표에서 배분했는가(하한 ≥6, 매직상수 아님)?
- [ ] L3/L4 는 background + timeout/log watchdog 을 붙였는가(hang 은 max-turns 로 안 잡음)?
- [ ] L4(전략+HITL)는 relay 패턴으로 갔는가(bounded 단일 shot 아님)?
- [ ] 원장 4필드(§4)를 기록했는가?

## 7. Layer 2 청사진 (미구현 — 설계만)

정적 §2 표는 cold-start prior 다. 실데이터 축적 후 별도 사이클에서 자기보정한다.
- **저장**: Hermes 측 전역 `turn-calibration`(대상 워크스페이스 아님 — 교차보정이라 전역).
- **스키마(1줄/기록)**: `<ts> <workspace> <grade_assigned> allocated=<n> used=<n> outcome=<ok|exhausted>`.
- **decay**: `(workspace, grade)` 키당 최근 ~20줄 FIFO(전역 단일 cap 이면 희소 워크스페이스 이력이 통째로
  밀리므로 키별 cap).
- **calibration**: 키별 `used` p90(성공 기록 한정)으로 §2 prior 보정 → `max(prior_기본, p90×여유계수)`.
- **연료**: 본 버전(v4.3.0)이 원장에 `max_turns_used` 를 기록하므로 이때부터 데이터가 쌓인다.
