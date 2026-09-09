# 사전위임 Triage 게이트 (무엇을 위임할지 — 정본)

> 위임(`claude -p` / `codex exec`) **전에** Hermes 가 통과시키는 단일 결정 게이트.
> 통과 → 작업 위임(`working` 진입). 불통 → 위임하지 않고 `rejected`/`auth-required` 로 **앞단 차단**(common-rules §K).
> 이 파일이 "무엇을 위임할지" 판단의 **유일한 상세 위치**다. SKILL.md·다른 reference 는 한 줄 포인터만 둔다(중복 금지).
>
> 계기: 다단계 복합작업·결정론 배치를 단일 `--max-turns` 위임으로 떠넘겨 4/4 turn 소진(protocol_26061117).

## 게이트 (위임 전 전수 통과)

| # | 체크 | 조건 | 불통 시 조치 | A2A 결과 |
|---|---|---|---|---|
| **G1** | 결정론 배치 | >~50건 **동일 동작 반복**(API 호출·SQL 실행·파일 변환 루프) | **위임 금지.** Hermes 가 직접 스크립트로 실행(primary-fallback-policy 의 fallback 라벨). CLI 에는 **스크립트 설계만** 시킬 수 있다. | 위임 자체 `rejected` |
| **G2** | 멀티라인 산출 | 산출 CSV 에 개행 포함 필드(예: `<sql>`) | 위임 프롬프트에 **"CSV 는 `csv.QUOTE_ALL` 로 쓸 것"** 명시(개행이 레코드 경계를 깨뜨림). | 통과 |
| **G3** | 외부 의존성 | 스크립트가 비표준 import(예: `psycopg2`) / 호스트 도구(psql 등) 가정 | 위임 전 `uv pip list`(또는 `command -v`)로 **의존성 사전 확인**. 없으면 대안(순수 stdlib·`docker exec`) 지정. | 미충족 시 `rejected` |
| **G4** | 복합 다단계 | Docker 기동 + DB 적재 + 평가 등 1프롬프트 다단계 | **bounded 단계 분할**: 각 단계를 별 호출로 쪼개고 Hermes 가 단계 사이 **체크포인트**(예: `/health`·`docker ps`·산출물 존재). 각 단계 max-turns 는 **grade→예산표대로 충분히**(정상 tool completion + 자기수습 여유) — '작게'가 아니다(예산 부족은 하강나선). 예산/grade 정본: `references/turn-budget-grades.md`. | 단계별 `working` |

## 판단 기준 (요지)
- **"N건에 대해 동일 동작 반복" → CLI 위임 아님**(매 턴 LLM 추론 = turn 낭비). reasoning-집약(스크립트 설계·디버깅)만 위임.
- CLI 가 스크립트 작성·실행·디버깅을 **모두** 시도하면 turn 이 소진된다 — **작성과 실행을 분리**(CLI 설계 → Hermes 실행)하거나 단계 분할.
- 굳이 CLI 로 배치를 돌려야 하면 `--max-turns` 를 넉넉히(30+) + background + **충분한 timeout**.
- **L4 원자화 예외**: 본질적으로 추론이 무거운 전략작업(전략수립 + HITL)은 억지로 원자화하지 않는다 — 매 shot 컨텍스트 재수립 비용만 낭비. 원자화(`1위임=1작업`)는 *이질적 결정론 작업 결합*을 막는 규율이지 한 추론작업 내부를 쪼개라는 게 아니다(grade L4 = relay/HITL, `references/turn-budget-grades.md` §2).

## 연계
- 실패 시 **구체 코드·처방**: `references/failure-codes.md`(상태축).
- 원장 기록: `references/primary-fallback-policy.md`(fallback 라벨 — 직접실행을 primary 성공으로 집계 금지).
- G1 직접 실행 시 스크립트 레시피(있는 스킬 한정)는 그 스킬 자신의 `references/` 에서만 `skill_view` 한다(스킬 간 cross-load 금지 — common-rules 머리말).
