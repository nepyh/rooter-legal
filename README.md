# rooter-legal

루터(rooter) 서비스 약관·정책 게시용 정적 사이트.

- 원본: `src/<slug>/<version>.md` (front matter 의 `code`/`version`/`title`/`effective_date` 가 경로와 일치해야 함)
- 생성: `python3 tools/render_html.py` → `<slug>/<version>/index.html` + 루트 `index.html` 커밋
- CI: `python3 tools/render_html.py --check` 가 생성물과 커밋본이 다르면 실패

약관을 개정할 때는 기존 `index.html` 을 고치지 않고 새 `<version>` 디렉터리를 추가한다.
