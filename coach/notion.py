"""사용자별 Notion 연동 — 사용자가 본인 Integration 토큰과 페이지 링크를 넣으면 그 페이지 아래에 학습 공간을 만든다.

- 토큰은 이 브라우저 세션에만 보관하고 DB에 저장하지 않는다(다른 서비스의 비밀 키이기 때문).
- 페이지는 스킬의 학습 공간 섹션 순서를 그대로 따른다: 오늘 브리핑 → 목표 → 공식 일정 → 학습 조건 → 진행률 → 주차별 계획.
- 주차별 계획은 체크박스(to_do)로 만들어 Notion에서 바로 완료 체크할 수 있다.
"""
from __future__ import annotations

import re
import time

import requests

from . import plan as planner

API = "https://api.notion.com/v1"
VERSION = "2022-06-28"
VIEWS_VERSION = "2026-03-11"  # 데이터베이스 보기(달력) API는 새 버전에서만 된다
TOKEN_PATTERN = re.compile(r"^(ntn_|secret_)[A-Za-z0-9]{20,}$")


class NotionError(RuntimeError):
    """사용자에게 그대로 보여 줄 수 있는 실패 이유."""


def page_id_from(link: str) -> str | None:
    """Notion 페이지 링크나 ID에서 32자리 ID를 뽑는다."""
    cleaned = (link or "").split("?")[0].split("#")[0].replace("-", "")
    match = re.search(r"([0-9a-fA-F]{32})$", cleaned)
    if not match:
        return None
    raw = match.group(1).lower()
    return f"{raw[:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:]}"


def token_looks_valid(token: str) -> bool:
    return bool(TOKEN_PATTERN.match((token or "").strip()))


def _headers(token: str, version: str = VERSION) -> dict:
    return {"Authorization": f"Bearer {token.strip()}", "Notion-Version": version, "Content-Type": "application/json"}


def _text(content: str, bold: bool = False, link: str | None = None) -> dict:
    rich = {"type": "text", "text": {"content": content[:1900]}}
    if link:
        rich["text"]["link"] = {"url": link}
    if bold:
        rich["annotations"] = {"bold": True}
    return rich


def _block(kind: str, *parts: dict, **extra) -> dict:
    return {"object": "block", "type": kind, kind: {"rich_text": list(parts), **extra}}


def _heading(content: str) -> dict:
    return _block("heading_2", _text(content))


def _bullet(label: str, value: str) -> dict:
    return _block("bulleted_list_item", _text(f"{label}: ", bold=True), _text(value or "미확인"))


def build_blocks(state: dict, info: dict | None) -> list[dict]:
    profile, target, plan = state["profile"], state["target"], state.get("plan")
    blocks: list[dict] = []
    if info:
        lines = [f"오늘 할 일: " + (" / ".join(f"{r['week']}주차 {r['phase']}" for r in info["todo"]) or "없음")]
        if info["nearest"]:
            lines.append(f"가장 가까운 마감: {info['nearest']['label']} D-{info['nearest']['dday']} ({info['nearest']['date']})")
        lines.append(f"진행률 {info['percent']}% · 지연 {info['delay_days']:g}일")
        blocks.append(_block("callout", _text("\n".join(lines)), icon={"type": "emoji", "emoji": "📌"}))
    blocks += [
        _heading("🎯 목표"),
        _bullet("자격증", target.get("name", "")), _bullet("희망 진로", profile.get("desired_job", "")),
        _bullet("상태", target.get("state", "준비중")), _bullet("목표 시험일", target.get("exam_date") or ""),
        _heading("🗓 공식 일정"),
        _bullet("원서접수", f"{target.get('reg_start') or '미확인'} ~ {target.get('reg_end') or '미확인'}"),
        _bullet("시험일", target.get("exam_date") or ""), _bullet("합격자 발표", target.get("result_date") or ""),
        _bullet("응시료", target.get("fee") or ""),
        _bullet("근거", f"{target.get('basis') or '미확인'} (확인 {target.get('checked_at') or '—'})"),
    ]
    if target.get("source_url"):
        blocks.append(_block("bulleted_list_item", _text("공식 링크", link=target["source_url"])))
    blocks += [
        _heading("👤 학습 조건"),
        _bullet("학습 방식", profile.get("learning_style", "")), _bullet("비용 기준", profile.get("cost_pref", "")),
        _bullet("주당 가용시간", f"{profile.get('weekly_hours') or 0:g}시간 · 주 {profile.get('study_days') or 5}일"),
        _bullet("보유 자격증", ", ".join(profile.get("owned") or []) or "없음"),
    ]
    if plan:
        stats = planner.progress(plan)
        blocks += [_heading("📊 진행률"), _bullet("전체", f"{stats['percent']}%"),
                   _bullet("단계별", ", ".join(f"{k} {v}%" for k, v in stats["by_phase"].items())),
                   _bullet("재조정 이력", "; ".join(plan["history"]) or "없음"),
                   _heading("📅 주차별 계획")]
        for row in plan["rows"]:
            label = f"{row['week']}주차 · {row['phase']} ({row['start']} ~ {row['end']}, {row['hours']:g}h) — {row['task']}"
            if row.get("done") and row.get("done_at"):
                label += f" · 완료 {row['done_at']}"
            if row.get("memo"):
                label += f"  [{row['memo']}]"
            blocks.append(_block("to_do", _text(label), checked=bool(row["done"])))
    if (state.get("study_path") or {}).get("text") and state["study_path"].get("cert") == target.get("name"):
        blocks += [_heading("📚 자료"), _block("paragraph", _text(re.sub(r"[*_`#>]", "", state["study_path"]["text"])))]
    blocks.append(_block("paragraph", _text("자격증 패스 코치에서 만든 페이지예요. 완료는 여기서 체크하고, 앱의 'Notion과 동기화'를 누르면 진행률·브리핑·계획이 맞춰져요.")))
    return blocks[:100]  # Notion은 한 번에 블록 100개까지 받는다


def create_space(token: str, parent_link: str, state: dict, info: dict | None) -> dict:
    """학습 공간 페이지를 만든다. 반환: {"url": 페이지 주소, "calendar": 달력 결과 또는 None, "calendar_error": 실패 이유 또는 None}"""
    if not token_looks_valid(token):
        raise NotionError("토큰 형식이 아니에요. 'ntn_' 또는 'secret_'로 시작하는 토큰을 넣어 주세요.")
    parent = page_id_from(parent_link)
    if not parent:
        raise NotionError("페이지 링크에서 페이지 ID를 찾지 못했어요. Notion 페이지의 '링크 복사' 주소를 그대로 붙여 넣어 주세요.")
    title = f"{state['target'].get('name') or '자격증'} 학습 공간"
    body = {"parent": {"page_id": parent}, "icon": {"type": "emoji", "emoji": "📚"},
            "properties": {"title": {"title": [_text(title)]}}, "children": build_blocks(state, info)}
    try:
        response = requests.post(f"{API}/pages", headers=_headers(token), json=body, timeout=20)
    except requests.RequestException:
        raise NotionError("Notion 서버에 연결하지 못했어요. 잠시 뒤 다시 시도해 주세요.") from None
    if response.status_code != 200:
        code = (response.json() if response.headers.get("content-type", "").startswith("application/json") else {}).get("code", "")
        reasons = {
            "unauthorized": "토큰이 맞지 않아요. 토큰을 다시 복사해 주세요.",
            "object_not_found": "그 페이지에 접근 권한이 없어요. 페이지를 연 뒤 오른쪽 위 ⋯ → 연결(Connections)에서 만든 연결을 추가해 주세요.",
            "restricted_resource": "연결에 콘텐츠 쓰기 권한이 없어요. 연결 설정의 Capabilities에서 'Insert content'를 켜 주세요.",
            "validation_error": "Notion이 페이지 형식을 받지 않았어요. 잠시 뒤 다시 시도해 주세요.",
            "rate_limited": "요청이 너무 많아요. 잠시 뒤 다시 시도해 주세요.",
        }
        raise NotionError(reasons.get(code, f"페이지를 만들지 못했어요 (HTTP {response.status_code})."))
    data = response.json()
    result = {"url": data.get("url", ""), "calendar": None, "calendar_error": None}
    try:  # 페이지는 이미 만들어졌으므로, 달력 실패는 따로 알린다
        result["calendar"] = ensure_calendar(token, data["id"], [], state["target"])
    except NotionError as error:
        result["calendar_error"] = str(error)
    return result


# ---------------------------------------------------------------- 주요 일정 달력 (학습 공간 안의 데이터베이스)
CAL_TITLE = "주요 일정"


def calendar_events(target: dict) -> list[dict]:
    """공식 확인된 날짜만 달력에 넣는다. 날짜를 모르는 일정은 날짜 없이 '확인 필요'로 남긴다."""
    name, basis = target.get("name") or "자격증", target.get("basis") or "미확인"
    events = []
    for key, label, kind in (("reg_start", "원서접수 시작", "접수"), ("reg_end", "원서접수 마감", "접수"),
                             ("exam_date", "시험일", "시험"), ("result_date", "합격자 발표", "발표")):
        if target.get(key):
            events.append({"title": f"[{name}] {label}", "date": target[key], "kind": kind, "memo": f"근거: {basis}"})
    if target.get("venue_notice"):
        events.append({"title": f"[{name}] 수험표 출력·고사장(자리) 공지 시작", "date": target["venue_notice"], "kind": "확인 필요",
                       "memo": f"근거: {basis} · 주관기관 일정표의 장소공고 시작일"})
    else:
        events.append({"title": f"[{name}] 수험표 출력·고사장(자리) 공지", "date": None, "kind": "확인 필요",
                       "memo": "날짜 미확인 — 주관기관 공지에서 확인한 뒤 날짜를 직접 넣어 주세요"})
    return events


def _event_props(event: dict) -> dict:
    props = {"일정": {"title": [_text(event["title"])]}, "종류": {"select": {"name": event["kind"]}},
             "메모": {"rich_text": [_text(event["memo"])]}}
    if event["date"]:
        props["날짜"] = {"date": {"start": event["date"]}}
    return props


def _calendar_view(token: str, database: str, source: str, fresh: bool) -> str:
    """'주요 일정'에 달력 보기가 없으면 만든다. 반환: "있음" | "만듦" """
    listed = _request("GET", f"{API}/views", token, VIEWS_VERSION, params={"database_id": database, "page_size": 50}).get("results", [])
    views = [_request("GET", f"{API}/views/{v['id']}", token, VIEWS_VERSION) for v in listed[:10]]
    if any(v.get("type") == "calendar" for v in views):
        return "있음"
    props = _request("GET", f"{API}/data_sources/{source}", token, VIEWS_VERSION).get("properties", {})
    date_id = (props.get("날짜") or {}).get("id")
    if not date_id:
        raise NotionError("'날짜' 속성을 찾지 못해 달력 보기를 만들지 못했어요.")
    _request("POST", f"{API}/views", token, VIEWS_VERSION, json={
        "database_id": database, "data_source_id": source, "name": "달력", "type": "calendar", "position": {"type": "start"},
        "configuration": {"type": "calendar", "date_property_id": date_id, "view_range": "month", "show_weekends": True}})
    if fresh:  # 방금 만든 DB라면 자동으로 생긴 표 보기는 지워 달력만 남긴다 (실패해도 문제없음)
        for view in views:
            if view.get("type") == "table":
                try:
                    _request("DELETE", f"{API}/views/{view['id']}", token, VIEWS_VERSION)
                except NotionError:
                    pass
    return "만듦"


def ensure_calendar(token: str, page_id: str, blocks: list[dict], target: dict) -> dict:
    """학습 공간 페이지 안에 '주요 일정' 데이터베이스(달력 보기)를 만들거나, 이미 있으면 빠진 일정을 넣고 바뀐 날짜를 고친다."""
    existing: dict[str, tuple[str, str | None]] = {}
    found = next((b for b in blocks if b.get("type") == "child_database" and (b.get("child_database") or {}).get("title") == CAL_TITLE), None)
    result = {"created": False, "added": 0, "updated": 0, "view": None, "view_error": None}
    if found:
        database = found["id"]
        source = (_request("GET", f"{API}/databases/{database}", token, VIEWS_VERSION).get("data_sources") or [{}])[0].get("id")
        if not source:
            raise NotionError("'주요 일정' 데이터베이스를 읽지 못했어요.")
        rows = _request("POST", f"{API}/data_sources/{source}/query", token, VIEWS_VERSION, json={"page_size": 100}).get("results", [])
        for row in rows:
            props = row.get("properties", {})
            title = "".join(t.get("plain_text", "") for t in (props.get("일정") or {}).get("title", []))
            existing[title] = (row["id"], ((props.get("날짜") or {}).get("date") or {}).get("start"))
    else:
        made = _request("POST", f"{API}/databases", token, VIEWS_VERSION, json={
            "parent": {"type": "page_id", "page_id": page_id}, "is_inline": True,
            "title": [_text(CAL_TITLE)], "icon": {"type": "emoji", "emoji": "🗓"},
            "initial_data_source": {"properties": {
                "일정": {"title": {}}, "날짜": {"date": {}}, "메모": {"rich_text": {}},
                "종류": {"select": {"options": [{"name": "접수", "color": "blue"}, {"name": "시험", "color": "red"},
                                                {"name": "발표", "color": "green"}, {"name": "확인 필요", "color": "gray"}]}}}}})
        database, source = made["id"], (made.get("data_sources") or [{}])[0].get("id")
        if not source:
            raise NotionError("'주요 일정' 데이터베이스를 만들었지만 내용을 넣을 위치를 찾지 못했어요.")
        result["created"] = True
    for event in calendar_events(target):
        if event["title"] not in existing:
            _request("POST", f"{API}/pages", token, VIEWS_VERSION,
                     json={"parent": {"type": "data_source_id", "data_source_id": source}, "properties": _event_props(event)})
            result["added"] += 1
        elif event["date"] and existing[event["title"]][1] != event["date"]:
            _request("PATCH", f"{API}/pages/{existing[event['title']][0]}", token, VIEWS_VERSION,
                     json={"properties": {"날짜": {"date": {"start": event["date"]}}}})
            result["updated"] += 1
        else:
            continue
        time.sleep(0.35)
    try:
        result["view"] = _calendar_view(token, database, source, result["created"])
    except NotionError as error:
        result["view_error"] = str(error)
    return result


# ---------------------------------------------------------------- 동기화 (Notion ↔ 앱)
# 스킬 규칙: 사용자는 Notion에서 직접 완료를 체크하고, 체크인은 그 체크를 읽어 지연을 계산한 뒤
# 진행률·오늘 브리핑·(재조정된) 계획을 같은 페이지에 다시 쓴다. 새 페이지는 만들지 않는다.
WEEK = re.compile(r"^\s*(\d+)주차")


def _plain(block: dict) -> str:
    """Notion에서 읽은 블록과 앱이 만든 블록 모두에서 글자만 뽑는다."""
    parts = (block.get(block.get("type", ""), {}) or {}).get("rich_text") or []
    return "".join(p.get("plain_text") or (p.get("text") or {}).get("content", "") for p in parts)


def _key(block: dict):
    kind, text = block.get("type"), _plain(block)
    if kind == "callout":
        return ("callout",)
    if kind == "to_do":
        match = WEEK.match(text)
        return ("todo", int(match.group(1))) if match else None
    if kind == "bulleted_list_item" and ": " in text:
        return ("bullet", text.split(": ", 1)[0])
    return None


def _request(method: str, url: str, token: str, version: str = VERSION, **kwargs) -> dict:
    for attempt in range(3):
        try:
            response = requests.request(method, url, headers=_headers(token, version), timeout=20, **kwargs)
        except requests.RequestException:
            raise NotionError("Notion 서버에 연결하지 못했어요. 잠시 뒤 다시 시도해 주세요.") from None
        if response.status_code == 429 and attempt < 2:
            time.sleep(1.5)
            continue
        if response.status_code == 200:
            return response.json()
        code = (response.json() if response.headers.get("content-type", "").startswith("application/json") else {}).get("code", "")
        reasons = {"unauthorized": "토큰이 맞지 않아요. Integration의 Secret을 다시 복사해 주세요.",
                   "object_not_found": "그 페이지를 찾지 못했어요. 앱이 만든 '학습 공간' 페이지의 링크인지, 연결(Connections)이 되어 있는지 확인해 주세요.",
                   "restricted_resource": "Integration에 읽기·쓰기 권한이 없어요. Capabilities에서 Read·Update·Insert content를 켜 주세요."}
        detail = ""
        try:
            detail = str(response.json().get("message", ""))[:160]
        except ValueError:
            pass
        raise NotionError(reasons.get(code, f"Notion 요청에 실패했어요 (HTTP {response.status_code}{' · ' + detail if detail else ''})."))
    raise NotionError("요청이 너무 많아요. 잠시 뒤 다시 시도해 주세요.")


def read_blocks(token: str, page_link: str) -> list[dict]:
    """학습 공간 페이지의 블록을 모두 읽는다."""
    if not token_looks_valid(token):
        raise NotionError("토큰 형식이 아니에요. 'ntn_' 또는 'secret_'로 시작하는 값을 넣어 주세요.")
    page = page_id_from(page_link)
    if not page:
        raise NotionError("학습 공간 페이지 링크에서 페이지 ID를 찾지 못했어요. 그 페이지의 '링크 복사' 주소를 붙여 넣어 주세요.")
    blocks, cursor = [], None
    for _ in range(10):
        data = _request("GET", f"{API}/blocks/{page}/children", token,
                        params={"page_size": 100, **({"start_cursor": cursor} if cursor else {})})
        blocks += data.get("results", [])
        cursor = data.get("next_cursor")
        if not data.get("has_more"):
            break
    return blocks


def pull_checks(blocks: list[dict], plan: dict) -> dict:
    """Notion의 완료 체크를 앱 계획에 반영한다. 반환: {"found": 찾은 주차 수, "changed": [(주차, 완료 여부)]}"""
    checked = {key[1]: bool(b["to_do"].get("checked")) for b in blocks if (key := _key(b)) and key[0] == "todo"}
    changed = []
    for row in plan["rows"]:
        if row["week"] in checked and bool(row["done"]) != checked[row["week"]]:
            row["done"] = checked[row["week"]]
            changed.append((row["week"], row["done"]))
    return {"found": len(checked), "changed": changed}


def push_updates(token: str, blocks: list[dict], state: dict, info: dict | None) -> dict:
    """오늘 브리핑·상태·진행률·주차별 계획(날짜·시간·메모·완료)을 기존 블록에 덮어쓴다. 사용자가 따로 적은 내용은 건드리지 않는다."""
    fresh = {key: block for block in build_blocks(state, info) if (key := _key(block))}
    updated = missing = 0
    seen = set()
    for block in blocks:
        key = _key(block)
        if not key or key in seen or key not in fresh:
            continue
        seen.add(key)
        new = fresh[key]
        kind = new["type"]
        same_text = _plain(block) == _plain(new)
        same_check = kind != "to_do" or bool(block["to_do"].get("checked")) == bool(new["to_do"].get("checked"))
        if same_text and same_check:
            continue
        payload = {"rich_text": new[kind]["rich_text"]}
        if kind == "to_do":
            payload["checked"] = new["to_do"]["checked"]
        _request("PATCH", f"{API}/blocks/{block['id']}", token, json={kind: payload})
        updated += 1
        time.sleep(0.35)  # Notion 요청 한도(초당 약 3회)를 넘지 않게
    missing = len([k for k in fresh if k[0] == "todo" and k not in seen])
    return {"updated": updated, "missing_weeks": missing}
