"""화면 디자인: 흰 헤더 + 왼쪽 대화 패널 + 오른쪽 대시보드(알약 탭, 둥근 흰 카드, 표).

Streamlit 기본 위젯을 shadcn/ui의 Card · Badge · Button · Tabs · Alert · Dialog 모양에 맞춰 CSS로 다듬고,
위젯으로 표현하기 어려운 조각(헤더, 요약 타일, 배지, 표)은 HTML로 그린다.
HTML에 넣는 값은 모두 escape 해서 넣는다.
"""
from __future__ import annotations

from html import escape

import streamlit as st

BLUE, INK, BG, LINE, MUTED, SOFT = "#0b63ce", "#111418", "#f3f4f6", "#e5e7eb", "#6b7280", "#f6f7f9"

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&display=swap');
html, body, [class*="st-"], .stMarkdown, button, input, textarea, select {{
  font-family: "Noto Sans KR", system-ui, -apple-system, "Apple SD Gothic Neo", "Malgun Gothic", sans-serif;
}}
/* 아이콘 글꼴은 건드리지 않는다 */
[data-testid="stIconMaterial"], .material-symbols-rounded, span[class*="material"] {{
  font-family: "Material Symbols Rounded" !important;
}}
.stApp {{ background: {BG}; color: {INK}; }}
header[data-testid="stHeader"] {{ background: transparent; height: 0; }}
[data-testid="stMain"] {{ overflow-x: hidden; }}
.block-container {{ padding-top: 0 !important; max-width: 1320px; }}

/* ---------- 헤더 ---------- */
.cc-header {{ background: #fff; margin: 0 0 14px; padding: 18px 0 14px; box-shadow: 0 0 0 100vmax #fff; clip-path: inset(0 -100vmax -1px);
  display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }}
.cc-logo {{ font-size: 24px; font-weight: 900; color: {INK}; letter-spacing: -.3px; line-height: 1.2; }}
.cc-sub {{ color: {MUTED}; font-size: 13px; margin-top: 2px; }}
.cc-pills {{ display: flex; gap: 6px; flex-wrap: wrap; }}
.cc-pill {{ border: 1px solid {LINE}; background: {SOFT}; border-radius: 999px; padding: 4px 12px; font-size: 12px; color: {MUTED}; white-space: nowrap; }}
.cc-pill.on {{ background: #e8f1fd; border-color: #c9defa; color: {BLUE}; font-weight: 700; }}
.cc-pill.who {{ background: #fff; color: {INK}; font-weight: 700; }}

/* ---------- 코치 머리글 (대화 패널) ---------- */
.cc-coach {{ display: flex; align-items: center; gap: 12px; background: #fff; border: 1px solid {LINE}; border-radius: 14px; padding: 12px 14px; }}
.cc-avatar {{ width: 40px; height: 40px; border-radius: 50%; background: {BLUE}; color: #fff; font-weight: 900; display: grid; place-items: center; flex: none; }}
.cc-coach .t {{ font-weight: 900; font-size: 15px; color: {INK}; }}
.cc-coach .s {{ font-size: 12px; color: {MUTED}; }}
.cc-online {{ margin-left: auto; background: #e8f7ee; color: #1f8a4c; border-radius: 999px; padding: 3px 10px; font-size: 12px; font-weight: 700; white-space: nowrap; }}
.cc-online.off {{ background: {SOFT}; color: {MUTED}; }}

/* ---------- 요약 타일 ---------- */
.cc-tiles {{ display: grid; grid-template-columns: 1.7fr 1fr 1fr 1fr; gap: 10px; margin-bottom: 4px; }}
.cc-tile {{ background: #fff; border: 1px solid {LINE}; border-radius: 14px; padding: 12px 14px; min-width: 0; }}
.cc-tile .k {{ font-size: 12px; color: {MUTED}; }}
.cc-tile .v {{ font-size: 20px; font-weight: 900; color: {INK}; line-height: 1.3; word-break: keep-all; }}
.cc-tile .n {{ font-size: 12px; color: {MUTED}; }}
.cc-tile.main .v {{ color: {BLUE}; }}
@media (max-width: 760px) {{ .cc-tiles {{ grid-template-columns: 1fr 1fr; }} }}

/* ---------- 카드 안 제목 ---------- */
.cc-sh {{ margin: 2px 0 10px; }}
.cc-sh h2 {{ font-size: 18px !important; font-weight: 900 !important; color: {INK}; margin: 0; padding: 0; }}
.cc-sh span {{ font-size: 12px; color: {MUTED}; }}
.cc-label {{ font-size: 12px; font-weight: 700; color: {BLUE}; margin: 14px 0 6px; }}
.cc-rank {{ display: flex; align-items: baseline; gap: 10px; margin: 6px 0 8px; flex-wrap: wrap; }}
.cc-rank .r {{ color: {BLUE}; font-weight: 900; font-size: 15px; }}
.cc-rank .n {{ font-size: 26px; font-weight: 900; color: {INK}; letter-spacing: -.3px; }}
.cc-box {{ background: {SOFT}; border-radius: 10px; padding: 12px 14px; font-size: 14px; line-height: 1.65; margin: 6px 0; }}
.cc-box b {{ color: {INK}; }}
.cc-box.blue {{ background: #e8f1fd; }}
.cc-box.green {{ background: #e6f6ec; }}
.cc-box.red {{ background: #fde8e8; }}
.cc-box .h {{ font-size: 12px; font-weight: 700; margin-bottom: 2px; }}
.cc-box.green .h {{ color: #1f8a4c; }} .cc-box.red .h {{ color: #c53030; }} .cc-box.blue .h {{ color: {BLUE}; }}
.cc-kv {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px 18px; margin: 8px 0; }}
.cc-kv .k {{ font-size: 12px; color: {MUTED}; }}
.cc-kv .v {{ font-size: 14px; color: {INK}; font-weight: 500; }}
@media (max-width: 760px) {{ .cc-kv {{ grid-template-columns: 1fr; }} }}

/* ---------- 배지 ---------- */
.cc-badge {{ display: inline-block; border-radius: 999px; padding: 2px 10px; font-size: 12px; font-weight: 700; margin-right: 6px; white-space: nowrap; }}
.cc-badge.navy {{ background: {INK}; color: #fff; }}
.cc-badge.best {{ background: {BLUE}; color: #fff; }}
.cc-badge.sky {{ background: #e8f1fd; color: {BLUE}; }}
.cc-badge.warn {{ background: #fdf3e4; color: #b56a0f; }}
.cc-badge.good {{ background: #e6f6ec; color: #1f8a4c; }}
.cc-badge.mute {{ background: {SOFT}; color: {MUTED}; }}
.cc-card-title {{ font-size: 16px; font-weight: 900; color: {INK}; margin: 6px 0 2px; }}
.cc-meta {{ font-size: 12px; color: {MUTED}; }}
.cc-foot {{ text-align: center; color: {MUTED}; font-size: 12px; padding: 28px 0 12px; }}

/* ---------- 표 ---------- */
.cc-table {{ width: 100%; border-collapse: separate; border-spacing: 0; font-size: 13px; border: 1px solid {LINE}; border-radius: 10px; overflow: hidden; margin: 6px 0; }}
.cc-table th {{ background: {SOFT}; color: {MUTED}; font-weight: 700; text-align: left; padding: 9px 12px; border-bottom: 1px solid {LINE}; white-space: nowrap; }}
.cc-table td {{ padding: 10px 12px; border-bottom: 1px solid {LINE}; background: #fff; vertical-align: top; line-height: 1.55; }}
.cc-table tr:last-child td {{ border-bottom: 0; }}
.cc-table td:first-child {{ white-space: nowrap; }}
.cc-table a {{ color: {BLUE}; text-decoration: none; font-weight: 700; }}
.cc-scroll {{ overflow-x: auto; }}
.stMarkdown table:not(.cc-table) {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
.stMarkdown table:not(.cc-table) th {{ background: {SOFT}; color: {MUTED}; font-weight: 700; padding: 8px 10px; border: 1px solid {LINE}; }}
.stMarkdown table:not(.cc-table) td {{ padding: 8px 10px; border: 1px solid {LINE}; background: #fff; }}

/* ---------- 카드 (테두리 컨테이너) ---------- */
[data-testid="stVerticalBlockBorderWrapper"], [class*="st-key-card"] {{
  background: #fff; border: 1px solid {LINE} !important; border-radius: 14px !important; box-shadow: 0 1px 2px rgba(16,24,40,.04); }}
[data-testid="stExpander"] details {{ background: #fff; border: 1px solid {LINE}; border-radius: 12px; }}
[data-testid="stForm"] {{ background: #fff; border: 1px solid {LINE}; border-radius: 14px; }}

/* ---------- 탭 = 알약 메뉴 ---------- */
[role="tablist"] {{ gap: 8px; border: 0 !important; padding: 2px 0 10px; flex-wrap: wrap; }}
[data-testid="stTab"] {{ border-radius: 999px !important; padding: 7px 16px !important; background: #fff; border: 1px solid {LINE} !important; cursor: pointer; height: auto !important; }}
[data-testid="stTab"] p {{ font-size: 14px; font-weight: 700; color: {INK}; }}
[data-testid="stTab"]:hover {{ border-color: {BLUE} !important; }}
[data-testid="stTab"][aria-selected="true"] {{ background: {BLUE}; border-color: {BLUE} !important; }}
[data-testid="stTab"][aria-selected="true"] p {{ color: #fff; }}
[role="tablist"] > :not([data-testid="stTab"]) {{ display: none; }}
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {{ display: none; }}

.react-aria-SelectionIndicator {{ display: none !important; }}
[role="tablist"]::before, [role="tablist"]::after, [data-testid="stTab"]::before, [data-testid="stTab"]::after {{ display: none !important; }}
[data-testid="stTab"] {{ border-bottom: 1px solid {LINE} !important; }}
[data-testid="stTab"][aria-selected="true"] {{ border-bottom-color: {BLUE} !important; }}

/* 좁은 화면: 대화 패널을 위에, 대시보드를 아래에 쌓는다 */
@media (max-width: 900px) {{
  [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .cc-coach) {{ flex-direction: column; }}
  [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .cc-coach) > [data-testid="stColumn"] {{ width: 100% !important; min-width: 100% !important; flex: 1 1 100% !important; }}
  [class*="st-key-cardchat"] {{ height: 340px !important; }}
}}

/* ---------- 버튼 ---------- */
.stButton > button, .stDownloadButton > button, .stLinkButton > a, [data-testid="stFormSubmitButton"] > button {{
  border-radius: 999px; border: 1px solid {LINE}; background: #fff; color: {INK}; font-weight: 700; box-shadow: none; }}
.stButton > button:hover, .stDownloadButton > button:hover, .stLinkButton > a:hover, [data-testid="stFormSubmitButton"] > button:hover {{
  border-color: {BLUE}; color: {BLUE}; background: #f3f8fe; }}
button[kind="primary"], [data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"] {{
  background: {BLUE} !important; border-color: {BLUE} !important; color: #fff !important; }}
button[kind="primary"]:hover, [data-testid="stBaseButton-primary"]:hover, [data-testid="stBaseButton-primaryFormSubmit"]:hover {{
  background: #084fa6 !important; border-color: #084fa6 !important; color: #fff !important; }}

/* ---------- 입력 ---------- */
[data-baseweb="input"], [data-baseweb="textarea"], [data-baseweb="select"] > div {{ border-radius: 10px !important; border-color: {LINE} !important; background: #fff !important; }}
[data-baseweb="input"]:focus-within, [data-baseweb="textarea"]:focus-within {{ border-color: {BLUE} !important; box-shadow: 0 0 0 3px rgba(11,99,206,.15); }}
label p {{ font-size: 12px !important; font-weight: 500; color: {MUTED}; }}

/* ---------- 사이드바 ---------- */
[data-testid="stSidebar"] {{ background: #fff; border-right: 1px solid {LINE}; }}
[data-testid="stSidebar"] h2 {{ font-size: 16px; font-weight: 900; color: {INK}; }}

/* ---------- 대화: 코치는 밝은 말풍선, 사용자는 검은 말풍선(오른쪽) ---------- */
[data-testid="stChatMessage"] {{ background: {SOFT}; border: 0; border-radius: 14px; padding: 10px 14px; gap: 0; max-width: 94%; font-size: 14px; }}
[data-testid="stChatMessage"] [data-testid^="stChatMessageAvatar"], [data-testid="stChatMessage"] > img {{ display: none; }}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {{ background: {INK}; margin-left: auto; width: fit-content; }}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) p {{ color: #fff; }}
[data-testid="stChatMessage"] table {{ display: block; overflow-x: auto; }}
[data-testid="stChatMessage"] th, [data-testid="stChatMessage"] td {{ white-space: nowrap; font-size: 12px; padding: 6px 8px !important; }}
[data-testid="stChatMessage"] {{ overflow-wrap: anywhere; }}
[data-testid="stChatMessageContent"] {{ min-width: 0; }}
[data-testid="stChatInput"] {{ border-radius: 14px; border: 1px solid {LINE}; background: #fff; }}

/* 대화 패널은 대시보드를 내려도 따라온다 (넓은 화면에서만) */
@media (min-width: 900px) {{ [data-testid="stColumn"]:has(> div .cc-coach):not(:has([data-testid="stColumn"] .cc-coach)) {{ position: sticky; top: 10px; align-self: flex-start; }} }}

/* ---------- 알림 · 진행 막대 ---------- */
[data-testid="stAlert"] {{ border-radius: 10px; border: 0; }}
[data-testid="stProgress"] > div > div > div > div {{ background: {BLUE}; }}
div[role="dialog"] {{ border-radius: 16px; }}
</style>
"""


def inject() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def header(pills: list[tuple[str, bool]], today: str, user: str | None) -> None:
    pill_html = "".join(f'<span class="cc-pill{" on" if on else ""}">{escape(label)}</span>' for label, on in pills)
    who = f"{escape(user)}님 · 자동 저장" if user else "로그인 전 · 창을 닫으면 사라져요"
    st.markdown(
        '<div class="cc-header"><div><div class="cc-logo">자격증 패스 코치</div>'
        '<div class="cc-sub">처음 자격증 준비를 시작하는 분을 위한 대화형 코치</div></div>'
        f'<div class="cc-pills">{pill_html}<span class="cc-pill">오늘 {escape(today)}</span><span class="cc-pill who">{who}</span></div></div>',
        unsafe_allow_html=True)


def coach_head(online: bool) -> None:
    badge = '<span class="cc-online">AI 연결됨</span>' if online else '<span class="cc-online off">규칙 기반</span>'
    st.markdown('<div class="cc-coach"><div class="cc-avatar">코</div><div><div class="t">자격증 패스 코치</div>'
                f'<div class="s">추천 · 일정 · 학습 경로 · 진도 관리</div></div>{badge}</div>', unsafe_allow_html=True)


def tiles(items: list[tuple[str, str, str]]) -> None:
    """요약 타일. items: (라벨, 값, 보조 설명) — 첫 칸이 넓다."""
    cells = "".join(f'<div class="cc-tile{" main" if i == 0 else ""}"><div class="k">{escape(k)}</div><div class="v">{escape(v)}</div>'
                    f'<div class="n">{escape(n)}</div></div>' for i, (k, v, n) in enumerate(items))
    st.markdown(f'<div class="cc-tiles">{cells}</div>', unsafe_allow_html=True)


def section(title: str, note: str = "") -> None:
    st.markdown(f'<div class="cc-sh"><h2>{escape(title)}</h2><span>{escape(note)}</span></div>', unsafe_allow_html=True)


def label(text: str) -> None:
    st.markdown(f'<div class="cc-label">{escape(text)}</div>', unsafe_allow_html=True)


def rank(tag: str, name: str) -> None:
    st.markdown(f'<div class="cc-rank"><span class="r">{escape(tag)}</span><span class="n">{escape(name)}</span></div>',
                unsafe_allow_html=True)


def box(text: str, kind: str = "", head: str = "") -> None:
    """부드러운 색 상자. kind: "" | blue | green | red"""
    head_html = f'<div class="h">{escape(head)}</div>' if head else ""
    st.markdown(f'<div class="cc-box {kind}">{head_html}{escape(text)}</div>', unsafe_allow_html=True)


def kv(pairs: list[tuple[str, str]]) -> None:
    cells = "".join(f'<div><div class="k">{escape(k)}</div><div class="v">{escape(v or "미확인")}</div></div>' for k, v in pairs)
    st.markdown(f'<div class="cc-kv">{cells}</div>', unsafe_allow_html=True)


def badges(items: list[tuple[str, str]]) -> str:
    return "".join(f'<span class="cc-badge {kind}">{escape(text)}</span>' for text, kind in items)


def table(headers: list[str], rows: list[list]) -> None:
    """HTML 표. 칸 값이 (글자, 종류) 튜플이면 배지로, ("link", 글자, 주소)면 링크로 그린다."""
    def cell(value) -> str:
        if isinstance(value, tuple) and len(value) == 3 and value[0] == "link":
            url = value[2] if str(value[2]).startswith(("https://", "http://")) else "#"
            return f'<a href="{escape(url, quote=True)}" target="_blank" rel="noopener">{escape(value[1])}</a>'
        if isinstance(value, tuple):
            return badges([value])
        return escape(str(value if value not in (None, "") else "—"))
    head = "".join(f"<th>{escape(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell(v)}</td>" for v in row) + "</tr>" for row in rows)
    st.markdown(f'<div class="cc-scroll"><table class="cc-table"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>',
                unsafe_allow_html=True)


def card_head(badge_items: list[tuple[str, str]], title: str, meta: str) -> None:
    st.markdown(f'{badges(badge_items)}<div class="cc-card-title">{escape(title)}</div><div class="cc-meta">{meta}</div>',
                unsafe_allow_html=True)


def footer(text: str) -> None:
    st.markdown(f'<div class="cc-foot">{escape(text)}</div>', unsafe_allow_html=True)
