"""자격증 카탈로그와 참고자료(공공데이터 CSV) 로더.

- CATALOG: 추천 후보로 쓰는 대표 자격증. 일정·응시료 같은 변하는 값은 넣지 않는다(공식 원문으로만 확인).
- 참고자료 CSV: 공식 원문을 읽지 못했을 때만 쓰는 보조 자료. 화면에는 항상 "자료집 기준"으로 표시한다.
"""
from __future__ import annotations

import csv
import json
import re
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
REFERENCE_DATE = {"national": "2025-12-31", "private": "2026-08-26"}


def _c(code, name, issuer, url, tags, level, desc, aliases=(), restricted=False, nxt=()):
    domain = re.sub(r"^www\.", "", url.split("/")[2])
    return {
        "code": code, "name": name, "issuer": issuer, "official_url": url, "domain": domain,
        "tags": list(tags), "level": level, "desc": desc, "aliases": [name, *aliases],
        "restricted": restricted, "next": list(nxt),
    }


CATALOG = [
    _c("INFO_ENGINEER", "정보처리기사", "한국산업인력공단", "https://www.q-net.or.kr/", ["개발", "인프라", "데이터"], "상위",
       "소프트웨어 설계·개발·데이터베이스 역량을 종합 검증하는 국가기술자격", ["정처기"], True),
    _c("INFO_CRAFTSMAN", "정보처리기능사", "한국산업인력공단", "https://www.q-net.or.kr/", ["개발", "사무"], "입문",
       "프로그래밍·데이터베이스 기초를 검증하는 국가기술자격(응시자격 제한 없음)", [], False, ["INFO_ENGINEER"]),
    _c("SQLD", "SQLD", "한국데이터산업진흥원", "https://www.dataq.or.kr/", ["데이터", "개발"], "입문",
       "데이터 모델링과 SQL 기본·활용 역량을 검증하는 국가공인 자격", ["SQL 개발자", "sql개발자"], False, ["SQLP", "BIGDATA"]),
    _c("SQLP", "SQLP", "한국데이터산업진흥원", "https://www.dataq.or.kr/", ["데이터", "개발"], "상위",
       "SQL 튜닝까지 포함한 전문가 수준의 SQL 역량을 검증하는 국가공인 자격", ["SQL 전문가"], True),
    _c("ADSP", "ADsP", "한국데이터산업진흥원", "https://www.dataq.or.kr/", ["데이터", "마케팅", "기획"], "입문",
       "데이터 이해·분석 기획·분석 기초 역량을 검증하는 국가공인 자격", ["데이터분석 준전문가", "데이터분석준전문가"], False, ["BIGDATA"]),
    _c("BIGDATA", "빅데이터분석기사", "한국데이터산업진흥원", "https://www.dataq.or.kr/", ["데이터"], "상위",
       "빅데이터 분석 기획부터 수집·처리·분석·시각화까지 검증하는 국가기술자격", ["빅분기"], True),
    _c("SOCIAL_RESEARCH_2", "사회조사분석사 2급", "한국산업인력공단", "https://www.q-net.or.kr/", ["데이터", "마케팅", "기획"], "중급",
       "조사 설계·자료 수집·통계 분석 역량을 검증하는 국가기술자격", ["사회조사분석사", "사조사"]),
    _c("COMPUTER_1", "컴퓨터활용능력 1급", "대한상공회의소", "https://license.korcham.net/", ["사무", "공통"], "중급",
       "스프레드시트·데이터베이스 활용 능력을 검증하는 국가기술자격", ["컴활 1급", "컴활1급", "컴활", "컴퓨터활용능력"]),
    _c("ACCOUNT_1", "전산회계 1급", "한국세무사회", "https://license.kacpta.or.kr/", ["회계", "사무"], "입문",
       "회계 원리와 전산 회계 프로그램 실무를 검증하는 국가공인 자격", ["전산회계1급", "전산회계"], False, ["TAX_2"]),
    _c("TAX_2", "전산세무 2급", "한국세무사회", "https://license.kacpta.or.kr/", ["회계", "세무"], "중급",
       "재무회계·원가회계·부가가치세·소득세 실무를 검증하는 국가공인 자격", ["전산세무2급", "전산세무"], False, ["FINANCE_MANAGER"]),
    _c("FINANCE_MANAGER", "재경관리사", "삼일회계법인", "https://www.samilexam.com/", ["회계", "세무", "금융"], "상위",
       "재무회계·세무회계·원가관리회계 관리자 수준 역량을 검증하는 국가공인 자격"),
    _c("ERP_ACCOUNT", "ERP정보관리사 회계 2급", "한국생산성본부", "https://license.kpc.or.kr/", ["회계", "사무", "물류"], "입문",
       "ERP 시스템의 회계 모듈 운용 역량을 검증하는 국가공인 자격", ["ERP정보관리사", "ERP 정보관리사", "ERP"]),
    _c("INFOSEC", "정보보안기사", "한국방송통신전파진흥원", "https://www.cq.or.kr/", ["보안", "인프라"], "상위",
       "시스템·네트워크·애플리케이션 보안과 보안 관리 역량을 검증하는 국가기술자격", ["정보보안 기사"], True),
    _c("LINUX_2", "리눅스마스터 2급", "한국정보통신진흥협회", "https://www.ihd.or.kr/", ["인프라", "개발", "보안"], "입문",
       "리눅스 운영·관리 기초 역량을 검증하는 국가공인 자격", ["리눅스마스터", "리눅스 마스터"], False, ["INFOSEC", "AWS_SAA"]),
    _c("NETWORK_2", "네트워크관리사 2급", "한국정보통신자격협회", "https://www.icqa.or.kr/", ["인프라", "보안"], "입문",
       "네트워크 일반·TCP/IP·운용 기초 역량을 검증하는 국가공인 자격", ["네트워크관리사"], False, ["INFOSEC"]),
    _c("AWS_CLF", "AWS Certified Cloud Practitioner", "Amazon Web Services", "https://aws.amazon.com/ko/certification/", ["인프라", "개발"], "입문",
       "AWS 클라우드 기본 개념과 서비스 이해를 검증하는 국제 자격", ["AWS CLF", "클라우드 프랙티셔너", "AWS 프랙티셔너"], False, ["AWS_SAA"]),
    _c("AWS_SAA", "AWS Certified Solutions Architect - Associate", "Amazon Web Services", "https://aws.amazon.com/ko/certification/", ["인프라", "개발"], "중급",
       "AWS 기반 아키텍처 설계 역량을 검증하는 국제 자격", ["AWS SAA", "SAA", "솔루션스 아키텍트"]),
    _c("SEARCH_AD_1", "검색광고마케터 1급", "한국정보통신진흥협회", "https://www.ihd.or.kr/", ["마케팅"], "입문",
       "검색광고 기획·운용·성과 분석 역량을 검증하는 국가공인 자격", ["검색광고마케터"], False, ["ADSP"]),
    # 기획: 기획 직무에 '필수'로 통하는 자격증은 드물다. 아래는 기획 역량과 맞닿은, 실제로 시행 중인 자격증이다.
    _c("MK_TEST", "매경TEST", "매일경제신문사", "https://exam.mk.co.kr/", ["기획", "금융", "사무"], "입문",
       "경제·경영 두 영역의 이해력과 전략적 사고를 점수로 측정하는 시험(일정 점수 이상은 국가공인 민간자격)", ["매경테스트", "매경 TEST"]),
    _c("TESAT", "TESAT", "한국경제신문사", "https://www.tesat.or.kr/", ["기획", "금융", "사무"], "입문",
       "경제 이론·시사 경제·상황 판단 능력을 측정하는 경제이해력검증시험(일정 등급 이상은 국가공인 민간자격)",
       ["테샛", "경제이해력검증시험"]),
    _c("CAPM", "CAPM", "PMI", "https://www.pmi.org/", ["기획", "개발"], "입문",
       "프로젝트 범위·일정·위험 관리의 기초를 검증하는 국제 자격. 실무 경력 없이 응시할 수 있지만 사전 교육 이수가 필요",
       ["Certified Associate in Project Management"], True, ["PMP"]),  # 사전 교육 이수 조건이 있어 '제한 있음'으로 표시
    _c("PMP", "PMP", "PMI", "https://www.pmi.org/", ["기획", "개발"], "상위",
       "프로젝트 관리 전문가 국제 자격. 프로젝트 실무 경력이 있어야 응시 가능", ["Project Management Professional"], True),
    _c("SERVICE_UX", "서비스·경험디자인기사", "한국디자인진흥원", "https://www.kidp.or.kr/", ["기획", "마케팅"], "상위",
       "사용자 조사부터 서비스·경험 기획 설계, 개발·운영까지 검증하는 국가기술자격",
       ["서비스경험디자인기사", "서비스 경험 디자인 기사", "서경디"], True),
    _c("BIZ_CONSULTANT", "경영지도사", "한국산업인력공단", "https://www.q-net.or.kr/", ["기획", "마케팅", "회계"], "상위",
       "기업 경영 문제를 진단하고 전략을 세우는 국가전문자격. 2차는 인사·재무·생산·마케팅 중 한 분야를 골라 응시",
       ["경영지도사(마케팅)", "경영지도사 마케팅"]),
    _c("CONVENTION_2", "컨벤션기획사 2급", "한국산업인력공단", "https://www.q-net.or.kr/", ["기획", "마케팅"], "중급",
       "국제회의·행사의 유치·기획·예산·운영 역량을 검증하는 국가기술자격", ["컨벤션기획사"], True),
    _c("DISTRIBUTION_2","유통관리사 2급", "대한상공회의소", "https://license.korcham.net/", ["유통", "마케팅", "물류"], "입문",
       "유통·물류·상권 분석·마케팅 관리 지식을 검증하는 국가자격", ["유통관리사"], False, ["LOGISTICS"]),
    _c("LOGISTICS", "물류관리사", "한국산업인력공단", "https://www.q-net.or.kr/", ["물류", "유통"], "중급",
       "물류 관리·화물 운송·보관 하역·국제 물류 지식을 검증하는 국가전문자격"),
    _c("INVEST_MANAGER", "투자자산운용사", "금융투자협회", "https://license.kofia.or.kr/", ["금융"], "중급",
       "집합투자재산·신탁재산 운용 업무에 필요한 지식을 검증하는 금융 자격"),
    _c("CREDIT_ANALYST", "신용분석사", "한국금융연수원", "https://www.kbi.or.kr/", ["금융", "회계"], "중급",
       "기업 회계·신용 분석 역량을 검증하는 국가공인 자격"),
    _c("SAFETY_ENGINEER", "산업안전기사", "한국산업인력공단", "https://www.q-net.or.kr/", ["안전"], "상위",
       "산업 현장의 안전 관리·재해 예방 역량을 검증하는 국가기술자격", [], True),
    _c("ELECTRIC_ENGINEER", "전기기사", "한국산업인력공단", "https://www.q-net.or.kr/", ["전기"], "상위",
       "전기 설비 설계·시공·운용 역량을 검증하는 국가기술자격", [], True),
    _c("JOB_COUNSELOR_2", "직업상담사 2급", "한국산업인력공단", "https://www.q-net.or.kr/", ["HR"], "중급",
       "직업 상담·직업 정보·노동시장 지식을 검증하는 국가기술자격", ["직업상담사"]),
    _c("KOREAN_HISTORY", "한국사능력검정시험", "국사편찬위원회", "https://www.historyexam.go.kr/", ["공공", "공통"], "입문",
       "한국사 이해도를 검증하는 시험. 공공 부문 채용에서 자주 활용", ["한능검", "한국사"]),
    _c("TOEIC_SPEAKING", "TOEIC Speaking", "한국TOEIC위원회", "https://www.toeicswt.co.kr/", ["어학", "공통"], "입문",
       "영어 말하기 능력을 평가하는 시험", aliases=("토익스피킹", "토익 스피킹", "토스", "TOEIC Speaking", "토익스피킹시험")),
    _c("OPIC", "OPIc", "ACTFL·멀티캠퍼스", "https://www.opic.or.kr/", ["어학", "공통"], "입문",
       "1:1 인터뷰 방식의 외국어 말하기 평가", aliases=("오픽", "OPIc", "opic")),
    _c("TEPS", "TEPS", "서울대학교 TEPS관리위원회", "https://www.teps.or.kr/", ["어학", "공통"], "입문",
       "서울대학교가 개발한 영어 능력 시험", aliases=("텝스", "TEPS")),
    _c("TOEFL", "TOEFL iBT", "ETS", "https://www.ets.org/toefl.html", ["어학"], "중급",
       "영어권 대학 진학 등에 쓰이는 학술 영어 시험", aliases=("토플", "TOEFL", "toefl ibt")),
    _c("TOEIC", "TOEIC", "한국TOEIC위원회", "https://exam.toeic.co.kr/", ["어학", "공통"], "입문",
       "비즈니스 영어 듣기·읽기 능력을 평가하는 어학 시험", ["토익"]),
]
BY_CODE = {c["code"]: c for c in CATALOG}

# 희망 직무 문장 → 직무 태그 (규칙 기반 추천과 LLM 실패 시 대체 추천에 사용)
JOB_TAGS = [
    (r"데이터|분석|통계|(?<![a-z])bi(?![a-z])|애널리", ["데이터"]),
    (r"개발|백엔드|프론트|소프트웨어|프로그래|엔지니어|(?<![a-z])sw(?![a-z])|(?<![a-z])it(?![a-z])", ["개발"]),
    (r"클라우드|인프라|devops|서버|네트워크|시스템", ["인프라"]),
    (r"보안|정보보호", ["보안"]),
    (r"회계|재무|경리|결산", ["회계"]),
    (r"세무|세금", ["세무"]),
    (r"마케팅|광고|브랜드|콘텐츠|퍼포먼스", ["마케팅"]),
    (r"기획|전략|(?<![a-z])pm(?![a-z])|서비스 ?기획", ["기획"]),
    (r"금융|은행|증권|투자|보험|자산", ["금융"]),
    (r"물류|(?<![a-z])scm(?![a-z])|구매|무역", ["물류"]),
    (r"유통|영업|(?<![a-z])md(?![a-z])|리테일", ["유통"]),
    (r"안전|(?<![a-z])ehs(?![a-z])", ["안전"]),
    (r"전기|전력|설비", ["전기"]),
    (r"사무|행정|총무|경영지원", ["사무"]),
    (r"공공|공기업|공무원", ["공공", "사무"]),
    (r"인사|(?<![a-z])hr(?![a-z])|채용|상담|노무", ["HR"]),
]


def norm(text: str) -> str:
    return re.sub(r"[\W_]+", "", (text or "").casefold())


def job_tags(text: str) -> list[str]:
    low = (text or "").casefold()
    tags: list[str] = []
    for pattern, values in JOB_TAGS:
        if re.search(pattern, low):
            tags += [v for v in values if v not in tags]
    return tags


@lru_cache(maxsize=1)
def _national_list() -> dict[str, dict]:
    rows = list(csv.reader((DATA_DIR / "national_list.csv").open(encoding="utf-8")))
    return {norm(r[3]): {"name": r[3].strip(), "kind": r[1], "series": r[2]} for r in rows[1:] if len(r) >= 4}


@lru_cache(maxsize=1)
def _national_info() -> dict[str, dict[str, str]]:
    info: dict[str, dict[str, str]] = {}
    for r in list(csv.reader((DATA_DIR / "national_exam_info.csv").open(encoding="utf-8")))[1:]:
        info.setdefault(norm(r[0]), {})[r[1]] = r[2]
    return info


@lru_cache(maxsize=1)
def _private() -> list[dict]:
    rows = list(csv.reader((DATA_DIR / "accredited_private.csv").open(encoding="utf-8")))
    return [
        {"ministry": r[0], "name": r[1], "grade": r[2], "manager": r[3], "valid_from": r[4], "valid_to": r[5]}
        for r in rows[1:] if len(r) >= 6
    ]


@lru_cache(maxsize=1)
def _guide() -> list[dict]:
    """공인민간자격 정보자료집(PDF)에서 뽑아 둔 자격증별 응시자격·응시료·유효기간·기관."""
    path = DATA_DIR / "private_guide.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("rows", [])


GUIDE_ALIASES = {"전산회계": "전산세무회계", "전산세무": "전산세무회계", "ERP정보관리사 회계": "ERP회계정보관리사",
                 "SQLD": "SQL", "SQLP": "SQL"}


def private_guide(name: str) -> dict | None:
    """자료집(PDF)에서 이름이 맞는 종목. 화면에는 항상 '자료집 기준'으로 표시한다."""
    base = re.sub(r"\s*\d급$", "", name or "").strip()
    key = norm(GUIDE_ALIASES.get(base, base))
    if len(key) < 3:
        return None
    best = None
    for row in _guide():
        rkey = norm(re.sub(r"\(.*?\)", "", row["name"]))
        if rkey and (rkey == key or (len(rkey) >= 3 and (rkey in key or key in rkey))):
            if best is None or abs(len(rkey) - len(key)) < abs(len(norm(best["name"])) - len(key)):
                best = row
    return best


def reference_info(name: str) -> dict[str, str]:
    """국가기술자격 종목별 시험정보(자료집). 없으면 빈 dict."""
    key = norm(re.sub(r"\s*\d급$", "", name or ""))
    return _national_info().get(norm(name)) or _national_info().get(key) or {}


def private_accreditation(name: str) -> list[dict]:
    """공인민간자격 등록현황(자료집)에서 이름이 겹치는 종목."""
    key = norm(re.sub(r"\s*\d급$", "", name or ""))
    if len(key) < 2:
        return []
    return [row for row in _private() if key in norm(row["name"]) or norm(row["name"]) in key]


def find_cert(text: str) -> dict | None:
    """문장에서 자격증을 찾는다. 카탈로그 → 국가자격 종목 목록(자료집) 순서."""
    key = norm(text)
    if not key:
        return None
    best: tuple[int, dict] | None = None
    for cert in CATALOG:
        for alias in cert["aliases"]:
            a = norm(alias)
            if a and a in key and (best is None or len(a) > best[0]):
                best = (len(a), cert)
    if best:
        return best[1]
    hit: tuple[int, dict] | None = None
    for nkey, row in _national_list().items():
        if len(nkey) >= 3 and nkey in key and (hit is None or len(nkey) > hit[0]):
            hit = (len(nkey), row)
    if hit:
        return adhoc_cert(hit[1]["name"])
    for row in _guide():  # 공인민간자격 정보자료집에 있는 종목
        gkey = norm(re.sub(r"\(.*?\)", "", row["name"]))
        if len(gkey) >= 3 and gkey in key and (hit is None or len(gkey) > hit[0]):
            hit = (len(gkey), row)
    if hit:
        return adhoc_cert(hit[1]["name"])
    return None


def adhoc_cert(name: str) -> dict:
    """카탈로그 밖 자격증의 경량 확인: 자료집에 있으면 주관기관만 채우고 나머지는 미확인으로 둔다."""
    info = reference_info(name)
    listed = _national_list().get(norm(name))
    issuer = (info.get("실시기관명") or "").strip() or ("한국산업인력공단" if listed else "미확인")
    url = (info.get("실시기관 홈페이지") or "").strip()
    if url and not url.startswith("http"):
        url = "https://" + url
    guide = None if (info or listed) else private_guide(name)
    if guide:
        issuer, url = guide["issuer"] or issuer, guide["homepage"]
        if url and not url.startswith("http"):
            url = "https://" + url
    if not url and listed:
        url = "https://www.q-net.or.kr/"
    url = url.replace("http://", "https://")
    domain = re.sub(r"^www\.", "", url.split("/")[2]) if url else ""
    return {
        "code": "ADHOC_" + norm(name).upper(), "name": name.strip(), "issuer": issuer, "official_url": url,
        "domain": domain, "tags": [], "level": "미확인",
        "desc": (info.get("개요") or "카탈로그 밖 자격증 — 세부 정보는 공식 사이트에서 확인이 필요해요.")[:160],
        "aliases": [name.strip()], "restricted": False, "next": [], "adhoc": True,
    }


def external_cert(name: str, issuer: str, url: str, desc: str = "") -> dict:
    """목록·자료집에 없는 자격증을 검색으로 확인했을 때 쓰는 임시 항목(경량 확인: 시행 여부·주관·공식 사이트만)."""
    parts = url.split("/")
    root = "/".join(parts[:3]) + "/" if len(parts) >= 3 else url
    return {
        "code": "EXT_" + norm(name).upper(), "name": name.strip(), "issuer": issuer.strip() or "미확인", "official_url": root,
        "domain": re.sub(r"^www\.", "", parts[2]) if len(parts) >= 3 else "", "tags": [], "level": "미확인",
        "desc": desc[:160] or "목록 밖 자격증 — 세부 정보는 공식 사이트에서 확인이 필요해요.",
        "aliases": [name.strip()], "restricted": False, "next": [], "adhoc": True,
    }


def cert_from_item(item: dict) -> dict | None:
    """추천 결과 한 줄에서 자격증 정보를 되찾는다(목록 → 추천 때 담아 둔 정보 → 이름 검색 순)."""
    return BY_CODE.get(item.get("code")) or item.get("cert") or find_cert(item.get("name") or "")


def is_owned(cert: dict, owned: list[str]) -> bool:
    owned_keys = [norm(o) for o in owned if o.strip()]
    return any(norm(a) in ok or ok in norm(a) for a in cert["aliases"] for ok in owned_keys if len(ok) >= 2)
