"""학습 계획·체크인·재조정·결과 반영 (스킬 study-loop-rules 이식).

규칙 요약
- 남은 주 수 = (시험일 − 오늘) ÷ 7, 시험 직전 3일은 복습으로 떼어 둔다.
- 단계 비율: 개념 40 / 문제풀이 25 / 기출 25 / 모의고사·복습 10 (문제풀이형은 25 / 35 / 30 / 10).
- 재조정 기준: 지연 3일 이상 또는 지연 시간이 주당 가용시간의 50% 초과.
- 재조정 원칙: 시험일 고정, 앞 단계(개념) 압축, 뒤 단계(기출·모의고사) 보호.
  남은 시간이 필요 시간의 70% 미만이면 자동 재배분 대신 사용자에게 선택지를 준다.
"""
from __future__ import annotations

from datetime import date, timedelta

PHASES = ["개념", "문제풀이", "기출", "모의고사·복습"]
BASE_WEIGHTS = {"개념": 40, "문제풀이": 25, "기출": 25, "모의고사·복습": 10}
SOLVER_WEIGHTS = {"개념": 25, "문제풀이": 35, "기출": 30, "모의고사·복습": 10}
TASKS = {
    "개념": "개념 학습 — 강의·교재 진도 나가기",
    "문제풀이": "단원별 문제풀이 + 틀린 개념 다시 보기",
    "기출": "기출문제 회차 풀이 + 오답 정리",
    "모의고사·복습": "실전 모의고사 + 취약 단원 복습",
    "직전 복습": "오답 노트·요약 정리 훑어보기 (새 내용 금지)",
}
REVIEW_DAYS = 3


def d(value) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def weights_for(style: str, boost_phase: str | None = None) -> dict[str, int]:
    weights = dict(SOLVER_WEIGHTS if "문제풀이" in (style or "") else BASE_WEIGHTS)
    if boost_phase in weights:  # 불합격 후 재도전: 가장 부족했던 단계 비중 +10%p
        donor = max((p for p in weights if p != boost_phase), key=lambda p: weights[p])
        weights[donor] -= 10
        weights[boost_phase] += 10
    return weights


def _half(value: float) -> float:
    return max(0.5, round(value * 2) / 2)


def build_plan(today: date, exam_date: date, weekly_hours: float, style: str = "",
               boost_phase: str | None = None) -> dict:
    """주차별 계획을 만든다. 저장 전 미리보기 용도로도 그대로 쓴다."""
    today, exam_date = d(today), d(exam_date)
    days_left = (exam_date - today).days
    if days_left < 1:
        raise ValueError("시험일이 오늘 이후여야 계획을 만들 수 있어요.")
    weights = weights_for(style, boost_phase)
    review_start = max(today, exam_date - timedelta(days=REVIEW_DAYS))
    study_days = (review_start - today).days
    rows: list[dict] = []
    if study_days >= 2:
        n_weeks = max(1, -(-study_days // 7))
        total = sum(weights.values())
        bounds, acc = [], 0
        for phase in PHASES:
            acc += weights[phase] / total
            bounds.append((acc, phase))
        for i in range(n_weeks):
            start = today + timedelta(days=7 * i)
            end = min(start + timedelta(days=6), review_start - timedelta(days=1))
            position = (i + 0.5) / n_weeks
            phase = next(p for limit, p in bounds if position <= limit + 1e-9)
            span = (end - start).days + 1
            rows.append({
                "week": i + 1, "phase": phase, "start": start.isoformat(), "end": end.isoformat(),
                "hours": _half(weekly_hours * span / 7), "task": TASKS[phase], "done": False, "done_at": "", "memo": "",
            })
    last_day = max(review_start, exam_date - timedelta(days=1))
    rows.append({
        "week": len(rows) + 1, "phase": "직전 복습", "start": review_start.isoformat(), "end": last_day.isoformat(),
        "hours": _half(weekly_hours * min(REVIEW_DAYS, max(1, days_left)) / 7), "task": TASKS["직전 복습"],
        "done": False, "done_at": "", "memo": "",
    })
    return {
        "rows": rows, "created": today.isoformat(), "last_progress": today.isoformat(), "exam_date": exam_date.isoformat(),
        "weekly_hours": weekly_hours, "weights": weights, "history": [],
        "weeks": max(1, round(days_left / 7)), "total_hours": sum(r["hours"] for r in rows),
    }


def capacity_check(plan: dict, required_hours: float | None) -> str | None:
    """필요 시간이 가용 시간을 넘으면 계획 확정 전에 선택지를 말한다."""
    if not required_hours or required_hours <= plan["total_hours"]:
        return None
    weeks = max(1, len(plan["rows"]) - 1)
    more = _half(required_hours / weeks)
    return (
        f"시험일까지 가용 시간은 총 {plan['total_hours']:g}시간인데, 입력하신 필요 학습량은 약 {required_hours:g}시간이에요.\n"
        f"1) 주당 시간을 {more:g}시간 정도로 늘리기  2) 강의 일부를 건너뛰고 기출 중심으로  3) 다음 회차로 목표 변경\n"
        "어떤 쪽이 좋을지 정한 뒤 계획을 확정해 주세요."
    )


def progress(plan: dict) -> dict:
    rows = plan["rows"]
    total = sum(r["hours"] for r in rows) or 1
    done = sum(r["hours"] for r in rows if r["done"])
    by_phase = {}
    for phase in [*PHASES, "직전 복습"]:
        items = [r for r in rows if r["phase"] == phase]
        if items:
            hours = sum(r["hours"] for r in items) or 1
            by_phase[phase] = round(100 * sum(r["hours"] for r in items if r["done"]) / hours)
    return {"percent": round(100 * done / total), "by_phase": by_phase}


def checkin(plan: dict, today: date, weekly_hours: float, study_days_per_week: int, target: dict) -> dict:
    """오늘 브리핑: 할 일 1~3개, 가장 가까운 마감, 지연 계산."""
    today = d(today)
    rows = plan["rows"]
    overdue = [r for r in rows if not r["done"] and d(r["end"]) < today]
    current = [r for r in rows if not r["done"] and d(r["start"]) <= today <= d(r["end"])]
    upcoming = [r for r in rows if not r["done"] and d(r["start"]) > today]
    delay_hours = sum(r["hours"] for r in overdue)
    per_day = max(0.25, weekly_hours / max(1, study_days_per_week))
    delay_days = round(delay_hours / per_day, 1)
    todo = (overdue + current)[:3] or upcoming[:1]
    # 마지막으로 완료 체크를 한 날부터 며칠이 지났는지(체크가 한 번도 없으면 계획을 만든 날부터)
    idle_days = max(0, (today - d(plan.get("last_progress") or plan["created"])).days)

    deadlines = []
    state = target.get("state", "준비중")
    for key, label in (("reg_end", "원서접수 마감"), ("exam_date", "시험일"), ("result_date", "합격자 발표")):
        value = target.get(key)
        if not value:
            continue
        if key == "reg_end" and state != "준비중":
            continue
        if key == "result_date" and state not in ("응시완료",):
            continue
        if d(value) >= today:
            deadlines.append((d(value), label))
    nearest = min(deadlines) if deadlines else None
    current_week = next((r["week"] for r in rows if d(r["start"]) <= today <= d(r["end"])), None)
    return {
        "today": today.isoformat(), "todo": todo, "delay_hours": delay_hours, "delay_days": delay_days,
        "needs_readjust": bool(overdue) and (delay_days >= 3 or delay_hours > weekly_hours * 0.5),
        "idle_days": idle_days, "suggest_shrink": idle_days >= 3 and bool(overdue or current),
        "nearest": {"date": nearest[0].isoformat(), "label": nearest[1], "dday": (nearest[0] - today).days} if nearest else None,
        "current_week": current_week, **progress(plan),
    }


def readjust(plan: dict, today: date, weekly_hours: float, reason: str) -> dict:
    """미완료 항목을 남은 기간에 다시 배분한다. 시험일은 건드리지 않는다.

    반환: {"status": "done"|"choice"|"noop", "message": str}
    """
    today = d(today)
    exam_date = d(plan["exam_date"])
    review_start = max(today, exam_date - timedelta(days=REVIEW_DAYS))
    rows = plan["rows"]
    pending = [r for r in rows if not r["done"] and r["phase"] != "직전 복습"]
    if not pending:
        return {"status": "noop", "message": "재조정할 미완료 항목이 없어요."}
    span = (review_start - today).days
    needed = sum(r["hours"] for r in pending)
    capacity = weekly_hours * span / 7
    if span < 1 or capacity < needed * 0.7:
        return {
            "status": "choice",
            "message": (
                f"남은 공부 가능 시간은 약 {max(capacity, 0):.1f}시간인데 미완료 분량은 {needed:g}시간이에요. "
                "자동으로 줄이기엔 차이가 커서 직접 골라 주세요.\n"
                "1) 주당 시간 늘리기  2) 개념 강의 일부를 건너뛰고 기출 중심으로  3) 다음 회차로 목표 변경"
            ),
        }
    cut = max(0.0, needed - capacity)
    compressed = False
    for phase in ("개념", "문제풀이"):  # 앞 단계부터 압축, 기출·모의고사는 보호
        items = [r for r in pending if r["phase"] == phase]
        room = sum(r["hours"] for r in items) * 0.5
        if cut <= 0 or not items or room <= 0:
            continue
        take = min(cut, room)
        ratio = take / sum(r["hours"] for r in items)
        for r in items:
            r["hours"] = _half(r["hours"] * (1 - ratio))
        cut -= take
        compressed = True
    total = sum(r["hours"] for r in pending) or 1
    cursor = 0.0
    stamp = f"재조정 {today.isoformat()}: {reason}" + (" · 개념 단계 압축" if compressed else " · 균등 재배분")
    for r in pending:
        start = today + timedelta(days=int(cursor))
        cursor += span * r["hours"] / total
        end = max(start, today + timedelta(days=max(int(cursor) - 1, 0)))
        end = min(end, review_start - timedelta(days=1)) if review_start > today else start
        r["start"], r["end"] = start.isoformat(), max(start, end).isoformat()
        r["memo"] = stamp
    plan["weekly_hours"] = weekly_hours
    plan["total_hours"] = sum(r["hours"] for r in rows)
    plan["history"].append(stamp)
    return {"status": "done", "message": f"시험일은 그대로 두고 미완료 {len(pending)}개 항목을 다시 배분했어요. ({stamp})"}


def mark_progress(plan: dict, today: date) -> None:
    """완료 체크가 새로 생긴 날을 기록한다('3일 연속 미완료' 판단에 쓴다)."""
    plan["last_progress"] = d(today).isoformat()


def set_done(plan: dict, row: dict, done: bool, today: date) -> None:
    """완료 여부를 바꾸면서 완료일도 함께 적는다(체크를 풀면 완료일을 지운다)."""
    done = bool(done)
    if done and not row.get("done"):
        row["done_at"] = d(today).isoformat()
        mark_progress(plan, today)
    elif not done:
        row["done_at"] = ""
    row["done"] = done


def weakest_phase(plan: dict) -> tuple[str, int] | None:
    """불합격 반영: 완료율이 가장 낮았던 단계를 사실로만 돌려준다."""
    by_phase = {p: v for p, v in progress(plan)["by_phase"].items() if p in PHASES}
    if not by_phase:
        return None
    phase = min(by_phase, key=lambda p: by_phase[p])
    return phase, by_phase[phase]


def briefing_text(info: dict, cert_name: str) -> str:
    lines = [f"**오늘 브리핑 — {cert_name} ({info['today']})**"]
    near = info["nearest"]
    if near and near["dday"] <= 3:
        lines.append(f"**{near['label']} D-{near['dday']}** ({near['date']})")
    if info["todo"]:
        items = []
        for r in info["todo"]:
            late = " _(지연)_" if d(r["end"]) < d(info["today"]) else ""
            items.append(f"- {r['week']}주차 · {r['phase']} — {r['task']} ({r['hours']:g}시간){late}")
        lines.append("오늘 할 일\n" + "\n".join(items))
    else:
        lines.append("남은 할 일이 없어요. 계획을 모두 마쳤어요.")
    if near and near["dday"] > 3:
        lines.append(f"가장 가까운 마감: {near['label']} D-{near['dday']} ({near['date']})")
    lines.append(f"진행률 {info['percent']}% · 지연 {info['delay_days']:g}일({info['delay_hours']:g}시간)")
    if info["needs_readjust"]:
        lines.append("지연이 재조정 기준(3일 이상 또는 주당 시간의 50% 초과)을 넘었어요. 학습 공간에서 재조정할 수 있어요.")
    if info["suggest_shrink"]:
        lines.append(f"{info.get('idle_days', 3)}일째 완료 체크가 없어요. 계획을 줄이고 싶으면 채팅에서 '계획 줄여줘'라고 말해 주세요.")
    return "\n\n".join(lines)


def to_ics(events: list[dict]) -> str:
    """동의한 공식 일정만 담은 캘린더 파일(.ics). events: [{"title","date"}]"""
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//cert-path-coach//KO", "CALSCALE:GREGORIAN"]
    for i, event in enumerate(events):
        day = d(event["date"])
        lines += [
            "BEGIN:VEVENT", f"UID:cert-coach-{day:%Y%m%d}-{i}@cert-path-coach",
            f"DTSTAMP:{day:%Y%m%d}T000000Z", f"DTSTART;VALUE=DATE:{day:%Y%m%d}",
            f"DTEND;VALUE=DATE:{day + timedelta(days=1):%Y%m%d}", f"SUMMARY:{event['title']}",
            f"DESCRIPTION:{event.get('note', '')}", "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def gcal_link(event: dict) -> str:
    """Google Calendar 일정 추가 화면 링크. 사용자가 직접 '저장'을 눌러야 등록된다."""
    from urllib.parse import urlencode

    day = d(event["date"])
    query = urlencode({"action": "TEMPLATE", "text": event["title"], "details": event.get("note", ""),
                       "dates": f"{day:%Y%m%d}/{day + timedelta(days=1):%Y%m%d}"})
    return "https://calendar.google.com/calendar/render?" + query


def space_markdown(state: dict, info: dict | None) -> str:
    """Notion 학습 공간과 같은 섹션 순서의 마크다운 내보내기."""
    profile, target, plan = state["profile"], state["target"], state.get("plan")
    out = [f"# {target.get('name', '자격증')} 학습 공간", ""]
    if info:
        out += [briefing_text(info, target.get("name", "")), ""]
    out += [
        "## 목표",
        f"- 자격증: {target.get('name', '미정')} / 희망 진로: {profile.get('desired_job') or '미입력'}",
        f"- 상태: {target.get('state', '준비중')} / 목표 시험일: {target.get('exam_date') or '미확인'}", "",
        "## 공식 일정",
        f"- 원서접수: {target.get('reg_start') or '미확인'} ~ {target.get('reg_end') or '미확인'}",
        f"- 시험일: {target.get('exam_date') or '미확인'} / 합격자 발표: {target.get('result_date') or '미확인'}",
        f"- 응시료: {target.get('fee') or '미확인'}",
        f"- 근거: {target.get('basis') or '미확인'} / 링크: {target.get('source_url') or '미확인'} / 확인 날짜: {target.get('checked_at') or '미확인'}", "",
        "## 학습 조건",
        f"- 학습 방식: {profile.get('learning_style') or '미입력'} / 비용 기준: {profile.get('cost_pref') or '미입력'}",
        f"- 주당 가용시간: {profile.get('weekly_hours') or '미입력'}시간 · 주 {profile.get('study_days') or '미입력'}일",
        f"- 보유 자격증: {', '.join(profile.get('owned') or []) or '없음'}", "",
    ]
    if plan:
        stats = progress(plan)
        out += ["## 진행률", f"- 전체 {stats['percent']}% / 단계별: " + ", ".join(f"{k} {v}%" for k, v in stats["by_phase"].items())]
        out += [f"- 재조정 이력: {'; '.join(plan['history']) or '없음'}", "", "## 주차별 계획", "",
                "| 주차 | 단계 | 기간 | 예상 시간 | 할 일 | 완료 | 완료일 | 메모 |", "| --- | --- | --- | --- | --- | --- | --- | --- |"]
        for r in plan["rows"]:
            out.append(f"| {r['week']} | {r['phase']} | {r['start']} ~ {r['end']} | {r['hours']:g}h | {r['task']} | {'완료' if r['done'] else '-'} | {r.get('done_at') or ''} | {r['memo']} |")
    return "\n".join(out) + "\n"
