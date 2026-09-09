# 배치 수집 패턴 — Claude Code 실패 후 Hermes 직접 실행

## 발생 상황

Claude Code `claude -p`로 300건 NL2SQL API 배치 수집을 맡겼으나 `max_turns` 초과로 실패.
이후 Hermes가 직접 Python 스크립트로 수집을 완료한 패턴.

## 핵심 문제

1. **Claude Code max_turns**: 결정론적 반복 작업(300건 API 호출)에 Claude Code를 쓰면
   turn 제한에 걸려 중간에 멈춘다. `--max-turns 15`로는 50건도 못 끝냄.
2. **CSV 개행 문제**: SQL 필드에 개행이 있으면 기본 `csv.writer`가 파일을 깨뜨린다.
   `wc -l`은 224줄인데 `csv.DictReader`는 3행만 파싱하는 증상.

## 해결 패턴

### 1. 단일 모델 순차 수집 스크립트
```python
import urllib.request, json, csv, time, re

def extract_tag(text, tag):
    m = re.search(rf'<{tag}>(.*?)</{tag}>', text, re.DOTALL)
    return m.group(1).strip() if m else ''

for i, sample in enumerate(samples):
    data = json.dumps({'model': MODEL, 'messages': [{'role': 'user', 'content': sample['question']}]}).encode()
    req = urllib.request.Request('http://localhost:8000/v1/chat/completions', data=data,
        headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=120) as resp:
        body = json.loads(resp.read())
        content = body['choices'][0]['message']['content']
        # extract <sql>, <summary>, <structured_output>, <metadata> tags
```

### 2. CSV 저장 — QUOTE_ALL 필수
```python
with open(out_path, 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
    writer.writeheader()
    for r in results:
        writer.writerow({k: r.get(k, '') for k in fieldnames})
```

### 3. 병렬 수집 (ThreadPoolExecutor)
```python
from concurrent.futures import ThreadPoolExecutor, as_completed
with ThreadPoolExecutor(max_workers=2) as executor:
    futures = {executor.submit(call_model, model, s['question']): s for s in samples}
    for future in as_completed(futures):
        ...
```

주의: ThreadPoolExecutor + urllib는 일부 모델(gemini)에서 hang 현상 발생.
순차 실행이 더 안정적이지만 느리다(300건 × 6s = 30분).

## 진행상황 로깅

background 실행 시 stdout 버퍼링 때문에 출력이 안 나올 수 있다.
파일 기반 progress 로깅이 신뢰성 높다:
```python
if (i+1) % 10 == 0:
    with open('/tmp/collect_progress.txt', 'w') as pf:
        pf.write(f'{i+1}/300 ok={ok} elapsed={elapsed:.0f}s\n')
```

## 교훈

- 결정론적 배치 작업(>50건 API 호출) → Hermes 직접 실행이 Claude Code보다 빠르고 안정적
- Claude Code는 reasoning-intensive 작업(스크립트 설계·디버깅)에만 사용
- CSV에 SQL 저장 → 반드시 QUOTE_ALL
- background 스크립트 진행 확인 → 파일 로깅이 stdout보다 신뢰성 높음
