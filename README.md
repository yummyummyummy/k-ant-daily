# k-ant-daily

매일 장 열리기 전, 내 관심 종목과 관련된 뉴스를 모아서 정리해주는 브리핑 페이지를 자동 생성합니다.
로컬 Claude Code(Max 구독)로 분석하고, GitHub Pages로 정적 배포합니다.

**공개 URL:** https://yummyummyummy.github.io/k-ant-daily/

## 하루 사용 흐름

1. Claude Code를 이 레포에서 실행한다.
2. `/daily-report` 슬래시 커맨드를 입력한다.
3. Claude가 뉴스 수집 → 요약 → HTML 생성 → 커밋/푸시까지 실행한다.
4. 생성된 URL을 카카오톡으로 공유한다.

## 구성

- `stocks.yml` — 대상 종목 리스트. 수정하면 다음 실행부터 반영.
- `scripts/fetch_news.py` — 네이버 금융에서 종목별 뉴스·공시·거시 뉴스·지수·환율 수집 → `.tmp/news.json`.
- `scripts/render.py` — 요약 JSON → Jinja2 템플릿 → `docs/YYYY-MM-DD.html` + `index.html` + `archive.html`.
- `templates/report.html.j2` — 리포트 템플릿 (모바일 우선, OG 태그, 다크 모드 대응).
- `templates/archive.html.j2` — 아카이브 목록 템플릿.
- `.claude/commands/daily-report.md` — 요약 스키마 + 실행 단계를 정의한 슬래시 커맨드.

## 수동 실행 (Claude 없이 테스트용)

```bash
source .venv/bin/activate
python scripts/fetch_news.py
# .tmp/summary.json 을 수동으로 작성한 뒤
python scripts/render.py .tmp/summary.json
open docs/index.html
```

## 주의

- 자동 생성 리포트이며 투자 권유가 아닙니다.
- 뉴스 원문의 해석/요약은 LLM이 수행하므로, 중요한 판단은 반드시 원문 링크를 확인하세요.
