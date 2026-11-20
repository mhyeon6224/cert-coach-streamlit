"""화면 디자인: 흰 헤더 + 왼쪽 대화 패널 + 오른쪽 대시보드(각진 탭, 얇은 테두리 흰 카드, 표) · 네이비 계열.

Streamlit 기본 위젯을 shadcn/ui의 Card · Badge · Button · Tabs · Alert · Dialog 모양에 맞춰 CSS로 다듬고,
위젯으로 표현하기 어려운 조각(헤더, 요약 타일, 배지, 표)은 HTML로 그린다.
HTML에 넣는 값은 모두 escape 해서 넣는다.
"""
from __future__ import annotations

import base64
from html import escape
from pathlib import Path

import streamlit as st

BLUE, INK, BG, LINE, MUTED, SOFT = "#123a6b", "#1d2733", "#f5f7fa", "#dde4ec", "#66737f", "#f3f6f9"
SEA, R = "#1f73c4", "2px"  # 강조색, 모서리 반경(각진 모양)

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Gaegu:wght@700&family=Jua&family=Noto+Sans+KR:wght@400;500;700;900&display=swap');
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
.cc-pill {{ border: 1px solid {LINE}; background: {SOFT}; border-radius: {R}; padding: 4px 12px; font-size: 12px; color: {MUTED}; white-space: nowrap; }}
.cc-pill.on {{ background: #e8f1fb; border-color: #c7dcf3; color: {BLUE}; font-weight: 700; }}
.cc-pill.who {{ background: #fff; color: {INK}; font-weight: 700; }}

/* ---------- 코치 머리글 (대화 패널) ---------- */
.cc-coach {{ display: flex; align-items: center; gap: 12px; background: #fff; border: 1px solid {LINE}; border-radius: {R}; padding: 12px 14px; }}
.cc-avatar {{ width: 40px; height: 40px; border-radius: {R}; background: {BLUE}; color: #fff; font-weight: 900; display: grid; place-items: center; flex: none; }}
.cc-coach .t {{ font-weight: 900; font-size: 15px; color: {INK}; }}
.cc-coach .s {{ font-size: 12px; color: {MUTED}; }}
.cc-online {{ margin-left: auto; background: #e8f7ee; color: #1f8a4c; border-radius: {R}; padding: 3px 10px; font-size: 12px; font-weight: 700; white-space: nowrap; }}
.cc-online.off {{ background: {SOFT}; color: {MUTED}; }}

/* ---------- 요약 타일 ---------- */
.cc-tiles {{ display: grid; grid-template-columns: 1.7fr 1fr 1fr 1fr; gap: 10px; margin-bottom: 4px; }}
.cc-tile {{ background: #fff; border: 1px solid {LINE}; border-radius: {R}; padding: 12px 14px; min-width: 0; }}
.cc-tile .k {{ font-size: 12px; color: {MUTED}; }}
.cc-tile .v {{ font-size: 20px; font-weight: 900; color: {INK}; line-height: 1.3; word-break: keep-all; }}
.cc-tile .n {{ font-size: 12px; color: {MUTED}; }}
.cc-tile.main .v {{ color: {BLUE}; }}
@media (max-width: 760px) {{ .cc-tiles {{ grid-template-columns: 1fr 1fr; }} }}

/* ---------- 카드 안 제목 ---------- */
.cc-sh {{ margin: 2px 0 10px; }}
.cc-sh h2 {{ font-size: 18px !important; font-weight: 900 !important; color: {INK}; margin: 0; padding: 0; }}
.cc-sh > span {{ font-size: 12px; color: {MUTED}; }}
.cc-label {{ font-size: 12px; font-weight: 700; color: {BLUE}; margin: 14px 0 6px; }}
.cc-rank {{ display: flex; align-items: baseline; gap: 10px; margin: 6px 0 8px; flex-wrap: wrap; }}
.cc-rank .r {{ color: {BLUE}; font-weight: 900; font-size: 15px; }}
.cc-rank .n {{ font-size: 26px; font-weight: 900; color: {INK}; letter-spacing: -.3px; }}
.cc-box {{ background: {SOFT}; border-radius: {R}; padding: 12px 14px; font-size: 14px; line-height: 1.65; margin: 6px 0; }}
.cc-box b {{ color: {INK}; }}
.cc-box.blue {{ background: #e8f1fb; }}
.cc-box.green {{ background: #e6f6ec; }}
.cc-box.red {{ background: #fde8e8; }}
.cc-box .h {{ font-size: 12px; font-weight: 700; margin-bottom: 2px; }}
.cc-box.green .h {{ color: #1f8a4c; }} .cc-box.red .h {{ color: #c53030; }} .cc-box.blue .h {{ color: {BLUE}; }}
.cc-kv {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px 18px; margin: 8px 0; }}
.cc-kv .k {{ font-size: 12px; color: {MUTED}; }}
.cc-kv .v {{ font-size: 14px; color: {INK}; font-weight: 500; }}
@media (max-width: 760px) {{ .cc-kv {{ grid-template-columns: 1fr; }} }}

/* ---------- 배지 ---------- */
.cc-badge {{ display: inline-block; border-radius: {R}; padding: 2px 10px; font-size: 12px; font-weight: 700; margin-right: 6px; white-space: nowrap; }}
.cc-badge.navy {{ background: {INK}; color: #fff; }}
.cc-badge.best {{ background: {BLUE}; color: #fff; }}
.cc-badge.sky {{ background: #e8f1fb; color: {BLUE}; }}
.cc-badge.warn {{ background: #fdf3e4; color: #b56a0f; }}
.cc-badge.good {{ background: #e6f6ec; color: #1f8a4c; }}
.cc-badge.mute {{ background: {SOFT}; color: {MUTED}; }}
.cc-card-title {{ font-size: 16px; font-weight: 900; color: {INK}; margin: 6px 0 2px; }}
.cc-meta {{ font-size: 12px; color: {MUTED}; }}
.cc-foot {{ text-align: center; color: {MUTED}; font-size: 12px; padding: 28px 0 12px; }}

/* ---------- 표 ---------- */
.cc-table {{ width: 100%; border-collapse: separate; border-spacing: 0; font-size: 13px; border: 1px solid {LINE}; border-radius: {R}; overflow: hidden; margin: 6px 0; }}
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
  background: #fff; border: 1px solid {LINE} !important; border-radius: {R} !important; box-shadow: 0 1px 2px rgba(16,24,40,.04); }}
[data-testid="stExpander"] details {{ background: #fff; border: 1px solid {LINE}; border-radius: {R}; }}
[data-testid="stForm"] {{ background: #fff; border: 1px solid {LINE}; border-radius: {R}; }}

/* ---------- 탭 = 알약 메뉴 ---------- */
[role="tablist"] {{ gap: 8px; border: 0 !important; padding: 2px 0 10px; flex-wrap: wrap; }}
[data-testid="stTab"] {{ border-radius: {R} !important; padding: 7px 16px !important; background: #fff; border: 1px solid {LINE} !important; cursor: pointer; height: auto !important; }}
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
  border-radius: {R}; border: 1px solid {LINE}; background: #fff; color: {INK}; font-weight: 700; box-shadow: none; }}
.stButton > button:hover, .stDownloadButton > button:hover, .stLinkButton > a:hover, [data-testid="stFormSubmitButton"] > button:hover {{
  border-color: {BLUE}; color: {BLUE}; background: #eef3f8; }}
button[kind="primary"], [data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"] {{
  background: {BLUE} !important; border-color: {BLUE} !important; color: #fff !important; }}
button[kind="primary"]:hover, [data-testid="stBaseButton-primary"]:hover, [data-testid="stBaseButton-primaryFormSubmit"]:hover {{
  background: #0c2a4f !important; border-color: #0c2a4f !important; color: #fff !important; }}

/* ---------- 입력 ---------- */
[data-baseweb="input"], [data-baseweb="textarea"], [data-baseweb="select"] > div {{ border-radius: {R} !important; border-color: {LINE} !important; background: #fff !important; }}
[data-baseweb="input"]:focus-within, [data-baseweb="textarea"]:focus-within {{ border-color: {BLUE} !important; box-shadow: 0 0 0 3px rgba(18,58,107,.18); }}
label p {{ font-size: 12px !important; font-weight: 500; color: {MUTED}; }}

/* ---------- 사이드바 ---------- */
[data-testid="stSidebar"] {{ background: #fff; border-right: 1px solid {LINE}; }}
[data-testid="stSidebar"] h2 {{ font-size: 16px; font-weight: 900; color: {INK}; }}

/* ---------- 대화: 코치는 밝은 말풍선, 사용자는 검은 말풍선(오른쪽) ---------- */
[data-testid="stChatMessage"] {{ background: {SOFT}; border: 0; border-radius: {R}; padding: 10px 14px; gap: 0; max-width: 94%; font-size: 14px; }}
[data-testid="stChatMessage"] [data-testid^="stChatMessageAvatar"], [data-testid="stChatMessage"] > img {{ display: none; }}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {{ background: {INK}; margin-left: auto; width: fit-content; }}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) p {{ color: #fff; }}
[data-testid="stChatMessage"] table {{ display: block; overflow-x: auto; }}
[data-testid="stChatMessage"] th, [data-testid="stChatMessage"] td {{ white-space: nowrap; font-size: 12px; padding: 6px 8px !important; }}
[data-testid="stChatMessage"] {{ overflow-wrap: anywhere; }}
[data-testid="stChatMessageContent"] {{ min-width: 0; }}
[data-testid="stChatInput"] {{ border-radius: {R}; border: 1px solid {LINE}; background: #fff; }}

/* 대화 패널은 대시보드를 내려도 따라온다 (넓은 화면에서만) */
@media (min-width: 900px) {{ [data-testid="stColumn"]:has(> div .cc-coach):not(:has([data-testid="stColumn"] .cc-coach)) {{ position: sticky; top: 10px; align-self: flex-start; }} }}

/* ---------- 알림 · 진행 막대 ---------- */
[data-testid="stAlert"] {{ border-radius: {R}; border: 0; }}
[data-testid="stProgress"] > div > div > div > div {{ background: {BLUE}; }}
div[role="dialog"] {{ border-radius: {R}; }}

/* ================= 각진 전문가형 마감 (shadcn/ui 구성요소 대응) ================= */
/* Card */
[class*="st-key-card"], .cc-tile, .cc-coach {{ box-shadow: 0 1px 0 rgba(18,58,107,.04); }}
.cc-header {{ border-top: 3px solid {BLUE}; }}
.cc-header > div:first-child {{ padding-left: 38px; }}
.cc-logo {{ color: {BLUE}; }}
.cc-sh {{ border-bottom: 1px solid {LINE}; padding-bottom: 10px; margin-bottom: 14px; display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }}
.cc-sh h2 {{ color: {BLUE} !important; }}
.cc-tile.main {{ border-left: 3px solid {BLUE}; }}
.cc-tile .v {{ color: {INK}; }} .cc-tile.main .v {{ color: {BLUE}; }}
.cc-rank .r {{ color: {SEA}; }} .cc-label {{ color: {SEA}; letter-spacing: .2px; }}
.cc-box {{ border-left: 3px solid {LINE}; }}
.cc-box.blue {{ border-left-color: {SEA}; }} .cc-box.green {{ border-left-color: #2b9466; background: #eef7f2; }}
.cc-box.red {{ border-left-color: #c8473f; background: #fbeeed; }}
.cc-box.blue .h {{ color: {SEA}; }}
/* Badge */
.cc-badge {{ border: 1px solid transparent; padding: 1px 8px; }}
.cc-badge.best {{ background: {BLUE}; }} .cc-badge.sky {{ color: {SEA}; border-color: #c7dcf3; }}
.cc-badge.good {{ background: #eef7f2; color: #2b9466; border-color: #bfe3d0; }}
.cc-badge.warn {{ border-color: #f3d6a6; }} .cc-badge.mute {{ border-color: {LINE}; }}
.cc-online {{ background: #eef7f2; color: #2b9466; border: 1px solid #bfe3d0; }}
.cc-online.off {{ border: 1px solid {LINE}; }}
/* Table */
.cc-table th {{ background: #eef3f8; color: {BLUE}; font-size: 12px; }}
[data-testid="stDataFrame"], [data-testid="stDataEditor"] {{ border: 1px solid {LINE}; border-radius: {R}; }}
/* Tabs: 각진 메뉴 */
[role="tablist"] {{ gap: 0 !important; border-bottom: 2px solid {BLUE} !important; padding: 0 !important; margin-bottom: 12px; }}
[data-testid="stTab"] {{ border-radius: 0 !important; border: 1px solid {LINE} !important; border-bottom: 0 !important; margin-right: -1px; padding: 9px 18px !important; background: #fff; }}
[data-testid="stTab"] p {{ color: {MUTED}; }}
[data-testid="stTab"]:hover {{ background: #eef3f8; }} [data-testid="stTab"]:hover p {{ color: {BLUE}; }}
[data-testid="stTab"][aria-selected="true"] {{ background: {BLUE}; border-color: {BLUE} !important; }}
/* Button · Input · Select · Textarea: 포커스 링 */
button:focus-visible, [data-testid="stTab"]:focus-visible {{ outline: 2px solid {SEA}; outline-offset: 2px; }}
.stButton > button, .stDownloadButton > button, .stLinkButton > a, [data-testid="stFormSubmitButton"] > button {{ color: {BLUE}; min-height: 38px; }}
/* Checkbox · Switch */
[data-baseweb="checkbox"] > span:first-child {{ border-radius: {R} !important; }}
/* Accordion(Expander) */
[data-testid="stExpander"] summary {{ font-weight: 700; color: {BLUE}; }}
/* Progress */
.cc-prog {{ height: 6px; background: #e6ecf2; margin-top: 8px; }}
.cc-prog > i {{ display: block; height: 100%; background: {BLUE}; }}
/* Separator */
[data-testid="stMarkdownContainer"] hr, hr {{ border-color: {LINE}; margin: 16px 0; }}
/* Avatar · 말풍선 */
.cc-avatar {{ background: {BLUE}; }}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {{ background: {BLUE}; }}
[data-testid="stChatMessage"] {{ border: 1px solid {LINE}; background: #fff; }}
/* Dialog · Tooltip · Alert */
div[role="dialog"] {{ border: 1px solid {LINE}; box-shadow: 0 12px 32px rgba(12,42,79,.18); }}
[data-testid="stAlert"] {{ border: 1px solid {LINE}; }}

/* ================= 상단바 (GitHub형) ================= */
.cc-header, [class*="st-key-topbar"] {{ background: #f6f8fa; box-shadow: 0 0 0 100vmax #f6f8fa; clip-path: inset(0 -100vmax -1px); border-top: 0;
  border-bottom: 1px solid {LINE}; padding: 10px 0 10px; margin: 0 0 6px; }}
.cc-header > div:first-child {{ padding-left: 40px; }}
.cc-brand {{ display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding-left: 40px; min-height: 36px; }}
.cc-header .cc-brand {{ padding-left: 0; }}
.cc-mark {{ width: 30px; height: 30px; flex: none; }}
.cc-name {{ font-size: 15px; font-weight: 700; color: {INK}; }}
.cc-slash {{ color: #9aa5b1; }} .cc-page {{ font-size: 15px; font-weight: 500; color: {MUTED}; }}
.cc-brand .cc-pills {{ margin-left: 14px; }}
.cc-pill {{ background: #fff; padding: 3px 9px; }}
[class*="st-key-topbar"] [data-testid="stPopover"] button {{ border-radius: 6px !important; background: #fff; border: 1px solid #d1d9e0; color: {INK}; font-weight: 700; min-height: 34px; }}
[class*="st-key-topbar"] [data-testid="stPopover"] button [data-testid="stIconMaterial"] {{ color: {BLUE}; }}
.cc-greet {{ margin: 10px 0 12px; }}
.cc-greet h1 {{ font-size: 24px !important; font-weight: 700 !important; color: {INK}; padding: 0 !important; margin: 0 !important; }}
.cc-greet p {{ font-size: 13px; color: {MUTED}; margin: 4px 0 0; }}
.cc-prof {{ display: flex; align-items: center; gap: 12px; padding: 4px 0 10px; border-bottom: 1px solid {LINE}; margin-bottom: 10px; }}
.cc-face {{ width: 40px; height: 40px; border-radius: 50%; background: {BLUE}; color: #fff; font-weight: 700; display: grid; place-items: center; flex: none; }}
.cc-prof .t {{ font-weight: 700; color: {INK}; }} .cc-prof .s {{ font-size: 12px; color: {MUTED}; }}
.cc-avatar {{ border-radius: 50% !important; }}

/* ================= 대화 프로필 아이콘 ================= */
[data-testid="stChatMessage"] {{ gap: 10px; background: transparent !important; border: 0 !important; padding: 4px 0; max-width: 100%; align-items: flex-start; }}
[data-testid="stChatMessage"] [data-testid^="stChatMessageAvatar"] {{ display: flex !important; width: 32px; height: 32px; border-radius: 50% !important;
  background: {BLUE} !important; color: #fff !important; flex: none; align-items: center; justify-content: center; border: 0; }}
[data-testid="stChatMessage"] [data-testid^="stChatMessageAvatar"] * {{ color: #fff !important; }}
[data-testid="stChatMessageContent"] {{ background: #fff; border: 1px solid {LINE}; border-radius: {R}; padding: 10px 14px; flex: 0 1 auto; }}
[class*="st-key-msg-user"] [data-testid="stChatMessage"] {{ flex-direction: row-reverse; width: 100%; margin-left: 0; }}
[class*="st-key-msg-user"] [data-testid="stChatMessage"] [data-testid^="stChatMessageAvatar"] {{ background: #57606a !important; }}
[class*="st-key-msg-user"] [data-testid="stChatMessageContent"] {{ background: {BLUE}; border-color: {BLUE}; }}
[class*="st-key-msg-user"] [data-testid="stChatMessageContent"] p {{ color: #fff; }}
[class*="st-key-msg-user"] [data-testid="stChatMessage"] {{ justify-content: flex-start; }}
[data-testid="stChatMessageContent"] {{ margin: 0 !important; }}
/* Streamlit 기본 도구 모음(Deploy 등)은 숨겨 상단바와 겹치지 않게 한다 */
[data-testid="stAppDeployButton"], [data-testid="stMainMenu"], [data-testid="stToolbarActions"], [data-testid="stStatusWidget"] {{ display: none !important; }}

/* ================= 상단바 정리 · 배너 ================= */
.cc-brand {{ flex-wrap: nowrap; white-space: nowrap; overflow: hidden; }}
.cc-mark {{ width: 32px; height: 32px; border-radius: 50%; border: 1px solid {LINE}; background: #fff; object-fit: cover; }}
img.cc-avatar {{ object-fit: cover; background: #fff; border: 1px solid {LINE}; }}
.cc-page {{ color: {INK}; font-weight: 700; }}
[class*="st-key-topbar"] {{ padding: 8px 0 !important; }}
.cc-greet {{ display: flex; justify-content: space-between; align-items: flex-end; gap: 12px; flex-wrap: wrap; }}
.cc-greet .cc-pills {{ margin: 0; }}
[class*="st-key-banner"] {{ background: #fff; border: 1px solid {LINE}; border-radius: {R}; padding: 6px 0; margin-top: 8px; }}
[class*="st-key-banner"] [data-testid="stImage"], [class*="st-key-banner"] [data-testid="stImageContainer"] {{ width: 100% !important; display: flex; justify-content: center; }}
[class*="st-key-banner"] img {{ max-height: 150px; width: auto !important; max-width: 100%; object-fit: contain; }}
[class*="st-key-banner"] [data-testid="stElementToolbar"] {{ display: none; }}
/* 대화: 달달이 얼굴 아이콘 */
[data-testid="stChatMessage"] > img, [data-testid="stChatMessage"] [data-testid^="stChatMessageAvatar"] img {{ display: block !important; width: 32px; height: 32px;
  border-radius: 50%; border: 1px solid {LINE}; background: #fff; object-fit: cover; flex: none; }}

/* ================= 배너 ================= */
.cc-banner {{ background: #fff; border: 1px solid {LINE}; border-radius: {R}; margin-top: 8px; padding: 18px 16px; display: flex; align-items: center;
  justify-content: center; gap: 34px; }}
.cc-banner img {{ width: 112px; height: 112px; object-fit: cover; flex: none; }}
.cc-banner .w {{ position: relative; }}
.cc-banner .t {{ font-family: "Jua", "Noto Sans KR", sans-serif; font-size: 46px; line-height: 1.15; color: #111; letter-spacing: 4px; position: relative; white-space: nowrap; }}
.cc-banner .n {{ font-family: "Gaegu", "Noto Sans KR", sans-serif; font-weight: 700; font-size: 30px; color: #111; letter-spacing: 8px; margin-top: 6px; position: relative; padding-left: 26px; }}
.cc-banner .sp {{ position: absolute; font-style: normal; font-size: 14px; color: #111; font-family: "Noto Sans KR", sans-serif; }}
.cc-banner .sp.a {{ top: -8px; left: 38%; }} .cc-banner .sp.b {{ top: -10px; right: 2px; }} .cc-banner .sp.c {{ top: -2px; left: 4px; }}
@media (max-width: 760px) {{ .cc-banner {{ gap: 16px; }} .cc-banner img {{ width: 76px; height: 76px; }} .cc-banner .t {{ font-size: 30px; letter-spacing: 2px; }}
  .cc-banner .n {{ font-size: 22px; }} }}
.cc-banner .f {{ position: relative; flex: none; line-height: 0; }}
.cc-banner .moon {{ position: absolute; width: 38px; height: 38px; top: -16px; right: -20px; transform: rotate(-14deg); }}
@media (max-width: 760px) {{ .cc-banner .moon {{ width: 24px; height: 24px; top: -14px; right: -6px; }} }}
[class*="st-key-topbar"] .stButton > button {{ border-radius: 6px !important; background: #fff; border: 1px solid #d1d9e0; color: {INK}; font-weight: 700; min-height: 34px; white-space: nowrap; }}
[class*="st-key-topbar"] .stButton > button[kind="primary"] {{ background: {BLUE} !important; color: #fff !important; }}
/* Streamlit의 보이지 않는 상단 도구 모음이 상단바 버튼(알림·프로필)을 덮어 클릭을 가로채지 않게 한다 */
header[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stToolbar"] > div {{ pointer-events: none !important; }}
[data-testid="stExpandSidebarButton"], [data-testid="stExpandSidebarButton"] *, [data-testid="stSidebarCollapsedControl"],
[data-testid="stSidebarCollapsedControl"] * {{ pointer-events: auto !important; }}
</style>
"""


def inject() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


ASSETS = Path(__file__).resolve().parent.parent / "assets"


def _data_uri(name: str) -> str:
    try:
        return "data:image/png;base64," + base64.b64encode((ASSETS / name).read_bytes()).decode()
    except OSError:
        return ""


FACE = _data_uri("dalda.png")
FACE_BIG = _data_uri("dalda_big.png") or FACE
MARK = f'<img class="cc-mark" src="{FACE}" alt="">' if FACE else '<span class="cc-mark"></span>'


def brand_html(page: str = "달달이") -> str:
    """상단바 왼쪽: 마스코트 + 서비스 이름 / 코치 이름."""
    return (f'<div class="cc-brand">{MARK}<span class="cc-name">자격증 패스 코치</span><span class="cc-slash">/</span>'
            f'<span class="cc-page">{escape(page)}</span></div>')


def header(pills: list[tuple[str, bool]], today: str, user: str | None) -> None:
    """위젯 없는 상단바 (입장 화면용)."""
    st.markdown(f'<div class="cc-header">{brand_html()}</div>', unsafe_allow_html=True)


def banner() -> None:
    """대시보드 맨 위 배너: 달달이 얼굴 + 손글씨 느낌의 서비스 이름."""
    moon = ('<svg class="moon" viewBox="0 0 48 48" aria-hidden="true"><path d="M31 6a18 18 0 1 0 11 27A15 15 0 0 1 31 6z" fill="#f7cf5a" '
            'stroke="#111" stroke-width="2.2" stroke-linejoin="round"/><circle cx="21" cy="25" r="1.6" fill="#111"/><circle cx="29" cy="29" r="1.6" fill="#111"/>'
            '<path d="M22 32q3 2.5 6 1" fill="none" stroke="#111" stroke-width="1.8" stroke-linecap="round"/>'
            '<circle cx="19" cy="30" r="2.2" fill="#f4a6a0" opacity=".8"/></svg>')
    face = f'<span class="f"><img src="{FACE_BIG}" alt="달달이">{moon}</span>' if FACE_BIG else ""
    st.markdown(f'<div class="cc-banner">{face}<div class="w"><div class="t"><i class="sp a">✳</i><i class="sp b">✳</i>자격증 패스 코치</div>'
                '<div class="n"><i class="sp c">✳</i>달달이</div></div></div>', unsafe_allow_html=True)


def greeting(user: str | None, line: str, pills: list[tuple[str, bool]] | None = None) -> None:
    name = f"{escape(user)}님" if user else "방문자님"
    pill_html = "".join(f'<span class="cc-pill{" on" if on else ""}">{escape(label)}</span>' for label, on in pills or [])
    st.markdown(f'<div class="cc-greet"><div><h1>안녕하세요, {name}</h1><p>{escape(line)}</p></div>'
                f'<div class="cc-pills">{pill_html}</div></div>', unsafe_allow_html=True)


def profile_card(user: str | None, note: str) -> None:
    initial = escape((user or "G")[0].upper())
    st.markdown(f'<div class="cc-prof"><span class="cc-face">{initial}</span><div><div class="t">{escape(user or "방문자")}</div>'
                f'<div class="s">{escape(note)}</div></div></div>', unsafe_allow_html=True)


def coach_head(online: bool) -> None:
    badge = '<span class="cc-online">AI 연결됨</span>' if online else '<span class="cc-online off">규칙 기반</span>'
    face = f'<img class="cc-avatar" src="{FACE}" alt="">' if FACE else '<div class="cc-avatar"></div>'
    st.markdown(f'<div class="cc-coach">{face}<div><div class="t">달달이</div>'
                f'<div class="s">자격증 코치 · 추천 · 일정 · 학습 경로 · 진도 관리</div></div>{badge}</div>', unsafe_allow_html=True)


def tiles(items: list[tuple[str, str, str]]) -> None:
    """요약 타일. items: (라벨, 값, 보조 설명) — 첫 칸이 넓다."""
    def bar(value: str) -> str:
        if not value.endswith("%") or not value[:-1].replace(".", "").isdigit():
            return ""
        return f'<div class="cc-prog"><i style="width:{min(100.0, float(value[:-1])):g}%"></i></div>'
    cells = "".join(f'<div class="cc-tile{" main" if i == 0 else ""}"><div class="k">{escape(k)}</div><div class="v">{escape(v)}</div>'
                    f'<div class="n">{escape(n)}</div>{bar(v)}</div>' for i, (k, v, n) in enumerate(items))
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
