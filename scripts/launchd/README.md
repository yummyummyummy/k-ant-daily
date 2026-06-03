# Local scheduling with launchd (macOS)

Mac mini에서 24/7 돌리는 용도. cron 대신 launchd 사용 — 슬립에서 깨울 수 있고 macOS 표준 방식.

## 한 번에 설치

```bash
./scripts/launchd/install.sh
```

세 개의 LaunchAgent 가 설치됨:
- `com.yummyummyummy.k-ant-daily.briefing`      — 평일 **07:30 KST** `/daily-report` (캘린더 갱신 + 보유종목 트래킹)
- `com.yummyummyummy.k-ant-daily.digest`        — 매일 **23:00 KST** `/post-market-digest` (장 마감 후 뉴스 다이제스트)
- `com.yummyummyummy.k-ant-daily.check-results` — **30분 주기** `/check-results` (방금 끝난 이벤트 결과 반영)

`check-results` 는 매 30분 fire 하지만 `scripts/pending_results.py` 로 **저렴하게 게이트**됨 — 결과 대기 이벤트(최근 4시간 내 종료 + result 비어있음)가 없으면 git/Codex 건드리지 않고 즉시 종료. 즉 이벤트 있는 날에만 실제 실행 → Codex 사용량 최소. dirty 작업 트리면 reset 안 하고 skip (작업 보호).

이전 컨셉(예측/리뷰/NXT 스냅샷) agent (`nxt-snapshot`, `review`, `refresh`) 는 제거됨. install.sh 가 잔존 agent 자동 unload.

로그는 `~/Library/Logs/k-ant-daily/` 에 누적됨 (실행당 한 파일).

## ⚠️ 작업 중 주의

각 wrapper 스크립트는 실행 시 **`git fetch origin main && git reset --hard origin/main`** 으로 로컬 작업 트리를 원격에 강제 동기화함. 따라서:
- **commit + push 안 한 로컬 변경은 다음 실행 시 모두 날아감**
- 작업 중이면 wrapper 중단 (launchctl unload) 후 재개

## 동작 원리

1. launchd가 스케줄 시각에 wrapper 스크립트 (`run-briefing.sh` / `run-digest.sh`) 실행
2. wrapper가:
   - `cd` 레포로 이동
   - `git fetch origin main && git reset --hard origin/main`
   - venv 확인/생성, deps 설치
   - ChatGPT 계정으로 로그인된 `codex exec` 실행
3. Codex CLI 가 `.claude/commands/{daily-report,post-market-digest}.md` 룰북을 읽어서 자동 수행
4. commit + push까지 자동

## 수동 실행 (테스트)

```bash
./scripts/launchd/run-briefing.sh
./scripts/launchd/run-digest.sh
```

## 일시 정지 / 재활성화

```bash
# 정지
launchctl unload -w ~/Library/LaunchAgents/com.yummyummyummy.k-ant-daily.briefing.plist
launchctl unload -w ~/Library/LaunchAgents/com.yummyummyummy.k-ant-daily.digest.plist

# 재개
launchctl load -w ~/Library/LaunchAgents/com.yummyummyummy.k-ant-daily.briefing.plist
launchctl load -w ~/Library/LaunchAgents/com.yummyummyummy.k-ant-daily.digest.plist
```

## 제거

```bash
for n in com.yummyummyummy.k-ant-daily.briefing com.yummyummyummy.k-ant-daily.digest; do
  launchctl unload -w ~/Library/LaunchAgents/$n.plist
  rm ~/Library/LaunchAgents/$n.plist
done
```

## 상태 확인

```bash
launchctl list | grep k-ant-daily
```

## 로그 확인

```bash
ls -t ~/Library/Logs/k-ant-daily/briefing-*.log | head -1 | xargs tail -100
ls -t ~/Library/Logs/k-ant-daily/digest-*.log | head -1 | xargs tail -100
tail ~/Library/Logs/k-ant-daily/launchd-briefing.err
```

## 문제 해결

- **스크립트 실행 안 됨**: plist syntax 에러 가능. `plutil -lint <file>.plist` 로 검증.
- **codex 명령 not found**: wrapper의 `PATH` 에 Codex CLI 경로가 포함되어 있나 확인.
- **Git push 실패**: gh/SSH 키 권한 확인.
- **Codex 인증 만료**: `codex login status` 확인 후 필요하면 `codex login` 으로 재로그인.
