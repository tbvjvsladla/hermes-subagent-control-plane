# Gateway Latency Diagnosis — Slack 응답지연 진단 패턴

claude-code-control relay 중 사용자가 "응답이 안 온다"고 제보할 때의 진단 절차와 검증 기준.

## 진단 3단계

### 1단계: 게이트웨이 로그에서 타임라인 추출

```bash
# 6/13 기준 응답시간 전수
grep "response ready.*platform=slack" ~/.hermes/profiles/<profile>/logs/gateway.log \
  | sed 's/.*time=//' | sed 's/s.*//' | sort -n
```

판정 기준:
- `time=<10s`: Hermes 직접 응답, 정상
- `time=100~800s`: Claude Code relay, Dead Air 구간
- `time=>1000s`: 복합 작업 또는 turn exhaustion 재시도 포함

### 2단계: 게이트웨이 ↔ Slack 전송 지연 확인

```bash
# response ready → Sending response 사이 시간차
grep -E "(response ready.*platform=slack|Sending response)" gateway.log \
  | paste - - | awk '{...}'
```

판정 기준:
- 10~20ms: 정상 (Slack API 호출 레이턴시)
- >1초: Slack API 지연 또는 rate limit 의심

### 3단계: Slack 대화내역 교차검증

게이트웨이 로그의 "Sending response" 시각과 실제 Slack 쓰레드에 메시지가 표시된 시각을 비교.

게이트웨이 로그만으로는 "Slack API 호출 성공"만 확인 가능. 실제 클라이언트 렌더링·스크롤 위치·알림 도달 여부는 보장하지 않음.

## streaming 설정 영향

```yaml
# config.yaml
streaming:
  enabled: false  # ← Dead Air 증폭. 모든 도구 호출 완료 후 한 번에 전송
  enabled: true   # ← 도구 호출 단위로 Slack에 실시간 표시
```

`streaming: false`일 때 claude relay 4~13분 동안 Slack에 `typing...` 인디케이터조차 표시되지 않음. 사용자는 완벽한 Dead Air = 통신 단절로 인지.

## Slack API 불안정 이력 패턴

과거 로그에서 발견된 Slack 불안정 신호:
- `chat.postMessage` 실패 (status 200인데 API error) — 5/31, 6/2 발생
- `Socket Mode unhealthy (transport disconnected)` — 6/10, 6/11 발생 → 자동 재연결
- `final stream delivery not confirmed` → 메시지 큐잉 발생

이런 이력이 있으므로 "게이트웨이 오작동 아님" 진단만 내리지 말고, Slack 쪽 이슈 가능성도 함께 보고할 것.

## Dead Air 계층 구조

relay 중 Dead Air는 3계층으로 발생:

| 계층 | 원인 | 진단 | 해소 |
|---|---|---|---|
| 1차 | claude -p 처리시간 (4~13분) | foreground terminal 블로킹 | 진행 알림 |
| 2차 | turn exhaustion → Hermes 파일 직접읽기 → 재시도 (추가 2~3분) | `error_max_turns` 로그 | G5 prompt-fed-context 사전적용 |
| 3차 | Agent cache idle-TTL eviction (3760s) → 세션 재생성 | `Agent cache idle-TTL evict` 로그 | 세션 타임아웃 연장 또는 streaming으로 idle 방지 |

1차만 해소하는 단일 진행알림으로는 2~3차 Dead Air가 잔존. G5 사전적용이 2차를, streaming이 3차를 각각 해소.
