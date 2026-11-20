"""사용자별 Google Calendar 연동 (OAuth 2.0).

흐름
1. 로그인한 사용자가 "Google Calendar 연결"을 누르면, 1회용 state 값을 DB에 저장하고 Google 동의 화면을 새 탭으로 연다.
2. 사용자가 본인 Google 계정으로 동의하면 Google이 앱 주소로 ?code=...&state=... 를 붙여 돌려보낸다.
3. 앱은 state로 사용자를 찾아 code를 토큰으로 바꾸고, 그 사용자 계정에 refresh token을 저장한다.
4. 이후 그 사용자가 고른 일정만 본인 캘린더(primary)에 등록한다. 동의하지 않은 일정은 만들지 않는다.

필요한 설정(Secrets): GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI(배포된 앱 주소)
범위: calendar.events (일정 만들기만. 다른 일정 읽기·삭제 권한 없음)
"""
from __future__ import annotations

import secrets as pysecrets
import time
from datetime import timedelta
from urllib.parse import urlencode

import requests

from .plan import d
from .services import secret

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
SCOPE = "https://www.googleapis.com/auth/calendar.events"
STATE_TTL = 600  # 동의 화면에서 10분 안에 돌아와야 한다


class CalendarError(RuntimeError):
    """Google Calendar 호출 실패 (사용자에게 그대로 보여 줄 수 있는 문장)."""


def config() -> dict | None:
    cid, csec, redirect = secret("GOOGLE_CLIENT_ID"), secret("GOOGLE_CLIENT_SECRET"), secret("GOOGLE_REDIRECT_URI")
    return {"client_id": cid, "client_secret": csec, "redirect_uri": redirect} if cid and csec and redirect else None


def new_state() -> dict:
    return {"value": pysecrets.token_urlsafe(32), "created": int(time.time())}


def state_valid(stored: dict | None, value: str) -> bool:
    return bool(stored and value and pysecrets.compare_digest(stored.get("value", ""), value)
                and time.time() - stored.get("created", 0) <= STATE_TTL)


def auth_link(cfg: dict, state: str) -> str:
    return AUTH_URL + "?" + urlencode({
        "client_id": cfg["client_id"], "redirect_uri": cfg["redirect_uri"], "response_type": "code",
        "scope": SCOPE, "access_type": "offline", "prompt": "consent", "include_granted_scopes": "true",
        "state": state,
    })


def exchange_code(cfg: dict, code: str) -> dict:
    try:
        response = requests.post(TOKEN_URL, timeout=15, data={
            "code": code, "client_id": cfg["client_id"], "client_secret": cfg["client_secret"],
            "redirect_uri": cfg["redirect_uri"], "grant_type": "authorization_code"})
    except requests.RequestException:
        raise CalendarError("Google 서버에 연결하지 못했어요.") from None
    if response.status_code != 200:
        raise CalendarError("Google 연결을 완료하지 못했어요. 처음부터 다시 연결해 주세요.")
    data = response.json()
    if not data.get("refresh_token"):
        raise CalendarError("Google이 장기 연결 권한을 주지 않았어요. 연결을 해제한 뒤 다시 시도해 주세요.")
    return {"refresh_token": data["refresh_token"], "connected_at": int(time.time())}


def _access_token(cfg: dict, refresh_token: str) -> str:
    try:
        response = requests.post(TOKEN_URL, timeout=15, data={
            "refresh_token": refresh_token, "client_id": cfg["client_id"], "client_secret": cfg["client_secret"],
            "grant_type": "refresh_token"})
    except requests.RequestException:
        raise CalendarError("Google 서버에 연결하지 못했어요.") from None
    if response.status_code != 200:
        raise CalendarError("Google 연결이 만료됐어요. 다시 연결해 주세요.")
    return response.json()["access_token"]


def event_body(event: dict) -> dict:
    day = d(event["date"])
    return {
        "summary": event["title"],
        "description": (event.get("note") or "") + "\n\n자격증 패스 코치에서 등록한 일정",
        "start": {"date": day.isoformat()}, "end": {"date": (day + timedelta(days=1)).isoformat()},
        "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": 24 * 60}]},
        # 같은 일정을 두 번 만들지 않도록 표시를 남긴다
        "extendedProperties": {"private": {"certCoachKey": event_key(event)}},
    }


def event_key(event: dict) -> str:
    return f"{event['title']}|{event['date']}"


def insert_events(cfg: dict, refresh_token: str, events: list[dict]) -> list[dict]:
    """동의한 일정만 등록한다. 이미 있는 일정은 건너뛴다. 결과: [{"title","date","status","link"}]"""
    token = _access_token(cfg, refresh_token)
    headers = {"Authorization": f"Bearer {token}"}
    results = []
    for event in events:
        key = event_key(event)
        try:
            found = requests.get(EVENTS_URL, headers=headers, timeout=15,
                                 params={"privateExtendedProperty": f"certCoachKey={key}", "maxResults": 1})
            if found.status_code == 200 and found.json().get("items"):
                item = found.json()["items"][0]
                results.append({**event, "status": "이미 등록됨", "link": item.get("htmlLink", "")})
                continue
            created = requests.post(EVENTS_URL, headers=headers, json=event_body(event), timeout=15)
            if created.status_code in (200, 201):
                results.append({**event, "status": "등록 완료", "link": created.json().get("htmlLink", "")})
            else:
                results.append({**event, "status": f"실패 (HTTP {created.status_code})", "link": ""})
        except requests.RequestException:
            results.append({**event, "status": "실패 (네트워크)", "link": ""})
    return results


def revoke(refresh_token: str) -> None:
    try:
        requests.post(REVOKE_URL, params={"token": refresh_token}, timeout=10)
    except requests.RequestException:
        pass
