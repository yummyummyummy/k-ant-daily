# Local scheduling with launchd (macOS)

Mac mini에서 24/7 돌리는 용도. cron 대신 launchd 사용 — 슬립에서 깨울 수 있고 macOS 표준 방식.

## 한 번에 설치

```bash
./scripts/launchd/install.sh
```

세 개의 LaunchAgent가 설치됨:
- `com.yummyummyummy.k-ant-daily.briefing` — 평일 **07:30 KST** `/daily-report` (아침 예측)
- `com.yummyummyummy.k-ant-daily.review`   — 평일 **20:10 KST** `/daily-review` (저녁 회고)
- `com.yummyummyummy.k-ant-daily.refresh`  — 평일 **09:00~15:30 KST 10분 주기** (장중 뉴스·시세 새로고침)

refresh 는 LLM 을 돌리지 않고 `fetch_news.py` + `render.py` 만 재실행 — 아침 브리핑 분석(rationale / key_points)은 그대로, `news` 블록 / `latest_news_ago` 칩 / intraday 가격만 갱신. launchd 는 10분 간격으로 항상 뜨지만 wrapper 가 장외 시간이면 즉시 exit.

로그는 `~/Library/Logs/k-ant-daily/` 에 누적됨 (실행당 한 파일).

## 동작 원리

1. launchd가 스케줄 시각에 wrapper 스크립트 (`run-briefing.sh` / `run-review.sh`) 실행
2. wrapper가:
   - `cd` 레포로 이동
   - `git fetch origin main && git reset --hard origin/main` — 원격 최신 상태로 동기화
   - venv 확인/생성, deps 설치
   - `claude --dangerously-skip-permissions --print "/daily-report"` (또는 review) 실행
3. Claude Code가 `.claude/commands/{daily-report,daily-review}.md` 읽어서 전 과정 자동 수행
4. commit + push까지 자동

## 시간대 참고

`StartCalendarInterval` 은 Mac의 **로컬 시간대** 를 사용. `date` 명령으로 `KST` 나오면 OK.

```bash
date            # Mon Apr 21 07:30:00 KST 2026 이런 식
systemsetup -gettimezone   # Time Zone: Asia/Seoul
```

Mac을 여행 중 다른 시간대로 변경하면 launchd 스케줄도 그 시간대 기준으로 동작하므로 주의.

## 슬립 상태에서 깨우기

launchd 자체는 슬립에서 Mac을 깨우지 **않음**. Mac이 슬립이면 schedule이 미실행되고, 깨어난 직후 한 번 실행됨 (catchup 기능).

24/7 깨어있게 하려면:
1. **시스템 설정 → 배터리 → 잠자기 방지** (iMac/MBP) 또는
2. **`pmset` 로 스케줄된 wake 설정** — Mac mini는 AC 전원이라 기본적으로 sleep 안 함

Mac mini는 보통 기본 설정으로도 sleep 안 하니 대개 문제 없음.

## 수동 실행 (테스트)

```bash
./scripts/launchd/run-briefing.sh    # 즉시 실행 (로그는 ~/Library/Logs/k-ant-daily/)
```

## 일시 정지 / 재활성화

```bash
# 정지
launchctl unload -w ~/Library/LaunchAgents/com.yummyummyummy.k-ant-daily.briefing.plist
launchctl unload -w ~/Library/LaunchAgents/com.yummyummyummy.k-ant-daily.review.plist

# 재개
launchctl load -w ~/Library/LaunchAgents/com.yummyummyummy.k-ant-daily.briefing.plist
launchctl load -w ~/Library/LaunchAgents/com.yummyummyummy.k-ant-daily.review.plist
```

## 제거

```bash
for n in com.yummyummyummy.k-ant-daily.briefing com.yummyummyummy.k-ant-daily.review; do
  launchctl unload -w ~/Library/LaunchAgents/$n.plist
  rm ~/Library/LaunchAgents/$n.plist
done
```

## 상태 확인

```bash
launchctl list | grep k-ant-daily
```

다음 예정 실행 시각은 launchd 내부에만 저장되고 명령행으론 직접 못 봄. 로그 파일 타임스탬프 + 실제 실행 여부로 판단.

## 로그 확인

```bash
# 최근 briefing 로그
ls -t ~/Library/Logs/k-ant-daily/briefing-*.log | head -1 | xargs tail -100

# 최근 review 로그
ls -t ~/Library/Logs/k-ant-daily/review-*.log | head -1 | xargs tail -100

# launchd 자체 stderr (plist 파싱 에러 등)
tail ~/Library/Logs/k-ant-daily/launchd-briefing.err
```

## 문제 해결

- **스크립트 실행 안 됨**: plist syntax 에러 가능. `plutil -lint <file>.plist` 로 검증.
- **claude 명령 not found**: wrapper의 `PATH` 에 Node가 포함되어 있나 확인. `which claude` 결과 경로와 같아야 함.
- **Git push 실패**: Mac의 gh/SSH 키가 push 권한 있는지 확인. 처음엔 수동으로 `git push` 한 번 돌려 credentials cache 쌓기.
- **Claude 인증 만료**: `claude` 명령 수동 실행 한 번으로 재로그인.

## 클라우드 트리거와 병행하지 말 것

`claude.ai/code/scheduled` 에 등록된 원격 트리거가 있으면 중복 실행됨. 로컬로 옮길 땐 원격 트리거를 **disable** (또는 삭제) 하세요.
