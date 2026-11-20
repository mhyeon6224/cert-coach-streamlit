# 자격증 패스 코치 (Streamlit)

처음 자격증을 준비하는 사람에게 **추천 → 공식 일정 확인 → 학습 경로 → 주차별 계획 → 체크인·재조정 → 결과 반영 → 다음 자격증**을 하나의 대화 흐름으로 이어 주는 코치입니다. 예선 스킬(`certificate-path-coach`)과 최종 PRD의 규칙을 Streamlit 앱으로 옮겼습니다.

## 기능

| PRD | 기능 | 위치 |
| --- | --- | --- |
| P0-1 | 조건 기반 1순위 + 대안 추천, 누락 조건만 질문 | 대화 / 추천 탭 |
| P0-2 | 주관기관 공식 사이트만 검색 → 날짜를 본문과 대조 → 확정됨·확인 필요·못 함 구분 | 대화 / 일정 탭 |
| P0-3 | 비용 선호에 맞춘 기본 경로 + 대안, 후기는 2곳 이상 반복된 의견만 | 대화 |
| P0-4 | 주차별 계획(개념 40/문제풀이 25/기출 25/모의·복습 10), 오늘 브리핑, 지연 3일·50% 기준 재조정 | 대화 / 계획 탭 |
| P1 | 동의 기반 캘린더 등록(Google Calendar·.ics), Notion 학습 공간 만들기, 합격 후 다음 경로, 불합격 시 부족 단계 보강 계획, 조건 변경 반영, 유효기간 관리(선택), 취업 가이드라인(조건부) | 각 탭 |

화면은 왼쪽 대화 패널 + 오른쪽 대시보드(대화·추천·일정·계획·프로필·기능 탭)로 나뉘고, 결과는 카드와 표로 정리됩니다.

## 연동 (모두 사용자 본인 계정, 동의 후에만)

- **Google Calendar** — 사용자가 본인 Google 계정으로 동의하면 고른 일정만 본인 캘린더에 등록합니다(권한: 일정 만들기). 운영자가 `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`(배포된 앱 주소)를 Secrets에 넣어야 켜집니다. 설정 전에는 '일정 추가 화면 열기' 링크와 .ics 파일이 대신 동작합니다.
- **Notion** — 계획 탭의 'Notion에 만들기'에서 본인 Internal Integration 토큰과 페이지 링크를 넣으면 그 페이지 아래에 학습 공간을 만듭니다. 토큰은 브라우저 세션에만 두고 DB에 저장하지 않습니다.

## 로컬 실행

```bash
pip install -r requirements.txt
```

```bash
streamlit run app.py
```

접속 비밀번호는 `pnumis` 입니다. API 키가 없어도 규칙 기반으로 동작하고, 키를 넣으면 AI 추천과 공식 일정 확인이 켜집니다.

## API 키 (선택)

`.streamlit/secrets.toml.example`을 `.streamlit/secrets.toml`로 복사해 값을 채웁니다. 이 파일은 git에 올라가지 않습니다.

| 이름 | 용도 |
| --- | --- |
| `GROQ_API_KEY` | AI 모델 (기본 Groq, OpenAI 호환) |
| `TAVILY_API_KEY` | 공식 일정·학습자료 웹 검색 |
| `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` | Groq 대신 다른 OpenAI 호환 모델(예: Upstage Solar)을 쓸 때 |
| `APP_PASSWORD` | 접속 비밀번호 (기본 `pnumis`) |
| `SUPABASE_URL` / `SUPABASE_KEY` | 계정·학습 상태 저장 (아래 참고) |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `GOOGLE_REDIRECT_URI` | 사용자별 Google Calendar 연동 |

## 계정과 저장소 (다시 접속해도 이어서 하기)

사이드바 "내 계정"에서 닉네임·비밀번호로 계정을 만들면 조건·계획·대화가 자동 저장됩니다. 비밀번호는 해시로만 저장합니다.

- `SUPABASE_URL`, `SUPABASE_KEY`(service_role)를 Secrets에 넣으면 Supabase DB에 저장되어 재배포·절전 뒤에도 유지됩니다. 테이블 생성 SQL은 `supabase_setup.sql`에 있습니다. 이 키는 DB 전체 권한이 있으므로 Secrets에만 넣고 저장소에 올리지 않습니다.
- 없으면 앱 서버의 SQLite 파일에 저장합니다. 로컬에서는 유지되지만 Streamlit Cloud에서는 앱이 재시작되면 지워집니다.

## 공식 일정 수집 방식

1. 일정표가 HTML에 그대로 있는 사이트(데이터자격시험: SQLD·SQLP·ADsP·빅데이터분석기사, TOEIC)는 `coach/crawl.py`가 페이지를 직접 읽어 파싱합니다. 키가 필요 없습니다.
2. 화면을 자바스크립트로 그리는 사이트(Q-Net 등)는 공식 도메인 한정 검색 + AI 추출 + 본문 대조로 확인합니다. Tavily·LLM 키가 필요합니다.

## 배포 (GitHub → Streamlit Community Cloud)

1. 이 폴더를 GitHub 저장소로 올립니다. (`app.py`와 `requirements.txt`가 저장소 최상위에 있어야 합니다.)
2. https://share.streamlit.io 에서 GitHub 계정으로 로그인 → **Create app** → 저장소·브랜치·`app.py` 선택
3. **Advanced settings → Secrets**에 `secrets.toml` 내용을 붙여 넣고 Deploy
4. 발급된 `https://<앱이름>.streamlit.app` 주소를 과제 파워포인트에 넣습니다.

## 구조

```
app.py                 화면 (비밀번호, 대화 패널, 6개 탭 대시보드)
coach/ui.py            디자인 (CSS, 헤더·타일·배지·표)
coach/router.py        발화 → 실행 모드(A~G) 판별, 상태 갱신, 동의 처리
coach/engine.py        추천 · 공식 일정 · 학습 경로 · 취업 가이드라인 · 유효기간
coach/plan.py          계획 생성 · 체크인 · 재조정 · 결과 반영 · .ics / .md 내보내기
coach/catalog.py       자격증 카탈로그 + 참고자료 로더
coach/services.py      LLM · 검색 연결 (키는 서버에서만 사용)
coach/crawl.py         공식 일정 페이지 직접 수집
coach/storage.py       계정 · 학습 상태 저장 (Supabase / SQLite)
coach/gcal.py          사용자별 Google Calendar 연동 (OAuth)
coach/notion.py        사용자별 Notion 학습 공간 만들기
data/                  공공데이터 참고자료 (국가자격 종목·시험정보 2025-12-31, 공인민간자격 2026-08-26)
```

## 데이터 규칙

- 일정·응시료는 공식 페이지 본문과 대조된 값만 표시하고, 나머지는 "미확인"으로 둡니다.
- 참고자료 CSV는 공식 원문을 읽지 못했을 때만 "자료집 기준"으로 씁니다.
- 계획 저장·캘린더 파일·보유 자격증 추가·정보 파일 저장은 사용자가 동의한 뒤에만 실행합니다.
- 계정을 만들지 않으면 입력한 내용은 브라우저 세션에만 있습니다. 계정을 만들면(저장 동의 필요) 조건·계획·대화가 DB에 저장되고, 비밀번호는 해시로만 저장합니다.
