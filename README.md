# claude-code-control 배포 패키지

실제 Claude Code CLI 서브에이전트를 `agent-card.json` 기반으로 제어하는 Hermes 스킬이다. 이 폴더는 Hermes 공식 스킬 구조인 `SKILL.md`와 `references/`, `scripts/`를 완결된 묶음으로 제공한다.

## 패키지 범위

- Hermes profile에 설치되는 제어 스킬이다.
- 대상 워크스페이스를 자동 개조하거나 `agent-card.json`을 대신 생성하는 installer가 아니다.
- 대상에는 `agent-card.json`, 카드가 선언한 context file, Claude Code CLI가 이미 있어야 한다.
- 인증정보와 API key는 포함하지 않는다.

## 요구사항

- Linux 또는 WSL
- Hermes Agent
- `claude` CLI
- Python 3 및 Bash
- Hermes toolset: `terminal`, `file`

## 로컬 폴더 설치

기존 동명 스킬을 덮어쓰지 않는 새 설치 예시다.

```bash
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
test ! -e "$HERMES_HOME/skills/claude-code-control"
cp -R ./claude-code-control "$HERMES_HOME/skills/claude-code-control"
```

named profile에 설치할 때는 먼저 해당 profile home을 명시한다.

```bash
PROFILE="research"
HERMES_HOME="$HOME/.hermes/profiles/$PROFILE"
test ! -e "$HERMES_HOME/skills/claude-code-control"
cp -R ./claude-code-control "$HERMES_HOME/skills/claude-code-control"
```

설치 후 새 Hermes 세션을 시작하거나 기존 세션에서 `/reload-skills`를 실행한다. 이후 확인한다.

```bash
hermes skills list
```

## GitHub/tap 배포

GitHub 저장소에서 `skills/claude-code-control/` 아래에 이 폴더 전체를 둔다. 개별 설치 형식은 다음과 같다.

```bash
hermes skills inspect owner/repo/skills/claude-code-control
hermes skills install owner/repo/skills/claude-code-control
```

여러 스킬을 한 저장소에서 제공하려면 tap을 사용할 수 있다.

```bash
hermes skills tap add owner/repo
hermes skills search claude-code-control --source owner/repo
hermes skills install owner/repo/claude-code-control
```

실제 원격 발행은 별도 인증·저장소 권한이 필요한 외부 작업이다. 현재 폴더 적재만으로 publish 또는 install이 완료된 것은 아니다.

## 설치본 검증

패키지 루트에서 실행한다.

```bash
python3 scripts/test_claude_control_scripts.py
bash -n scripts/preflight_claude_auth.sh
bash -n scripts/verify_server.sh
python3 -m py_compile scripts/card_drift_check.py scripts/parse_claude_json.py
```

실제 연결은 대상 카드 확인 후 다음 순서를 따른다.

1. `scripts/preflight_claude_auth.sh`로 유효 HOME 탐지
2. read-only discovery smoke
3. bounded action
4. parser와 카드별 verification으로 독립 검증

## 포함 파일

- `SKILL.md`: Hermes 진입점
- `references/`: 공통 제어 계약, 실패 분류, triage, budget, 실전 참고자료
- `scripts/`: 인증 preflight, 결과 parser, 서버/card 검증기, 자체 테스트
- `LICENSE`: MIT
- `README.md`: 배포·설치·검증 안내
- `PACKAGE_MANIFEST.json`: 배포본 파일별 SHA-256·크기·mode inventory

캐시, `__pycache__`, `.pytest_cache`, 인증정보, 런타임 로그는 포함하지 않는다.

## 공식 근거

- Hermes Skills System: https://hermes-agent.nousresearch.com/docs/user-guide/features/skills
- Hermes CLI Commands: https://hermes-agent.nousresearch.com/docs/reference/cli-commands

## 라이선스

MIT. `LICENSE`를 참조한다.
