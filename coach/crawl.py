"""주관기관 공식 일정 페이지 직접 수집.

일정표가 HTML에 그대로 들어 있는 사이트는 검색·AI 없이 페이지를 직접 읽어 규칙으로 파싱한다.
(화면을 자바스크립트로 그리는 사이트는 여기서 읽을 수 없어 검색 경로로 넘긴다.)
파싱 결과는 페이지에 적힌 값 그대로이며, 페이지 구조가 바뀌어 읽지 못하면 빈 결과를 돌려준다.
"""
from __future__ import annotations

import re
from datetime import date

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept-Language": "ko",
}
DATAQ_URL = "https://www.dataq.or.kr/www/accept/schedule.do"
TOEIC_URL = "https://exam.toeic.co.kr/receipt/examSchList.php"
KACPTA_URL = "https://license.kacpta.or.kr/web/info/info_diary.aspx"
KACPTA_CODES = {"ACCOUNT_1", "TAX_2", "ADHOC_전산세무회계"}
DATAQ_SECTIONS = ["빅데이터 분석기사", "데이터분석 전문가", "데이터분석 준전문가", "SQL 전문가", "SQL 개발자",
                  "데이터아키텍처 전문가", "데이터아키텍처 준전문가"]
DATAQ_NAMES = {"SQLD": "SQL 개발자", "SQLP": "SQL 전문가", "ADSP": "데이터분석 준전문가", "BIGDATA": "빅데이터 분석기사"}


def page_text(url: str) -> str:
    response = requests.get(url, headers=HEADERS, timeout=15)
    response.raise_for_status()
    response.encoding = response.apparent_encoding
    text = re.sub(r"<script.*?</script>|<style.*?</style>|<!--.*?-->", " ", response.text, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text))


def _md(year: int, value: str, month_hint: int | None = None) -> str | None:
    try:
        if "." in value:
            month, day = value.split(".")
            return date(year, int(month), int(day)).isoformat()
        return date(year, int(month_hint), int(value)).isoformat() if month_hint else None
    except (TypeError, ValueError):
        return None


def parse_dataq(text: str, section: str) -> list[dict]:
    year_match = re.search(r"(20\d{2})년도 일정", text) or re.search(r"(20\d{2})년", text)
    start = text.find("일정표")
    if not year_match or start < 0:
        return []
    year, body = int(year_match[1]), text[start:]
    begin = body.find(section)
    if begin < 0:
        return []
    ends = [body.find(name, begin + len(section)) for name in DATAQ_SECTIONS if name != section]
    ends = [e for e in ends if e > begin] + [body.find("원서접수 시간", begin)]
    chunk = body[begin:min(e for e in ends if e > begin)] if any(e > begin for e in ends) else body[begin:]
    pattern = re.compile(
        r"(?:제(\d+)회\s+)?(필기|실기|-)\s+(\d{1,2}\.\d{1,2})~(\d{1,2}(?:\.\d{1,2})?)\s+\d{1,2}\.\d{1,2}\s+"
        r"(\d{1,2}\.\d{1,2})\([월화수목금토일]\)\s+\S+\s+(\d{1,2}\.\d{1,2})")
    rows, round_no = [], ""
    for match in pattern.finditer(chunk):
        round_no = match[1] or round_no
        kind = "" if match[2] == "-" else f" {match[2]}"
        reg_start = _md(year, match[3])
        rows.append({
            "round": f"{year}년 제{round_no}회{kind}", "reg_start": reg_start,
            "reg_end": _md(year, match[4], int(match[3].split(".")[0])), "exam_date": _md(year, match[5]),
            "result_date": _md(year, match[6]), "source_url": DATAQ_URL,
        })
    return [r for r in rows if r["exam_date"]]


def parse_toeic(text: str) -> list[dict]:
    pattern = re.compile(
        r"제(\d+)회\s+(\d{4})\.(\d{2})\.(\d{2}) \(.\) [\d:]+\s+(\d{4})\.(\d{2})\.(\d{2}) \(.\) [\d:]+\s+"
        r"정기접수 : (\d{4})\.(\d{2})\.(\d{2}) \(.\) [\d:]+~(\d{4})\.(\d{2})\.(\d{2})")
    rows = []
    for m in pattern.finditer(text):
        rows.append({"round": f"제{m[1]}회", "exam_date": f"{m[2]}-{m[3]}-{m[4]}", "result_date": f"{m[5]}-{m[6]}-{m[7]}",
                     "reg_start": f"{m[8]}-{m[9]}-{m[10]}", "reg_end": f"{m[11]}-{m[12]}-{m[13]}", "source_url": TOEIC_URL})
    return rows


def parse_kacpta(text: str) -> list[dict]:
    """한국세무사회 연간 일정표(전산세무·전산회계). 장소공고(수험표·고사장 확인) 기간도 함께 읽는다."""
    start = text.find("전산세무 1,2급")
    if start < 0:
        return []
    year_match = re.search(r"(20\d{2})년", text[max(0, start - 400):start]) or re.search(r"(20\d{2})년", text)
    if not year_match:
        return []
    year = int(year_match[1])
    end = re.search(r"20\d{2}년", text[start:])
    chunk = text[start:start + end.start()] if end else text[start:start + 1500]
    md = r"(\d{1,2})\.\s?(\d{1,2})"
    pattern = re.compile(rf"제\s?(\d+)\s?회\s+{md}\s*[∼~]\s*{md}\s+{md}\s*[∼~]\s*{md}\s+{md}\([월화수목금토일]\)\s+{md}")
    rows = []
    for m in pattern.finditer(chunk):
        def day(i: int) -> str | None:
            return _md(year, f"{m[i]}.{m[i + 1]}")
        rows.append({"round": f"{year}년 제{m[1]}회", "reg_start": day(2), "reg_end": day(4), "venue_start": day(6),
                     "venue_end": day(8), "exam_date": day(10), "result_date": day(12), "source_url": KACPTA_URL})
    return [r for r in rows if r["exam_date"]]


def crawl_official(cert: dict) -> dict | None:
    """직접 읽을 수 있는 사이트면 {"rounds", "url", "title"}을, 대상이 아니면 None을 돌려준다.

    네트워크·구조 오류는 {"rounds": [], "error": ...}로 돌려 호출부가 '못 함'으로 표시하게 한다.
    """
    code = cert.get("code")
    if code in DATAQ_NAMES:
        url, title, parser = DATAQ_URL, "데이터자격시험 연간 일정표", lambda t: parse_dataq(t, DATAQ_NAMES[code])
    elif code in KACPTA_CODES:
        url, title, parser = KACPTA_URL, "한국세무사회 자격시험 연간 일정", parse_kacpta
    elif code == "TOEIC":
        url, title, parser = TOEIC_URL, "TOEIC 시험일정", parse_toeic
    else:
        return None
    try:
        rounds = parser(page_text(url))
    except Exception as error:
        return {"rounds": [], "url": url, "title": title, "error": type(error).__name__}
    return {"rounds": rounds, "url": url, "title": title, "error": None if rounds else "일정표 구조를 읽지 못함"}
