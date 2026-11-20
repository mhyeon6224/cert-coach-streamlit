"""자격증 패스 코치 — Streamlit 앱.

추천 → 공식 일정 확인 → 학습 경로 → 주차별 계획 → 체크인·재조정 → 결과 반영 → 다음 자격증까지
하나의 상태 흐름으로 잇는 대화형 자격증 코치.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

from coach import engine, plan as planner
from coach.catalog import BY_CODE, CATALOG, find_cert
from coach.router import apply_round, do_plan, do_recommend, handle, new_state, set_target
from coach.services import build_services, secret
from coach import gcal, notion, storage, ui

st.set_page_config(page_title="자격증 패스 코치", page_icon="🎓", layout="wide")
ui.inject()


@st.cache_resource
def user_store():
    return storage.build_store()


store = user_store()


def google_callback() -> None:
    """Google 동의 화면에서 돌아온 탭. 새 탭이라 로그인 상태가 없으므로 1회용 state 값으로 사용자를 찾는다."""
    params = st.query_params
    if "state" not in params or ("code" not in params and "error" not in params):
        return
    st.markdown("### Google Calendar 연결")
    cfg = gcal.config()
    state_value = str(params.get("state", ""))[:200]
    try:
        pending = storage.get_meta(store, "gstate", state_value) if state_value.replace("-", "").replace("_", "").isalnum() else {}
        if "error" in params:
            st.warning("연결을 취소했어요. 이 탭을 닫고 원래 탭으로 돌아가세요.")
        elif not cfg or not gcal.state_valid({"value": state_value, "created": pending.get("created", 0)} if pending else None, state_value):
            st.error("연결 요청이 만료됐거나 올바르지 않아요. 원래 탭에서 'Google Calendar 연결'을 다시 눌러 주세요.")
        else:
            tokens = gcal.exchange_code(cfg, str(params["code"]))
            storage.put_meta(store, "gcal", pending["nickname"], tokens)
            storage.put_meta(store, "gstate", state_value, {})
            st.success(f"{pending['nickname']}님의 Google Calendar가 연결됐어요. 이 탭을 닫고 원래 탭에서 '연결 확인'을 눌러 주세요.")
    except (gcal.CalendarError, storage.StoreError) as error:
        st.error(str(error))
    st.stop()


google_callback()

GREETING = (
    "안녕하세요, 자격증 코치 **달달이**예요.\n\n"
    "무엇을 딸지, 언제 접수하는지, 무엇으로 공부할지, 계획을 어떻게 지킬지를 하나의 흐름으로 이어 드려요. "
    "궁금한 단계부터 말해 주세요. 결과는 오른쪽 대시보드에 카드와 표로 정리돼요.\n\n"
    "일정·응시료는 공식 사이트에서 확인된 것만 보여 주고, 확인하지 못한 값은 **미확인**으로 남겨요."
)
ASSETS = Path(__file__).resolve().parent / "assets"
AVATAR = {"assistant": str(ASSETS / "dalda.png") if (ASSETS / "dalda.png").exists() else ":material/school:",
          "user": ":material/person:"}
EXAMPLES = ["데이터 분석 직무에 맞는 자격증 추천해줘", "1순위 시험 일정 알려줘", "1순위로 준비할래",
            "학습 계획 세워줘", "오늘 뭐 공부해?", "합격했어"]


# ------------------------------------------------------------------ 접속 비밀번호
def gate() -> None:
    if st.session_state.get("authed"):
        return
    ui.header([], date.today().isoformat(), None)
    _, middle, _ = st.columns([1, 1.2, 1])
    middle.markdown("#### 입장 비밀번호")
    middle.caption("과도한 접속을 막기 위해 비밀번호를 사용해요.")
    with middle.form("login"):
        password = st.text_input("비밀번호", type="password")
        if st.form_submit_button("입장", type="primary"):
            if hmac.compare_digest(password.encode(), secret("APP_PASSWORD", "pnumis").encode()):
                st.session_state["authed"] = True
                st.rerun()
            st.error("비밀번호가 맞지 않아요.")
    st.stop()


gate()


@st.cache_resource
def services():
    return build_services()


llm, search = services()


def merge_state(data: dict) -> dict:
    """저장된 값을 현재 버전의 상태 구조에 맞춰 불러온다."""
    fresh = new_state()
    for key, default in fresh.items():
        if key in data and (default is None or isinstance(data[key], type(default)) or data[key] is None):
            fresh[key] = data[key]
    base = new_state()["profile"]
    fresh["profile"] = {**base, **{k: v for k, v in (fresh["profile"] or {}).items() if k in base}}
    fresh["pending"], fresh["plan_preview"] = None, None
    return fresh


def snapshot(state: dict) -> dict:
    data = {k: v for k, v in state.items() if k not in ("pending", "plan_preview")}
    data["messages"] = state["messages"][-40:]
    return data


if "S" not in st.session_state:
    st.session_state["S"] = new_state()
S = st.session_state["S"]
if not S["messages"]:
    S["messages"].append({"role": "assistant", "content": GREETING})


def send(message: str) -> str:
    S["messages"].append({"role": "user", "content": message})
    try:
        reply = handle(message, S, llm, search, today)
    except Exception as error:  # 한 단계가 실패해도 대화 전체를 멈추지 않는다
        reply = f"⛔ 이 요청을 처리하다 문제가 생겼어요({type(error).__name__}). 조건을 바꿔 다시 시도해 주세요."
    S["messages"].append({"role": "assistant", "content": reply})
    return reply


def calendar_line(result: dict | None, error: str | None) -> str:
    if error:
        return f"주요 일정 달력: 못 함 — {error}"
    if not result:
        return ""
    parts = []
    if result["created"]:
        parts.append("새로 만듦")
    if result["added"]:
        parts.append(f"일정 {result['added']}개 추가")
    if result["updated"]:
        parts.append(f"날짜 {result['updated']}개 수정")
    if result.get("view") == "만듦":
        parts.append("달력 보기 추가")
    line = "주요 일정 달력: " + (", ".join(parts) or "바뀐 것 없음")
    if result.get("view_error"):
        line += f" · 달력 보기는 못 만듦({result['view_error']}) — Notion에서 표 위 + → Calendar로 추가할 수 있어요"
    return line


def remembered_token() -> str:
    """이 창에서 쓴 토큰, 없으면 계정에 기억해 둔 토큰."""
    if st.session_state.get("notion_token"):
        return st.session_state["notion_token"]
    auth_now = st.session_state.get("auth")
    if auth_now and "notion_token_loaded" not in st.session_state:
        st.session_state["notion_token_loaded"] = True
        try:
            st.session_state["notion_token"] = storage.get_meta(store, "notion", auth_now["nickname"]).get("token", "")
        except storage.StoreError:
            pass
    return st.session_state.get("notion_token", "")


def remember_box(key: str) -> bool:
    """토큰을 계정에 기억할지 묻는다. 로그인한 경우에만."""
    if not st.session_state.get("auth"):
        st.caption("오른쪽 위 프로필에서 로그인하면 토큰과 페이지 링크를 계정에 기억해 둘 수 있어요.")
        return False
    return st.checkbox("이 토큰을 내 계정에 기억하기 (다음부터 다시 붙여 넣지 않아도 돼요)", value=True, key=key,
                       help="계정 DB에 저장돼요. 지우려면 체크를 풀고 다시 실행하거나 프로필 메뉴에서 '기억한 Notion 토큰 지우기'를 누르세요.")


def keep_token(token: str, remember: bool) -> None:
    st.session_state["notion_token"] = token.strip()
    auth_now = st.session_state.get("auth")
    if auth_now:
        try:
            storage.put_meta(store, "notion", auth_now["nickname"], {"token": token.strip()} if remember else {})
        except storage.StoreError:
            pass


def notion_sync(token: str, link: str, today_value, hours: float, active: bool) -> list[str]:
    """스킬의 체크인 절차: Notion 체크 읽기 → 지연 계산 → 필요하면 재조정 → 진행률·브리핑·계획을 Notion에 다시 쓰기."""
    plan, lines = S["plan"], []
    blocks = notion.read_blocks(token, link)
    pulled = notion.pull_checks(blocks, plan)
    if not pulled["found"]:
        raise notion.NotionError("그 페이지에서 주차별 계획 체크박스를 찾지 못했어요. 앱이 만든 'OOO 학습 공간' 페이지의 링크를 넣어 주세요. "
                                 "(그 페이지를 넣어 둔 상위 페이지 링크가 아니에요.)")
    done_now = [w for w, done in pulled["changed"] if done]
    undone = [w for w, done in pulled["changed"] if not done]
    lines.append("Notion 체크 가져오기: " + (f"완료 {len(done_now)}개" + (f", 완료 취소 {len(undone)}개" if undone else "") if pulled["changed"] else "바뀐 것 없음"))
    info = planner.checkin(plan, today_value, hours or 1, int(S["profile"]["study_days"] or 5), S["target"])
    if active and info["needs_readjust"]:
        outcome = planner.readjust(plan, today_value, hours or plan["weekly_hours"], f"지연 {info['delay_days']:g}일")
        lines.append(("재조정: " if outcome["status"] == "done" else "재조정 보류: ") + outcome["message"])
        info = planner.checkin(plan, today_value, hours or 1, int(S["profile"]["study_days"] or 5), S["target"])
    lines.append(f"진행률 {info['percent']}% · 지연 {info['delay_days']:g}일")
    pushed = notion.push_updates(token, blocks, S, info if active else None)
    lines.append(f"Notion에 다시 쓰기: {pushed['updated']}개 항목 갱신(오늘 브리핑·진행률·주차별 계획)")
    if pushed["missing_weeks"]:
        lines.append(f"확인 필요: 계획의 {pushed['missing_weeks']}개 주차는 그 페이지에 없어요. 계획을 새로 만들었다면 학습 공간도 새로 만들어 주세요.")
    try:
        lines.append(calendar_line(notion.ensure_calendar(token, notion.page_id_from(link), blocks, S["target"]), None))
    except notion.NotionError as error:
        lines.append(calendar_line(None, str(error)))
    return lines


def run_sync(token: str, link: str, today_value, hours: float, active: bool, remember: bool | None = None) -> None:
    """동기화하고 결과를 화면 위 알림으로 남긴 뒤 다시 그린다(진행률 타일·표에 바로 반영)."""
    lines = notion_sync(token, link, today_value, hours, active)
    st.session_state["notion_token"] = token.strip()
    if remember is not None:
        keep_token(token, remember)
    S["notion"] = {"url": link.strip()}
    st.session_state["flash"] = "Notion과 동기화했어요.\n\n" + "\n".join(f"- {line}" for line in lines if line)
    st.rerun()


NOTION_GUIDE = (
    "1. [notion.so/profile/integrations](https://www.notion.so/profile/integrations) 에서 **새 연결(New connection)** 을 만들어요. "
    "인증 방식은 **API token**, 워크스페이스는 본인 것을 고르면 돼요.\n"
    "2. 만들어진 화면에서 **토큰** 을 복사해요. `ntn_`로 시작해요.\n"
    "3. 학습 공간을 넣고 싶은 Notion 페이지를 **연 뒤**, 본문 오른쪽 위 **⋯ → 연결(Connections)** 에서 방금 만든 연결을 추가해요. "
    "이 단계를 빼먹으면 '접근 권한이 없어요'가 나와요.\n"
    "4. 같은 페이지에서 **⋯ → 링크 복사** 로 페이지 주소를 복사해요.")


@st.dialog("Notion에 학습 공간 만들기", width="large")
def notion_dialog(info) -> None:
    st.markdown(ui.badges([("내 Notion에만 저장", "navy"), ("토큰은 동의할 때만 계정에 기억", "good")]), unsafe_allow_html=True)
    st.markdown("고른 페이지 아래에 **학습 공간 페이지를 새로 하나** 만들어요. 주차별 계획(체크박스)과 **주요 일정 달력**이 들어가요.")
    if (S.get("notion") or {}).get("url"):
        st.warning("이미 만든 학습 공간이 있어요. 여기서 만들면 페이지가 하나 더 생겨요. 체크를 맞추려면 이 창을 닫고 'Notion과 동기화'를 눌러 주세요.")
    with st.expander("처음이라면: 3분 준비 방법", expanded=not remembered_token()):
        st.markdown(NOTION_GUIDE)
    token = st.text_input("① 토큰", type="password", value=remembered_token(), placeholder="ntn_...")
    remember = remember_box("remember_make")
    link = st.text_input("② 학습 공간을 넣을 페이지 링크", value=st.session_state.get("notion_parent", ""),
                         placeholder="https://www.notion.so/...")
    agree = st.checkbox("내 Notion에 페이지를 새로 만드는 데 동의해요")
    if st.button("학습 공간 만들기", type="primary", disabled=not (token and link and agree)):
        try:
            with st.spinner("Notion에 페이지를 만드는 중이에요…"):
                made = notion.create_space(token, link, S, info)
            st.session_state["notion_parent"] = link.strip()
            keep_token(token, remember)
            S["notion"] = {"url": made["url"]}
            st.success("페이지를 만들었어요. 완료는 Notion에서 체크하고, 계획 탭의 'Notion과 동기화'로 맞추면 돼요.")
            note = calendar_line(made["calendar"], made["calendar_error"])
            if note:
                st.markdown(f"- {note}")
            if made["url"]:
                st.link_button("Notion에서 열기", made["url"])
        except notion.NotionError as error:
            st.error(f"만들지 못했어요. {error}")
    st.caption("실패해도 앱 안의 학습 공간과 .md 내보내기는 그대로 쓸 수 있어요.")


@st.dialog("Notion과 동기화", width="large")
def notion_sync_dialog(today_value, hours: float, active: bool) -> None:
    st.markdown("Notion에서 체크한 완료를 앱으로 가져오고, 진행률·오늘 브리핑·주차별 계획·주요 일정을 **같은 페이지에** 다시 써요. 새 페이지는 만들지 않아요.")
    token = st.text_input("토큰", type="password", value=remembered_token(), placeholder="ntn_...")
    remember = remember_box("remember_sync")
    page = st.text_input("학습 공간 페이지 링크", value=(S.get("notion") or {}).get("url", ""),
                         placeholder="앱이 만든 'OOO 학습 공간' 페이지의 링크",
                         help="Notion에서 'OOO 학습 공간' 페이지를 열고 ⋯ → 링크 복사. 그 페이지를 넣어 둔 상위 페이지 링크가 아니에요.")
    agree = st.checkbox("그 페이지의 브리핑·진행률·계획 항목을 앱이 고쳐 쓰는 데 동의해요")
    if st.button("동기화하기", type="primary", disabled=not (token and page and agree)):
        try:
            with st.spinner("Notion을 읽고 다시 쓰는 중이에요…"):
                run_sync(token, page, today_value, hours, active, remember)
        except notion.NotionError as error:
            st.error(f"동기화하지 못했어요. {error}")


# ------------------------------------------------------------------ 사이드바
def memo_pad() -> None:
    """프로필 메뉴의 메모장: 자주 붙여 넣는 링크·메모를 적어 둔다."""
    with st.form("memo_form", border=False):
        text = st.text_area("내 메모장", S.get("memo", ""), height=130,
                            placeholder="예: Notion 학습 공간 링크, 접수 사이트 주소, 수험번호 메모 …",
                            help="로그인하면 계정에 저장돼요. 로그인 전에는 이 창을 닫으면 사라져요.")
        if st.form_submit_button("메모 저장", use_container_width=True):
            S["memo"] = text
            st.toast("메모를 저장했어요.")
    linked = (S.get("notion") or {}).get("url")
    if linked:
        st.caption("연결된 Notion 학습 공간")
        st.code(linked, language=None)


def account_panel() -> None:
    """상단바 프로필 메뉴: 로그인·새 계정·로그아웃."""
    auth = st.session_state.get("auth")
    if auth:
        ui.profile_card(auth["nickname"], "조건·계획·대화·메모가 자동 저장돼요")
        st.caption(f"저장 위치: {store.label}")
        memo_pad()
        if st.button("기억한 Notion 토큰 지우기", use_container_width=True, key="forget_notion"):
            st.session_state.pop("notion_token", None)
            try:
                storage.put_meta(store, "notion", auth["nickname"], {})
                st.toast("Notion 토큰을 지웠어요.")
            except storage.StoreError as error:
                st.error(str(error))
        if st.button("로그아웃", use_container_width=True, key="logout"):
            for key in ("auth", "saved_digest", "notion_token", "notion_token_loaded"):
                st.session_state.pop(key, None)
            st.session_state["S"] = new_state()
            st.rerun()
        return
    ui.profile_card(None, "로그인하면 다시 접속해도 이어서 할 수 있어요")
    memo_pad()
    with st.form("account", border=False):
        nick = st.text_input("닉네임")
        account_pw = st.text_input("계정 비밀번호", type="password", help="다른 서비스에서 쓰는 비밀번호는 쓰지 마세요.")
        agree = st.checkbox("내 조건·계획·대화를 저장하는 데 동의해요 (새로 만들 때 필요)")
        col_in, col_up = st.columns(2)
        do_login = col_in.form_submit_button("로그인", type="primary", use_container_width=True)
        do_signup = col_up.form_submit_button("새로 만들기", use_container_width=True)
    try:
        if do_login:
            loaded, info = storage.login(store, nick.strip(), account_pw)
            if info:
                st.session_state["auth"] = info
                st.session_state["S"] = merge_state(loaded)
                st.session_state["flash"] = f"{info['nickname']}님, 지난번에 이어서 진행해요."
                st.rerun()
            st.error("닉네임 또는 비밀번호가 맞지 않아요.")
        if do_signup:
            if not agree:
                st.error("저장에 동의해야 계정을 만들 수 있어요.")
            else:
                problem = storage.signup(store, nick.strip(), account_pw, snapshot(S))
                if problem:
                    st.error(problem)
                else:
                    _, info = storage.login(store, nick.strip(), account_pw)
                    st.session_state["auth"] = info
                    st.session_state["flash"] = "계정을 만들었어요. 지금부터 자동 저장돼요."
                    st.rerun()
    except storage.StoreError as error:
        st.error(f"저장소에 연결하지 못했어요. {error}")
    st.caption("계정 없이도 쓸 수 있어요. 그 경우 창을 닫으면 내용이 사라져요.")


with st.sidebar:
    st.header("설정")
    with st.expander("내 정보 파일로 저장·불러오기"):
        st.caption("계정을 쓰지 않을 때의 대안이에요. 원할 때만 파일로 내려받아 다음에 불러올 수 있어요.")
        if st.checkbox("내 조건·계획을 파일로 저장하는 데 동의해요"):
            saved = {k: v for k, v in S.items() if k not in ("messages", "pending", "plan_preview")}
            st.download_button("내 정보 내려받기 (.json)", json.dumps(saved, ensure_ascii=False, indent=1),
                               "cert-coach-profile.json", "application/json", use_container_width=True)
        uploaded = st.file_uploader("저장한 파일 불러오기", type="json")
        if uploaded is not None:
            raw = uploaded.getvalue()
            digest = hashlib.sha256(raw).hexdigest()
            if st.session_state.get("loaded_file") != digest:
                try:
                    fresh = merge_state(json.loads(raw.decode("utf-8")))
                    fresh["messages"] = [{"role": "assistant", "content": "저장한 정보를 불러왔어요. 이어서 진행할게요."}]
                    st.session_state["S"] = fresh
                    st.session_state["loaded_file"] = digest
                    st.rerun()
                except (ValueError, UnicodeDecodeError, AttributeError):
                    st.error("파일을 읽지 못했어요. 이 앱에서 내려받은 파일인지 확인해 주세요.")
        if st.button("전체 초기화", use_container_width=True):
            st.session_state["S"] = new_state()
            st.rerun()

    with st.expander("연결 상태·데모 설정"):
        st.write(("✅" if llm else "⚪") + " AI 모델 " + ("연결됨" if llm else "미설정 — 규칙 기반으로 동작"))
        st.write(("✅" if search else "⚪") + " 웹 검색 " + ("연결됨" if search else "미설정 — 직접 수집 가능한 사이트만 일정 확인"))
        st.write(("✅" if store.durable else "🟡") + " 저장소: " + store.label)
        demo = st.checkbox("오늘 날짜 바꾸기 (지연·재조정 시연용)")
        demo_day = st.date_input("가상의 오늘", date.today(), disabled=not demo)
    today = demo_day if demo else date.today()
    if demo:
        st.warning(f"데모 날짜 사용 중: {today.isoformat()}")

target = S["target"]
P = S["profile"]
auth = st.session_state.get("auth")
# 화면에 띄우던 안내는 모두 알림함으로 모은다 (새 알림은 잠깐 뜨는 토스트로도 알려 준다)
if st.session_state.get("flash"):
    _message = st.session_state.pop("flash")
    S.setdefault("notices", []).insert(0, {"at": datetime.now(timezone(timedelta(hours=9))).strftime("%m-%d %H:%M"), "text": _message})
    del S["notices"][30:]
    st.session_state["unread"] = st.session_state.get("unread", 0) + 1
    st.toast("알림: " + _message.split("\n")[0][:80])


@st.dialog("취업 가이드라인 — 분석한 자료", width="large")
def guideline_dialog(detail: dict) -> None:
    st.caption(f"{detail.get('origin', '')} · 확인 날짜 {detail.get('checked_at', '')}"
               + (f" · 검색어: {detail['query']}" if detail.get("query") else ""))
    if detail.get("competencies"):
        ui.label("역량별 근거")
        ui.table(["필요 역량", "근거 자료", "구분"],
                 [[c["name"], ", ".join(f"[{n}]" for n in c["sources"]) or "근거 번호 없음",
                   ("2건 이상 반복", "good") if len(c["sources"]) >= 2 else ("한 번만 확인", "warn")]
                  for c in detail["competencies"]])
    ui.label("읽은 자료")
    for source in detail["sources"]:
        with st.container(border=True):
            st.markdown(f"**[{source['no']}] {source['title']}**")
            if source.get("url"):
                st.markdown(f"[원문 열기]({source['url']})")
            st.caption(f"AI가 읽은 부분(앞 {source['read_chars']}자 중 일부)")
            st.text(source["excerpt"] + ("…" if source["read_chars"] > len(source["excerpt"]) else ""))
    st.caption("검색으로 찾은 글의 일부만 읽고 요약한 것이라, 실제 공고 원문과 다를 수 있어요.")


@st.dialog("알림")
def notice_dialog() -> None:
    notices = S.get("notices") or []
    if not notices:
        st.caption("아직 알림이 없어요. 목표 저장, 재조정, Notion 동기화 같은 변경 사항이 여기에 쌓여요.")
        return
    for item in notices:
        with st.container(border=True):
            st.caption(item["at"])
            st.markdown(item["text"])
    if st.button("알림 모두 지우기", use_container_width=True):
        S["notices"] = []
        st.rerun()


@st.dialog("내 프로필")
def profile_dialog() -> None:
    account_panel()


with st.container(key="topbar"):
    bar_left, bar_bell, bar_right = st.columns([3.4, 1, 1.2], vertical_alignment="center")
    bar_left.markdown(ui.brand_html(), unsafe_allow_html=True)
    _unread = st.session_state.get("unread", 0)
    if bar_bell.button(f"알림 {_unread}" if _unread else "알림", icon=":material/notifications:", use_container_width=True,
                       type="primary" if _unread else "secondary", key="bell"):
        st.session_state["unread"] = 0
        notice_dialog()
    if bar_right.button(auth["nickname"] if auth else "로그인", icon=":material/account_circle:", use_container_width=True, key="profile_btn"):
        profile_dialog()

_plan = S.get("plan")
_hours = float(P["weekly_hours"] or (_plan or {}).get("weekly_hours") or 0)
_info = planner.checkin(_plan, today, _hours or 1, int(P["study_days"] or 5), target) if _plan else None
_exam = target.get("exam_date")


def queue(message: str) -> None:
    """대시보드의 버튼을 누르면 대화창에 그 문장을 보낸다."""
    st.session_state["queued"] = message


if _exam and target.get("name"):
    _line = f"{target['name']} 시험까지 D-{(date.fromisoformat(_exam) - today).days}"
elif target.get("name"):
    _line = f"목표 {target['name']} · 시험일 미확인"
else:
    _line = "아직 목표 자격증이 없어요. 대화나 추천 탭에서 시작해 보세요."
ui.banner()
ui.greeting(auth["nickname"] if auth else None,
            f"오늘 {today.isoformat()} · {_line}" + ("" if auth else " · 로그인 전이라 창을 닫으면 내용이 사라져요"),
            [("AI 추천" if llm else "규칙 기반 추천", bool(llm)), ("웹 검색" if search else "공식 페이지 직접 수집", bool(search)),
             ("클라우드 저장" if store.durable else "임시 저장", store.durable)])
left, right = st.columns([1, 1.9], gap="medium")

# ------------------------------------------------------------------ 대화 (왼쪽 패널)
with left:
    ui.coach_head(bool(llm))
    chat_box = st.container(height=560, key="cardchat")
    with chat_box:
        for index, message in enumerate(S["messages"]):
            with st.container(key=f"msg-{message['role']}-{index}"):
                with st.chat_message(message["role"], avatar=AVATAR[message["role"]]):
                    st.markdown(message["content"])
    prompt = st.chat_input("예: 회계 직무에 맞는 자격증 추천해줘") or st.session_state.pop("queued", None)
    if prompt:
        with chat_box:
            with st.container(key="msg-user-new"):
                with st.chat_message("user", avatar=AVATAR["user"]):
                    st.markdown(prompt)
            with st.container(key="msg-assistant-new"):
                with st.chat_message("assistant", avatar=AVATAR["assistant"]), st.spinner("확인하는 중이에요…"):
                    send(prompt)
        st.rerun()
    st.caption("로그인은 오른쪽 위 프로필 버튼, 파일 저장·데모 날짜는 왼쪽 위 » 메뉴에 있어요.")

# ------------------------------------------------------------------ 대시보드 (오른쪽)
with right:
    ui.tiles([
        ("목표 자격증", target.get("name") or "미정", (f"{target.get('issuer') or ''} · {target.get('state')}" if target.get("code") else "추천 탭에서 골라 보세요")),
        ("시험일", f"D-{(date.fromisoformat(_exam) - today).days}" if _exam else "미확인", _exam or "일정 탭에서 확인"),
        ("진행률", f"{_info['percent']}%" if _info else "—", f"현재 {_info['current_week']}주차" if _info and _info["current_week"] else "계획 저장 후 표시"),
        ("지연", f"{_info['delay_days']:g}일" if _info else "—", "3일 이상이면 재조정"),
    ])
    tab_home, tab_rec, tab_sched, tab_space, tab_profile, tab_more = st.tabs(["대화", "추천", "일정", "계획", "프로필", "기능"])

with tab_home:
    with st.container(border=True, key="card1"):
        ui.section("지금 어디까지 왔나요", "어느 단계에서 시작해도 돼요")
        done = [bool(P["desired_job"]), bool(S.get("recommendations")), bool(_exam), bool(_plan),
                bool(_info and _info["percent"] > 0), target.get("state") in ("합격", "불합격")]
        steps = [("조건 입력", "희망 직무·비용 선호·주당 시간", "프로필 탭"), ("자격증 추천", "1순위 1개 + 대안, 근거와 주의점", "추천 탭"),
                 ("공식 일정", "주관기관에서 확인된 접수·시험·발표일", "일정 탭"), ("학습 계획", "주차별 미리보기 → 동의 후 저장", "계획 탭"),
                 ("체크인·재조정", "오늘 할 일, 지연 3일 이상이면 재조정", "계획 탭"), ("결과 반영", "합격 → 다음 자격증 / 불합격 → 재도전 계획", "기능 탭")]
        nxt = done.index(False) if False in done else None
        ui.table(["단계", "하는 일", "어디서", "상태"],
                 [[f"{i + 1}. {name}", what, where,
                   ("완료", "good") if done[i] else (("다음 단계", "best") if i == nxt else ("대기", "mute"))]
                  for i, (name, what, where) in enumerate(steps)])
    with st.container(border=True, key="card2"):
        ui.section("이렇게 말해 보세요", "누르면 왼쪽 대화창으로 보내요")
        cols = st.columns(2)
        for index, example in enumerate(EXAMPLES):
            cols[index % 2].button(example, key=f"ex_{index}", use_container_width=True, on_click=queue, args=(example,))

# ------------------------------------------------------------------ 추천
with tab_rec:
    with st.container(border=True, key="card3"):
        ui.section("추천 결과", "내 조건에 맞는 1순위 + 대안")
        st.caption(f"이번 판단에 쓸 정보: {engine.used_info(P, ['desired_job', 'major_experience', 'owned', 'learning_style', 'cost_pref', 'weekly_hours', 'target_period'])}")
        if st.button("내 조건으로 추천 받기", type="primary", disabled=not P["desired_job"]):
            with st.spinner("후보를 비교하는 중이에요…"):
                do_recommend(S, llm, search, today)
        if not P["desired_job"]:
            st.info("'프로필' 탭에 희망 직무를 적거나, 대화창에서 \"자격증 추천해줘\"라고 말해 주세요.")
        recs = S.get("recommendations")
        if recs:
            for note in recs["notices"]:
                st.caption(note)
            if recs["summary"]:
                ui.box(recs["summary"], "blue", "요약")
            for item in recs["candidates"]:
                if item["rank"] == 1:
                    ui.rank("1순위", item["name"])
                else:
                    if item["rank"] == 2:
                        ui.label("대안 자격증")
                    ui.card_head([(f"대안 {item['rank'] - 1}", "sky")], item["name"], "")
                ui.box(item["reason"], "", "진로 연결 근거")
                ui.kv([("주관", item["issuer"]), ("응시자격", "제한 있음 — 공식 확인 필요" if item["restricted"] else "제한 없음"),
                       ("준비 예상 범위", item["prep_scope"]), ("주의점", item["caution"])])
                if st.button(f"{item['name']}(으)로 준비 시작", key=f"start_{item['code']}", type="primary" if item["rank"] == 1 else "secondary"):
                    set_target(S, BY_CODE[item["code"]])
                    st.session_state["flash"] = f"{item['name']} 준비를 시작했어요. '일정' 탭에서 시험일을 확인해 주세요."
                    st.rerun()
            ui.label("한눈에 비교")
            ui.table(["순위", "자격증", "주관", "응시자격", "공식 사이트"],
                     [[("1순위", "best") if c["rank"] == 1 else (f"대안 {c['rank'] - 1}", "sky"), c["name"], c["issuer"],
                       ("제한 있음", "warn") if c["restricted"] else ("제한 없음", "good"), ("link", "바로가기", c["official_url"])]
                      for c in recs["candidates"]])
            if recs["practice_first"]:
                ui.box(recs["practice_first"], "red", "솔직히 말하면")
            st.caption(f"추천 방식: {recs['mode']} · {recs['checked_at']} 기준 · 취업·합격을 보장하지 않아요.")
    if S.get("guideline"):
        with st.container(border=True, key="card4"):
            ui.section("취업 가이드라인", "목표 직무·관심 공고가 있을 때만")
            guide = S.get("guideline_detail") or {}
            if guide.get("job_summary") or guide.get("cert_links"):
                # 구조화된 결과가 있으면 카드·표로 보여 준다
                ui.box(guide.get("job_summary") or "미확인", "blue", f"직무 요약 · {guide['job']}" if guide.get("job") else "직무 요약")
                skills = guide.get("competencies") or []
                if skills:
                    ui.label("공고에서 요구하는 역량")
                    ui.chips([(c["name"], "good" if len(c["sources"]) >= 2 else "warn") for c in skills])
                    st.caption("초록: 자료 2건 이상에서 반복된 요건 · 노랑: 한 번만 확인된 요건(참고만)")
                if guide.get("cert_links"):
                    ui.label("자격증이 닿는 지점과 한계")
                    for link in guide["cert_links"]:
                        ui.pair_card(link["cert"], link["touches"], link["limits"])
                if guide.get("portfolio"):
                    ui.label("포트폴리오·경험으로 채울 것")
                    ui.steps(guide["portfolio"])
                ui.kv([("근거 범위", guide.get("origin", "")), ("확인 날짜", guide.get("checked_at", ""))])
                st.caption("공고마다 필수/우대가 달라요. 자격증이 취업을 보장하지 않으며, 시험 일정·응시자격은 공식 원문으로 따로 확인해야 해요.")
            else:
                st.markdown(S["guideline"])
            if guide.get("sources"):
                if st.button("분석한 자료 보기", icon=":material/fact_check:", key="guide_sources"):
                    guideline_dialog(guide)

# ------------------------------------------------------------------ 일정
with tab_sched, st.container(border=True, key="card5"):
    ui.section("공식 시험 일정·응시료", "주관기관 공식 페이지에서 확인된 값만 표시")
    st.caption("자격증을 고르고 확인 버튼을 누르세요.")
    names = []
    for name in [target.get("name"), *reversed(list(S["schedules"])), *[c["name"] for c in (S.get("recommendations") or {}).get("candidates", [])],
                 *[c["name"] for c in CATALOG]]:
        if name and name not in names:
            names.append(name)
    col1, col2 = st.columns([3, 1])
    picked = col1.selectbox("자격증", names, label_visibility="collapsed")
    cert = BY_CODE.get(target.get("code")) if picked == target.get("name") and target.get("code") in BY_CODE else find_cert(picked)
    cert = cert or target
    if col2.button("공식 일정 확인", type="primary", use_container_width=True):
        with st.spinner("주관기관 공식 페이지를 확인하는 중이에요…"):
            S["schedules"][picked] = engine.lookup_schedule(cert, llm, search, today)
    result = S["schedules"].get(picked)
    if result:
        future = [r for r in result["rounds"] if not r["past"]]
        past = [r for r in result["rounds"] if r["past"]]
        if future:
            ui.table(["회차", "원서접수", "시험일", "합격자 발표"],
                     [[r["round"], f"{r['reg_start'] or '미확인'} ~ {r['reg_end'] or '미확인'}", (r["exam_date"], "best"),
                       r["result_date"] or "미확인"] for r in future[:8]])
            if len(future) > 8:
                st.caption(f"가까운 8개 회차만 표로 보여 줘요. 전체 {len(future)}개 회차는 아래 '목표 회차'에서 고를 수 있어요.")
        else:
            ui.box("남은 회차 일정은 미확인이에요. 공식 일정이 아직 발표되지 않았거나 확인하지 못했어요.", "", "남은 회차")
        ui.kv([("주관", result["issuer"]), ("확인 날짜", result["checked_at"]),
               ("응시료", result["fee"]["text"] if result["fee"] else "미확인"),
               ("응시자격", result["eligibility"]["text"] if result["eligibility"] else "미확인")])
        if past:
            st.caption("지난 회차: " + ", ".join(f"{r['round']}({r['exam_date']})" for r in past))
        for head, kind, items in (("확정됨", "green", result["confirmed"]), ("확인 필요", "blue", result["need_check"]),
                                  ("못 함", "red", result["failed"])):
            if items:
                ui.box(" / ".join(items), kind, head)
        if result["reference"] and not future:
            st.caption(f"참고(자료집 기준 2025-12-31, 일정 아님): {result['reference'][:300]}…")
        ui.table(["공식 페이지"], [[("link", s["title"] or s["url"], s["url"])] for s in result["sources"][:4]]
                 or [[("link", result["official_url"], result["official_url"])]])
        if future:
            choice = st.radio("목표 회차", [f"{r['round']} — 시험일 {r['exam_date']}" for r in future])
            if st.button("이 회차를 목표로 저장"):
                set_target(S, cert)
                apply_round(S, future[[f"{r['round']} — 시험일 {r['exam_date']}" for r in future].index(choice)], result)
                st.session_state["flash"] = f"{picked} 목표 회차를 저장했어요."
                st.rerun()
    else:
        st.info("버튼을 누르면 주관기관 공식 사이트만 검색해서 일정을 읽고, 본문과 대조된 날짜만 보여 줘요.")

    with st.expander("공식 사이트에서 본 시험일 직접 입력"):
        st.caption("자동 확인이 안 될 때 써요. 직접 입력한 날짜는 '사용자 입력'으로 표시돼요.")
        with st.form("manual"):
            c1, c2, c3 = st.columns(3)
            exam_day = c1.date_input("시험일", today + timedelta(days=56), min_value=today + timedelta(days=1))
            reg_day = c2.date_input("원서접수 마감 (선택)", None)
            result_day = c3.date_input("합격자 발표 (선택)", None)
            if st.form_submit_button(f"{picked} 목표로 저장"):
                set_target(S, cert)
                S["target"].update(exam_date=exam_day.isoformat(), reg_end=reg_day.isoformat() if reg_day else None,
                                   reg_start=None, result_date=result_day.isoformat() if result_day else None,
                                   basis="사용자 입력(공식 확인은 사용자 책임)", checked_at=today.isoformat(),
                                   source_url=cert.get("official_url"))
                st.session_state["flash"] = f"{picked} 시험일을 저장했어요. 이제 학습 계획을 세울 수 있어요."
                st.rerun()

    st.divider()
    ui.section("캘린더에 넣기", "동의한 일정만 · 미확인 날짜는 등록하지 않아요")
    events = []
    for key, label in (("reg_end", "원서접수 마감"), ("exam_date", "시험일"), ("result_date", "합격자 발표")):
        value = target.get(key)
        if value and date.fromisoformat(value) >= today and not (key == "reg_end" and target.get("state") != "준비중"):
            events.append({"title": f"[{target['name']}] {label}", "date": value, "note": f"근거: {target.get('basis')}"})
    if not events:
        st.caption("목표 자격증의 확정 일정이 있으면 여기에서 고를 수 있어요. 미확인 날짜는 등록 대상이 아니에요.")
    else:
        st.caption("준비를 시작했다고 자동으로 넣지 않아요. 넣을 일정만 직접 체크해 주세요.")
        chosen = [e for e in events if st.checkbox(f"{e['title']} — {e['date']}", key=f"cal_{e['title']}")]
        if chosen:
            st.dataframe(pd.DataFrame(chosen).rename(columns={"title": "일정", "date": "날짜", "note": "메모"}),
                         hide_index=True, use_container_width=True)
            gcfg = gcal.config()
            with st.container(border=True, key="card6"):
                st.markdown(ui.badges([("Google Calendar", "navy"), ("내 계정으로 연결", "sky")]), unsafe_allow_html=True)
                if not gcfg:
                    st.caption("자동 등록(계정 연결)은 운영자가 Google 연동 설정을 마치면 켜져요. 지금은 아래 '일정 추가 화면 열기'를 쓸 수 있어요.")
                elif not auth:
                    st.info("자동 등록은 내 계정에 Google 연결을 저장해야 해서, 오른쪽 위 프로필 버튼으로 로그인한 뒤 쓸 수 있어요.")
                else:
                    try:
                        linked = storage.get_meta(store, "gcal", auth["nickname"])
                    except storage.StoreError:
                        linked = {}
                    if linked.get("refresh_token"):
                        st.caption("연결됨 — 고른 일정만 내 Google Calendar(기본 캘린더)에 등록해요. 하루 전 알림이 붙어요.")
                        g1, g2 = st.columns([2, 1])
                        if g1.button(f"선택한 {len(chosen)}개 일정 등록하기", type="primary", use_container_width=True):
                            try:
                                with st.spinner("Google Calendar에 등록하는 중이에요…"):
                                    st.session_state["gcal_result"] = gcal.insert_events(gcfg, linked["refresh_token"], chosen)
                            except gcal.CalendarError as error:
                                st.error(str(error))
                        if g2.button("연결 해제", use_container_width=True):
                            gcal.revoke(linked["refresh_token"])
                            storage.put_meta(store, "gcal", auth["nickname"], {})
                            st.session_state.pop("gcal_result", None)
                            st.rerun()
                        for row in st.session_state.get("gcal_result", []):
                            mark = "✅" if row["status"] in ("등록 완료", "이미 등록됨") else "⛔"
                            st.markdown(f"{mark} {row['title']} ({row['date']}) — {row['status']}"
                                        + (f" · [캘린더에서 보기]({row['link']})" if row["link"] else ""))
                    else:
                        st.caption("내 Google 계정에 한 번만 연결하면, 이후에는 버튼 하나로 등록돼요. 권한은 '일정 만들기'만 요청해요.")
                        if st.button("Google Calendar 연결 시작", type="primary"):
                            pending = gcal.new_state()
                            storage.put_meta(store, "gstate", pending["value"], {"nickname": auth["nickname"], "created": pending["created"]})
                            st.session_state["gcal_link"] = gcal.auth_link(gcfg, pending["value"])
                        if st.session_state.get("gcal_link"):
                            st.link_button("① Google 동의 화면 열기 (새 탭)", st.session_state["gcal_link"])
                            if st.button("② 연결 확인"):
                                st.session_state.pop("gcal_link", None)
                                st.rerun()
            with st.expander("계정 연결 없이 넣기"):
                st.caption("누르면 내 Google 캘린더의 '일정 추가' 화면이 내용이 채워진 채 열려요. 저장만 누르면 돼요.")
                for event in chosen:
                    st.link_button(f"일정 추가 화면 열기 — {event['title']} ({event['date']})", planner.gcal_link(event))
                st.download_button("다른 캘린더용 파일 받기 (.ics)", planner.to_ics(chosen), "cert-schedule.ics", "text/calendar")
                st.caption(".ics 파일은 Outlook·Apple 캘린더·휴대폰 캘린더에서 열면 등록돼요.")

# ------------------------------------------------------------------ 학습 공간
with tab_space, st.container(border=True, key="card7"):
    if not target.get("code"):
        st.info("아직 목표 자격증이 없어요. 추천 탭에서 준비 시작 버튼을 누르거나 대화에서 \"SQLD로 준비할래\"라고 말해 주세요.")
    else:
        ui.section(f"{target['name']} 학습 공간", "오늘 브리핑 · 주차별 계획 · 완료 체크")
        plan = S.get("plan")
        hours = float(P["weekly_hours"] or (plan or {}).get("weekly_hours") or 0)
        info = planner.checkin(plan, today, hours or 1, int(P["study_days"] or 5), target) if plan else None
        exam = target.get("exam_date")
        st.caption(f"일정 근거: {target.get('basis') or '미확인'} · 확인 날짜 {target.get('checked_at') or '—'}")

        b1, b2, b3, b4 = st.columns(4)
        for col, label, phrase in ((b1, "접수했어요", "접수했어"), (b2, "시험 봤어요", "시험 봤어"),
                                   (b3, "합격했어요", "합격했어"), (b4, "불합격했어요", "불합격했어")):
            if col.button(label, use_container_width=True):
                with st.spinner("반영하는 중이에요…"):
                    st.session_state["flash"] = send(phrase)
                st.rerun()

        active = target.get("state") in ("준비중", "접수완료")
        if plan and info:
            if active:
                with st.container(border=True, key="card8"):
                    st.markdown(planner.briefing_text(info, target["name"]))
            else:
                st.info(f"'{target['state']}' 상태라 체크인을 멈췄어요. 결과가 나오면 위 버튼이나 대화로 알려 주세요.")
            st.progress(info["percent"] / 100, text="단계별 완료율 — " + " · ".join(f"{k} {v}%" for k, v in info["by_phase"].items()))
            frame = pd.DataFrame(plan["rows"])
            edited = st.data_editor(
                frame, hide_index=True, use_container_width=True, disabled=["week", "phase", "start", "end", "hours", "task"],
                column_config={"week": "주차", "phase": "단계", "start": "시작", "end": "마감",
                               "hours": st.column_config.NumberColumn("예상 시간", format="%.1f h"), "task": "할 일",
                               "done": st.column_config.CheckboxColumn("완료"), "memo": "메모"}, key="plan_editor")
            new_rows = edited.to_dict("records")
            if [(r["done"], r["memo"]) for r in new_rows] != [(r["done"], r["memo"]) for r in plan["rows"]]:
                for row, new in zip(plan["rows"], new_rows):
                    row["done"], row["memo"] = bool(new["done"]), str(new["memo"] or "")
                st.rerun()
            c1, c2, c3 = st.columns(3)
            if c1.button("남은 기간으로 재조정", disabled=not active, use_container_width=True):
                outcome = planner.readjust(plan, today, hours or plan["weekly_hours"], f"지연 {info['delay_days']:g}일")
                st.session_state["flash"] = outcome["message"]
                st.rerun()
            c2.download_button("내보내기 (.md)", planner.space_markdown(S, info if active else None),
                               "study-space.md", "text/markdown", use_container_width=True)
            if c3.button("계획 삭제", use_container_width=True):
                S["plan"] = None
                st.rerun()
            if plan["history"]:
                st.caption("재조정 이력: " + " / ".join(plan["history"]))
            st.divider()
            ui.label("Notion 학습 공간")
            linked_url = (S.get("notion") or {}).get("url", "")
            st.caption((f"연결된 페이지가 있어요. Notion에서 완료를 체크한 뒤 '동기화'를 누르면 앱의 진행률·지연·재조정과 Notion 페이지가 맞춰져요."
                        if linked_url else "아직 연결된 페이지가 없어요. 처음이면 '새로 만들기', 이미 만든 페이지가 있으면 '동기화'에서 그 페이지 링크를 넣어 주세요."))
            n1, n2, n3 = st.columns(3)
            if n1.button("Notion과 동기화", type="primary", use_container_width=True):
                if remembered_token() and linked_url:
                    try:
                        with st.spinner("Notion을 읽고 다시 쓰는 중이에요…"):
                            run_sync(remembered_token(), linked_url, today, hours, active)
                    except notion.NotionError as error:
                        st.error(f"동기화하지 못했어요. {error}")
                else:
                    notion_sync_dialog(today, hours, active)
            if n2.button("Notion에 새로 만들기", use_container_width=True):
                notion_dialog(info if active else None)
            if linked_url:
                n3.link_button("Notion 페이지 열기", linked_url, use_container_width=True)
        elif not active:
            st.info(f"현재 상태는 '{target['state']}'예요. 새 목표가 정해지면 다시 계획을 세울 수 있어요.")
        else:
            ui.section("주차별 계획 만들기", "미리보기 → 동의 후 저장")
            ready = bool(exam and hours)
            if not exam:
                st.warning("확정된 시험일이 필요해요. '일정' 탭에서 확인하거나 직접 입력해 주세요.")
            if not hours:
                st.warning("'프로필' 탭에 주당 공부 가능 시간을 입력해 주세요.")
            required = st.number_input("강의·교재 총 분량을 안다면 필요 학습 시간 (선택, 모르면 0)", 0.0, 1000.0, 0.0, 5.0)
            if st.button("계획 미리보기", type="primary", disabled=not ready):
                do_plan(S, today)
            preview = S.get("plan_preview")
            if preview:
                st.dataframe(pd.DataFrame(preview["rows"])[["week", "phase", "start", "end", "hours", "task"]].rename(
                    columns={"week": "주차", "phase": "단계", "start": "시작", "end": "마감", "hours": "예상 시간", "task": "할 일"}),
                    hide_index=True, use_container_width=True)
                st.caption("단계 비율 " + " / ".join(f"{k} {v}%" for k, v in preview["weights"].items())
                           + f" · 총 {preview['total_hours']:g}시간 · 시험 직전 3일은 복습 · 강의 분량은 '분량 확인 필요'")
                warning = planner.capacity_check(preview, required)
                if warning:
                    st.warning(warning)
                if st.button("이 계획으로 저장할게요 (동의)", type="primary"):
                    S["plan"], S["plan_preview"], S["pending"] = preview, None, None
                    st.rerun()

with tab_space:
    with st.container(border=True, key="cardpath"):
        ui.section("강의·교재 추천", "비용 선호에 맞춘 기본 경로 + 대안")
        if not target.get("code"):
            st.caption("목표 자격증을 정하면 그 자격증의 강의·교재·기출 자료를 찾아 드려요.")
        else:
            ui.kv([("대상", target["name"]), ("비용 선호", P["cost_pref"] or "미입력 — '강의 무료·교재 구매' 기준"),
                   ("학습 방식", P["learning_style"] or "미입력"), ("주당 가용시간", f"{float(P['weekly_hours'] or 0):g}시간")])
            st.caption("검색 결과에 실제로 있는 강의·교재만 보여 주고, 후기는 2곳 이상에서 반복된 의견만 요약해요. 불법 복제 자료는 추천하지 않아요.")
            if not search:
                ui.box("웹 검색 키가 아직 없어 강의·교재 이름을 확인할 수 없어요. 확인하지 않은 자료 이름은 지어내지 않아요. 키를 넣으면 이 버튼으로 바로 찾아요.",
                       "blue", "지금은 일반 순서만 안내해요")
            if st.button("강의·교재 찾기", type="primary", key="find_path"):
                with st.spinner("강의·교재·기출 자료를 찾는 중이에요…"):
                    cert_for_path = BY_CODE.get(target["code"]) or target
                    S["study_path"] = {"cert": target["name"], "at": today.isoformat(),
                                       "text": engine.study_path(cert_for_path, P, llm, search, today)}
            found = S.get("study_path")
            if found and found.get("cert") == target["name"]:
                st.markdown(found["text"])
                st.caption(f"{found['at']} 기준 · 가격·무료 범위는 바뀔 수 있으니 구매 전에 원문을 확인해 주세요.")
            ui.label("기본 학습 순서")
            ui.table(["단계", "비중", "하는 일"], [
                ["개념", "40%", "강의·교재로 전체 범위 한 번 보기"], ["문제풀이", "25%", "단원별 문제 + 틀린 개념 다시 보기"],
                ["기출", "25%", "기출문제 회차 풀이 + 오답 정리"], ["모의·복습", "10%", "실전 모의고사, 시험 직전 3일은 복습만"]])

# ------------------------------------------------------------------ 프로필
with tab_profile:
    with st.form("profile"):
        ui.section("프로필", "필요한 것만 채우면 돼요 · 대화에서 말한 조건도 여기에 반영돼요")
        f1, f2 = st.columns(2)
        job = f1.text_input("진로 / 관심 직무", P["desired_job"], placeholder="예: 데이터 분석")
        style = f2.selectbox("학습 방식", ["", *engine.STYLE_OPTIONS], format_func=lambda v: v or "선택 안 함",
                             index=(["", *engine.STYLE_OPTIONS].index(P["learning_style"]) if P["learning_style"] in engine.STYLE_OPTIONS else 0))
        major = f1.text_input("전공·경험", P["major_experience"], placeholder="예: 경영학 전공, 인턴 3개월")
        cost = f2.selectbox("비용 선호", ["", *engine.COST_OPTIONS], format_func=lambda v: v or "선택 안 함",
                            index=(["", *engine.COST_OPTIONS].index(P["cost_pref"]) if P["cost_pref"] in engine.COST_OPTIONS else 0))
        hours = f1.number_input("주당 가용 시간", 0.0, 80.0, float(P["weekly_hours"] or 0), 0.5)
        days = f2.number_input("주당 공부 일수", 1, 7, int(P["study_days"] or 5))
        period = f1.text_input("목표 시기", P["target_period"], placeholder="예: 내년 상반기")
        owned = f2.text_input("보유 자격증 (쉼표로 구분)", ", ".join(P["owned"]))
        posting = st.text_area("관심 공고 (선택)", P["interest_posting"], height=90,
                               placeholder="채용공고 본문을 붙여 넣으면 취업 가이드라인을 만들어요.")
        if st.form_submit_button("저장", type="primary"):
            old_hours = P["weekly_hours"]
            P.update(desired_job=job.strip(), major_experience=major.strip(),
                     owned=[o.strip() for o in owned.split(",") if o.strip()], learning_style=style, cost_pref=cost,
                     weekly_hours=float(hours), study_days=int(days), target_period=period.strip(),
                     interest_posting=posting.strip())
            st.session_state["flash"] = ("주당 시간이 바뀌었어요. '계획' 탭에서 재조정할 수 있어요."
                                         if S.get("plan") and hours and hours != old_hours else "프로필을 저장했어요.")
            st.rerun()
    with st.container(border=True, key="card9"):
        ui.section("저장 상태", "")
        ui.table(["항목", "상태"], [
            ["계정", (f"{auth['nickname']}님 로그인 중 · 자동 저장", "good") if auth else ("로그인 전 · 창을 닫으면 사라져요", "warn")],
            ["저장 위치", store.label],
            ["AI 추천", ("연결됨", "good") if llm else ("미설정 · 규칙 기반으로 동작", "mute")],
            ["웹 검색", ("연결됨", "good") if search else ("미설정 · 직접 수집 가능한 사이트만", "mute")]])

# ------------------------------------------------------------------ 기능
with tab_more:
    with st.container(border=True, key="card10"):
        ui.section("취득 후 다음 경로", "결과를 알려 주면 다음 단계로 이어 줘요")
        ui.box("보유 자격증에 추가하고, 상태를 합격으로 바꾼 뒤 다음 자격증을 제안해요.", "green", "합격")
        ui.box("완료율이 가장 낮았던 단계를 알려 주고, 다음 회차 공식 일정을 확인한 뒤 그 단계 비중을 올린 계획을 제안해요.", "red", "불합격")
        r1, r2 = st.columns(2)
        r1.button("합격했어요", use_container_width=True, key="more_pass", on_click=queue, args=("합격했어",), disabled=not target.get("code"))
        r2.button("불합격했어요", use_container_width=True, key="more_fail", on_click=queue, args=("불합격했어",), disabled=not target.get("code"))
    with st.container(border=True, key="card11"):
        ui.section("보유 자격증·유효기간 관리", "이미 보유한 자격증은 다시 추천하지 않아요")
        if P["owned"]:
            ui.table(["보유 자격증"], [[name] for name in P["owned"]])
        else:
            st.caption("아직 없어요. '프로필' 탭에서 입력하거나 합격 소식을 알려 주세요.")
        S["validity_opt_in"] = st.toggle("유효기간 관리 사용 (원할 때만)", S["validity_opt_in"])
        if S["validity_opt_in"]:
            st.caption("어학 성적처럼 만료가 있는 자산의 취득일·만료일을 입력하면 유효 여부와 갱신 시점을 검토해요. 날짜 형식: YYYY-MM-DD")
            base = pd.DataFrame(S["assets"] or [{"name": "", "acquired": "", "expires": ""}], columns=["name", "acquired", "expires"])
            edited = st.data_editor(base, num_rows="dynamic", hide_index=True, use_container_width=True,
                                    column_config={"name": "자산 (자격증·어학 성적)", "acquired": "취득일", "expires": "만료일"},
                                    key="asset_editor")
            S["assets"] = [{k: ("" if pd.isna(v) else str(v)) for k, v in row.items()} for row in edited.to_dict("records")
                           if isinstance(row.get("name"), str) and row["name"].strip()]
            rows = engine.validity_review(S["assets"], today)
            if rows:
                st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
                st.caption("만료일은 입력하신 값 기준이에요. 기관별 유효기간 규정은 공식 사이트에서 확인해 주세요.")
        else:
            st.caption("꺼져 있으면 이름·등급만 확인하고 유효기간은 다루지 않아요.")
    with st.container(border=True, key="card12"):
        ui.section("연동", "모두 본인 계정에만, 동의한 뒤에만")
        ui.table(["기능", "어디서", "설명"], [
            ["Google Calendar", "일정 탭", "공식 확인된 일정 중 고른 것만 내 캘린더에 등록 · .ics 파일도 가능"],
            ["Notion", "계획 탭", "내 토큰으로 학습 공간 페이지 생성 · Notion에서 체크한 완료를 가져와 진행률·재조정을 맞추는 동기화"],
            ["취업 가이드라인", "프로필 탭 → 추천 탭", "관심 공고나 목표 직무가 있을 때만 작성"],
            ["내보내기", "계획 탭", "학습 공간을 마크다운(.md) 파일로 저장"]])
    with st.container(border=True, key="card13"):
        ui.section("이 코치가 지키는 규칙", "")
        ui.table(["규칙", "내용"], [
            ["공식 근거", "일정·응시료·응시자격은 공식 페이지 본문과 대조된 값만 표시하고, 나머지는 미확인으로 둬요."],
            ["실패 보고", "실패는 숨기지 않고 확정됨 / 확인 필요 / 못 함으로 나눠 알려요."],
            ["동의 우선", "계획 저장, 캘린더 등록, 보유 자격증 추가, 정보 저장은 동의한 뒤에만 해요."],
            ["과장 금지", "합격·취업을 보장하는 표현을 쓰지 않고, 불법 복제 자료를 추천하지 않아요."],
            ["참고자료", "국가기술자격 시험정보(2025-12-31), 공인민간자격 등록현황(2026-08-26)은 공식 원문을 못 읽었을 때만 '자료집 기준'으로 써요."]])

ui.footer("자격증 패스 코치 · 제작 mhyeon6224 · 일정·응시료는 공식 사이트에서 다시 확인해 주세요 · 취업·합격을 보장하지 않아요")

# ------------------------------------------------------------------ 자동 저장 (로그인한 경우에만)
if st.session_state.get("auth"):
    current = snapshot(st.session_state["S"])
    digest = hashlib.sha256(json.dumps(current, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()
    if st.session_state.get("saved_digest") != digest:
        try:
            storage.save(store, st.session_state["auth"], current)
            st.session_state["saved_digest"] = digest
        except storage.StoreError:
            st.toast("자동 저장에 실패했어요. 잠시 뒤 다시 시도할게요.", icon="⚠️")
