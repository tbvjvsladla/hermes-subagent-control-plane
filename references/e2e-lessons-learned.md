# E2E 실전 교훈 — claude-code-control (v4.1.0 → v4.2.0 → v4.3.0 turn예산 개정 근거)

> 이 파일은 `server-hitl-260706204657` E2E(2026-07-06)에서 실제 검증된 교훈을 문서화한다.
> 대상: easy_vllm_simulator (Claude Code 서브에이전트) — gemma-4-E4B-it 서빙 E2E.
> 전체 E2E 는 총 12회 `claude -p` 호출 · 6회 성공 · 6회 turn 소진/타임아웃(devlog3 전수 기준).
> 아래 §1 표는 대표 9회를 유형별로 정리한 subset 이다(전수 아님 — 헤드라인 수치와 표 행수 차이는 이 subset 관계 때문).

---

## 1. 단일 작업 위임 vs 복합 다단계 — 계량 증거

| 호출 유형 | turn 소비 | 결과 | 위임 내용 |
|---|---|---|---|
| parse+crosscheck+estimate 1회 | 24 turns | 성공했으나 과도한 turn | 3단계 밀집 |
| parse+crosscheck+estimate+generate 1회 | 27 turns | 성공했으나 한계 | 4단계 밀집 |
| generate only (1차 시도) | 6 turns | **turn 소진 실패** | 파일 탐색에 turn 낭비 |
| generate only (G5 적용) | 3 turns | **성공** | 데이터 주입 + 범위 최소 |
| container start (1차) | 8 turns | **timeout 실패** | compose+health+chat 밀집 |
| container start debug (1차) | 15 turns | **turn 소진 실패** | 진단+수정+기동 복합 |
| container start debug (2차) | 15 turns | **turn 소진 실패** | GPU 진단 복합 |
| container start (단순화) | 8 turns | **turn 소진 실패** | 기동+health+chat 3단계 |
| container start (최소) | 3 turns | 부분 성공 (퇴장했으나 기동됨) | 기동만 |

**결론**: 단일 결정론 작업 1개당 3~6 turn 관측(G5 완전주입·최소범위 하). 2단계 이상 결합 시 15+ turn에서 turn 소진. **G4 규칙 강화: 1회 위임 = 1개 이질적 결정론 작업.**

> ⚠️ **이 3~6 은 budget 하한이 아니다** — G5 없이/탐색 여지가 있으면 더 필요하다. 실무 하한은 tool completion + 자기수습 여유 포함 **≥6**, 유형별 예산은 grade표(`references/turn-budget-grades.md` §2). max-turns 소진 시 예산을 **줄이지 말고 늘린다**(`references/failure-codes.md` MAX_TURNS_EXHAUSTED).

### 1.1 714 라이브 재검증 — max-turns 하한 실측 (easy_vllm A.X-4.0-Light-7B, 2026-07-07)

`commission_26070714` 라이브 E2E: 지시는 "타겟 GPU 서빙"으로 단순하나 전략수립+HITL 이 필요한 **L4** 작업. **단일 Bash 실행조차 max-turns 2/4 는 소진 실패, 6 에서 성공.**

| max-turns | 결과 |
|---:|---|
| 2 | 실패(`error_max_turns` — Bash 한 줄도 마무리 못 함) |
| 4 | 실패(`error_max_turns`) |
| 6 | **성공**(컨테이너 기동 + Hermes 검증 PASS) |

교훈: **작업은 작게 쪼개되 max-turns 는 줄이지 않는다.** hang 은 max-turns 가 아니라 timeout + 로그감시 + post-verify 로 잡는다(`references/turn-budget-grades.md` §1·§5).

---

## 2. G5 prompt-fed-context — 계량 증거

| 호출 | 데이터 사전 주입 여부 | turn 소비 | 결과 |
|---|---|---|---|
| config.yaml 생성 + recipe generate | **주입 안 함** | 6 turns | 실패 — Claude가 SKILL.md·컨텍스트 파일 읽느라 turn 소진 |
| config.yaml 생성 + recipe generate | **주입함** (config 템플릿, r12 데이터, yaml 경로) | 3 turns | 성공 |
| container start + health + chat | **주입 안 함** | 8 turns | 실패 |
| container start only (모델 경로, compose 경로 주입) | **주입함 (지만 범위가 넓음)** | 8 turns | 실패 |

**모범 사례** (generate 성공 케이스):
```text
"너는 서브에이전트다. 파일 읽기 없이 다음 3단계만 실행하라.
단계1 — config.yaml 생성: Write 도구로 다음 내용을 그대로 써라: <전체 내용>
단계2 — generate 실행: Bash로 <정확한 명령어> 실행
단계3 — JSON 반환: {task_state, generated_files, error}
컨텍스트 파일, agent-card.json, SKILL.md 등 읽을 필요 없다."
```

> ⚠️ **모범사례 스코프(G4 예외)**: 이 3단계 결합은 *동일 grade 내부의 강결합 결정론 시퀀스*(config write→generate→return)로 **L2 단일 산출단계의 내부 절차**다 — 서로 다른 이질적 결정론 작업 2개를 묶는 것과 다르다. G4 원자화(`1위임=1작업`)는 이질 작업 결합을 막는 규율이지 한 산출단계 내부를 쪼개라는 게 아니다(`references/turn-budget-grades.md` §2 L4 예외와 동치).

---

## 3. `--dangerously-skip-permissions` 사용 판단

이 E2E에서 모든 성공적인 Write/Bash 호출은 `--dangerously-skip-permissions`를 사용했다.

**안전한 사용 조건** (SKILL.md §3-D 주의사항의 구체화):
1. 격리 워크스페이스 (원격 연결 끊김, 로컬 전용)
2. 명령형 지시 (자유도 없음, 단계가 명시됨)
3. 쓰기 대상이 gitignored 산출물 통로 (`output/`, `.hermes-claude-control/runs/`, `temp/`)
4. product code (Dockerfile, compose 템플릿, configs skeleton) 수정 없음

**절대 사용 금지**: read-only discovery, product code 수정, 브랜치 전환, manifest Flag 변경, 서브노드 provisioning.

---

## 4. WSL / Docker Desktop CIFS 마운트 전파 pitfall

**증상**: 컨테이너 안에서 CIFS NAS 마운트포인트가 빈 디렉토리로 보임.
**원인**: Docker Desktop(별도 WSL VM)에서 CIFS 마운트에 대해 private propagation 적용.
**진단**: `docker run --rm -v /mnt/llm_model:/mnt:ro <image> ls /mnt/` → 비어있음.
**해결**: 마운트포인트 자체가 아닌 **child 서브디렉토리**를 bind:
```yaml
# 실패: - ${NAS_MODEL_PATH:-/mnt/models}:/app/models:ro
# 성공: - ${NAS_MODEL_PATH:-/mnt/models}/Model:/app/models/Model:ro
```
**근거**: child 디렉토리를 bind하면 CIFS 안으로 traverse되어 실제 내용이 보인다.
**참고**: NFS는 일반적으로 이 문제가 없음. CIFS + Docker Desktop 조합에서만 재현.

---

## 5. Simulator 프로젝트: target GPU ≠ actual HW

**문제**: easy_vllm_simulator는 실제 HW(RTX 5090 32GB)에서 타겟 GPU(RTX 4090 24GB)를 시뮬레이션한다.
**함정**: `gpu-memory-utilization: 0.95`만 설정하면 실제 HW 기준으로 계산되어 5090에서 30.4GB 사용 → 4090 PC에 이식 시 OOM.
**해결**: 절대 KV clamp(`--kv-cache-memory-bytes`)를 **타겟 예산**(24GB × 0.9 = 21.6 GiB) 기준으로 산정:
```
kv-cache-memory-bytes = target_budget_gib × 1GiB - weights_gib - overhead_gib
                     = 24 × 0.9 × 1073741824 - 14.89 × 1073741824 - 2.55 × 1073741824
                     ≈ 4468944000 bytes (≈ 4.16 GiB)
```
**gmu는 startup free-memory 게이트용으로만 유지**하고, KV 사이징은 절대 clamp가 제어한다.
**검증**: yaml 주석에 "RTX 4090 24GB 타겟 시뮬레이션 — 절대 KV clamp 적용" 명시.

> ⚠️ **스코프 caveat**: 위 절대수치(4.16 GiB, 21.6 GiB 예산 등)는 **easy_vllm_simulator 전용 예제**다. 타 워크스페이스에 그대로 이식 금지 — 원리(타겟예산 기반 절대 KV clamp)만 이식하고 수치는 각 타겟 HW/모델로 재산정한다.

---

## 6. Turn exhaustion 복구 결정트리

E2E에서 검증된 패턴:
```
claude -p 결과
├── exit 0 + is_error=false → 검증 후 계속
├── exit 1 (timeout/turn 소진) → 
│   ├── 1. search_files 로 예상 산출 경로 확인
│   ├── 2. 부분 산출 있으면 → Hermes가 읽어서 검증
│   │   ├── 산출이 요구 충족 → "Hermes recovery record"로 기록, 다음 단계로
│   │   └── 산출 불충분 → 원인 분석 후 단일 작업으로 재위임
│   └── 3. 부분 산출 없으면 → 
│       ├── G5 데이터 주입 보강
│       ├── 작업 범위를 1개 결정론 작업으로 축소
│       ├── --max-turns 재산정 — **줄이지 말고 grade→예산표대로 ↑**(단일 L0 6~10/L1 12~20, 진단 L3 30~50, 소진값 이하로 내리지 않음; scope 축소와 budget은 직교 — references/turn-budget-grades.md §2·§5)
│       └── 재위임
└── 이 패턴을 3회 초과 반복 금지 → 사용자에게 HITL 보고
```

---

## 7. E2E 성공률 향상을 위한 위임 전 체크리스트

- [ ] 1회 위임 = 1개 결정론 작업인가? (G4 강화)
- [ ] 필요한 모든 파일 경로/데이터를 prompt에 주입했는가? (G5)
- [ ] `--allowedTools`가 위임 작업에 필요한 최소 집합인가?
- [ ] `--max-turns`가 grade→예산표(`references/turn-budget-grades.md` §2)대로 **충분히** 배분됐는가? (줄이지 않음; 단일 L0 6~10/L1 12~20, 진단 L3 30~50, 하한 ≥6)
- [ ] `--dangerously-skip-permissions` 사용 조건을 충족하는가? (§3)
- [ ] product code, 스킬 본문, 헌법 파일을 건드리지 않는가?
- [ ] timeout이 작업에 충분한가? (단기 300s, 장기/진단 600s)
