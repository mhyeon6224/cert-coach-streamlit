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
KACPTA_FEE_URL = "https://license.kacpta.or.kr/web/info/info_outline.aspx"
DATAQ_FEE_URL = "https://www.dataq.or.kr/www/accept/guide.do"
DATAQ_FEES = {"SQLD": r"SQL 개발자\(SQLD\)", "SQLP": r"SQL 전문가\(SQLP\)", "ADSP": r"데이터 분석 준전문가\(ADsP\)"}
SPEAKING_URL = "https://www.toeicswt.co.kr/receipt/examSchList.php"
OPIC_URL = "https://www.opic.or.kr/opics/servlet/controller.opic.site.receipt.AnnualScheduleServlet?p_process=select-list&p_tab=0"
TEPS_PAGE = "https://www.teps.or.kr/receiption/examschedule"
TEPS_LIST = "https://www.teps.or.kr/receiption/scheduleList1"
ALADIN_SEARCH = "https://www.aladin.co.kr/search/wsearchresult.aspx"
KACPTA_CODES = {"ACCOUNT_1", "TAX_2", "ADHOC_전산세무회계"}
KOFIA_PAGE = "https://license.kofia.or.kr/examInfo/examYearly.do"
KOFIA_API = "https://license.kofia.or.kr/examInfo/ajax/examYearlyMstInfo.do"
KOFIA_LICENSES = {"투자자산운용사": "FWM006", "금융투자분석사": "FWR005", "재무위험관리사": "FWD003"}
KBI_PAGE = "https://www.kbi.or.kr/platformWeb/Qual.do?cmd=openPage&pageName=qualTestScheduleList"
KBI_API = "https://www.kbi.or.kr/platformWeb/Qual.do?cmd=qualTestScheduleList"
KBI_NAMES = ["신용위험분석사", "신용분석사", "여신심사역", "국제금융역", "외환전문역", "자산관리사", "은행텔러"]
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


def parse_speaking(text: str) -> list[dict]:
    """TOEIC Speaking 시험일정: 시험일 · 성적발표일 · 접수기간."""
    start = text.find("시험일정 리스트 테이블")
    day = r"(\d{4})\.(\d{2})\.(\d{2})"
    pattern = re.compile(rf"{day} \(.\)\s+{day} \(.\) [\d:]+\s+{day} \(.\) [\d:]+~{day}")
    rows = []
    for m in pattern.finditer(text[max(start, 0):]):
        rows.append({"round": f"{m[1]}-{m[2]}-{m[3]} 시험", "exam_date": f"{m[1]}-{m[2]}-{m[3]}", "result_date": f"{m[4]}-{m[5]}-{m[6]}",
                     "reg_start": f"{m[7]}-{m[8]}-{m[9]}", "reg_end": f"{m[10]}-{m[11]}-{m[12]}", "source_url": SPEAKING_URL})
    return rows


def parse_opic(text: str) -> list[dict]:
    """OPIc 연간 정기시험 일정: 시험일 · 접수기간 · 성적발표일."""
    day = r"(\d{4})\.(\d{2})\.(\d{2})\(.\)"
    pattern = re.compile(rf"정기\s+OPIc\s+{day}\s+{day}\s*~\s*{day}\s+{day}")
    rows, seen = [], set()
    for m in pattern.finditer(text):
        exam = f"{m[1]}-{m[2]}-{m[3]}"
        if exam in seen:
            continue
        seen.add(exam)
        rows.append({"round": f"{exam} 정기시험", "exam_date": exam, "reg_start": f"{m[4]}-{m[5]}-{m[6]}",
                     "reg_end": f"{m[7]}-{m[8]}-{m[9]}", "result_date": f"{m[10]}-{m[11]}-{m[12]}", "source_url": OPIC_URL})
    return rows


def fetch_teps(years: list[int]) -> dict:
    """TEPS 연간 일정. 일정 페이지에서 연도별 회차 범위를 읽고, 그 범위의 일정표를 받는다."""
    page = requests.get(TEPS_PAGE, headers=HEADERS, timeout=15)
    page.raise_for_status()
    rows = []
    for year, first, last in re.findall(r'<option value="(\d{4})" data-from="(\d+)" data-to="(\d+)"', page.text):
        if int(year) not in years:
            continue
        response = requests.get(TEPS_LIST, params={"seqfrom": first, "seqto": last}, headers=HEADERS, timeout=15)
        response.raise_for_status()
        response.encoding = response.apparent_encoding
        text = re.sub(r"\s+", " ", re.sub(r"<style.*?</style>|<[^>]+>", " ", response.text, flags=re.S))
        for chunk in re.split(r"\s(?=\d{3}\s+\d{2}\.\d{2}\.\d{2}\()", text)[1:]:
            number = chunk.split()[0]
            days = [f"20{y}-{m}-{dd}" for y, m, dd in re.findall(r"(\d{2})\.(\d{2})\.(\d{2})\(", chunk)]
            if len(days) >= 4:
                rows.append({"round": f"제{number}회", "exam_date": days[0], "reg_start": days[1], "reg_end": days[2],
                             "result_date": days[-1], "source_url": TEPS_PAGE})
    return {"rounds": rows}


def official_fee(cert: dict) -> str | None:
    """공식 안내 페이지에 적힌 응시료. 읽지 못하면 None(지어내지 않는다)."""
    code = cert.get("code")
    try:
        if code in DATAQ_FEES:
            m = re.search(DATAQ_FEES[code] + r"\s*([\d,]+원)", page_text(DATAQ_FEE_URL))
            return m[1] if m else None
        if code == "BIGDATA":
            text = page_text(DATAQ_FEE_URL)
            a = re.search(r"빅데이터분석기사 - 필기\s*([\d,]+원)", text)
            b = re.search(r"빅데이터분석기사 - 실기\s*([\d,]+원)", text)
            return f"필기 {a[1]} / 실기 {b[1]}" if a and b else None
        if code in KACPTA_CODES:
            m = re.search(r"접수수수료\s*([\d,]+원)", page_text(KACPTA_FEE_URL))
            return m[1] if m else None
    except Exception:
        return None
    return None


def book_price(title: str) -> dict | None:
    """알라딘 검색 결과에서 같은 이름의 책 정가를 읽는다. 책 이름이 맞지 않으면 None."""
    clean = re.sub(r"[\(\[].*?[\)\]]", " ", title or "")
    words = [w for w in re.split(r"[\s/·,]+", clean) if len(w) >= 2][:5]
    if len(words) < 2:
        return None
    try:
        response = requests.get(ALADIN_SEARCH, params={"SearchTarget": "Book", "SearchWord": " ".join(words)}, headers=HEADERS, timeout=15)
        response.raise_for_status()
        raw = response.text
    except Exception:
        return None
    for m in re.finditer(r'<a href="(https://www\.aladin\.co\.kr/shop/wproduct\.aspx\?ItemId=\d+)" class="bo3"[^>]*>(.*?)</a>', raw, flags=re.S):
        name = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m[2])).strip()
        tail = raw[m.end():m.end() + 3000]
        price = re.search(r'<span class="">([\d,]+)</span>원', tail)
        flat = re.sub(r"\s", "", name)
        if not price or "세트" in name or "절판" in re.sub(r"<[^>]+>", "", tail[:2500]):
            continue
        if sum(1 for w in words if re.sub(r"\s", "", w) in flat) >= max(2, len(words) - 1):
            return {"title": name[:80], "price": f"{price[1]}원", "url": m[1]}
    return None


def book_search_url(title: str) -> str:
    from urllib.parse import urlencode
    clean = re.sub(r"\s+", " ", re.sub(r"[\(\[].*?[\)\]]", " ", title or "")).strip()
    return ALADIN_SEARCH + "?" + urlencode({"SearchTarget": "Book", "SearchWord": clean})


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


def _ymd(value: str) -> str | None:
    digits = re.sub(r"\D", "", value or "")[:8]
    try:
        return date(int(digits[:4]), int(digits[4:6]), int(digits[6:8])).isoformat() if len(digits) == 8 else None
    except ValueError:
        return None


def fetch_kofia(license_code: str) -> dict:
    """금융투자협회 자격시험센터 연간 일정(사이트가 화면에 쓰는 일정 데이터를 그대로 받는다)."""
    response = requests.post(KOFIA_API, data={"rcptSttType": "ALL", "licenseCd": license_code}, timeout=15,
                             headers={**HEADERS, "X-Requested-With": "XMLHttpRequest", "Referer": KOFIA_PAGE})
    response.raise_for_status()
    rows = []
    for item in response.json().get("examSchedList") or []:
        exam = _ymd(str(item.get("examinationDt") or ""))
        if not exam:
            continue
        rows.append({"round": f"{exam[:4]}년 제{item.get('timeCnt')}회", "reg_start": _ymd(str(item.get("receiptSrtDtTm") or "")),
                     "reg_end": _ymd(str(item.get("receiptEndDtTm") or "")), "exam_date": exam,
                     "result_date": _ymd(str(item.get("successAnnDt") or "")), "source_url": KOFIA_PAGE})
    return {"rounds": rows}


def fetch_kbi(name: str, years: list[int]) -> dict:
    """한국금융연수원 자격시험 일정(응시료 포함). 올해와 내년 일정을 함께 본다."""
    rows, fee = [], None
    for year in years:
        response = requests.post(KBI_API, timeout=15, headers={**HEADERS, "X-Requested-With": "XMLHttpRequest", "Referer": KBI_PAGE},
                                 data={"l_pageno": 1, "l_listscale": 100, "p_sortorder": "QUAL_TYPE, D_YY, I_QLFN, Q_NUM",
                                       "p_dYy": str(year), "p_qualType": "", "p_nQlfn": ""})
        response.raise_for_status()
        for item in response.json().get("ds") or []:
            if re.sub(r"\s", "", str(item.get("N_QLFN") or "")).split("(")[0] != name:
                continue
            def md(text: str) -> str | None:
                m = re.search(r"(\d{1,2})\.(\d{1,2})", text or "")
                return _md(year, f"{m[1]}.{m[2]}") if m else None
            period = str(item.get("D_INT_ACPT_DT") or "").split("~")
            exam = md(str(item.get("D_OF_APPR") or ""))
            if not exam:
                continue
            rows.append({"round": f"{year}년 제{item.get('Q_SEQ')}회", "reg_start": md(period[0]),
                         "reg_end": md(period[1]) if len(period) > 1 else None, "exam_date": exam,
                         "result_date": md(str(item.get("D_SUCC_ANNO") or "")), "source_url": KBI_PAGE})
            if item.get("SUM_W_APP_EXAM"):
                fee = f"{item['SUM_W_APP_EXAM']}원"
    return {"rounds": rows, "fee": fee}


def crawl_official(cert: dict) -> dict | None:
    """직접 읽을 수 있는 사이트면 {"rounds", "url", "title"}을, 대상이 아니면 None을 돌려준다.

    네트워크·구조 오류는 {"rounds": [], "error": ...}로 돌려 호출부가 '못 함'으로 표시하게 한다.
    """
    code, name = cert.get("code"), re.sub(r"\s", "", cert.get("name") or "")
    fetcher = None
    kbi_name = next((n for n in KBI_NAMES if n in name), None)
    if code == "TEPS":
        year = date.today().year
        url, title, fetcher = TEPS_PAGE, "TEPS 연간 시험일정", lambda: fetch_teps([year, year + 1])
    elif name in KOFIA_LICENSES:
        url, title, fetcher = KOFIA_PAGE, "금융투자협회 자격시험 연간 일정", lambda: fetch_kofia(KOFIA_LICENSES[name])
    elif kbi_name:
        year = date.today().year
        url, title, fetcher = KBI_PAGE, "한국금융연수원 자격시험 일정", lambda: fetch_kbi(kbi_name, [year, year + 1])
    if fetcher:
        try:
            got = fetcher()
        except Exception as error:
            return {"rounds": [], "url": url, "title": title, "error": type(error).__name__}
        return {"rounds": got["rounds"], "url": url, "title": title, "fee": got.get("fee"),
                "error": None if got["rounds"] else "일정 데이터를 읽지 못함"}
    if code in DATAQ_NAMES:
        url, title, parser = DATAQ_URL, "데이터자격시험 연간 일정표", lambda t: parse_dataq(t, DATAQ_NAMES[code])
    elif code in KACPTA_CODES:
        url, title, parser = KACPTA_URL, "한국세무사회 자격시험 연간 일정", parse_kacpta
    elif code == "TOEIC_SPEAKING":
        url, title, parser = SPEAKING_URL, "TOEIC Speaking 시험일정", parse_speaking
    elif code == "OPIC":
        url, title, parser = OPIC_URL, "OPIc 연간 시험일정", parse_opic
    elif code == "TOEIC":
        url, title, parser = TOEIC_URL, "TOEIC 시험일정", parse_toeic
    else:
        return None
    try:
        rounds = parser(page_text(url))
    except Exception as error:
        return {"rounds": [], "url": url, "title": title, "error": type(error).__name__}
    return {"rounds": rounds, "url": url, "title": title, "fee": official_fee(cert) if rounds else None,
            "error": None if rounds else "일정표 구조를 읽지 못함"}
