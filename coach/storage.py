"""사용자 계정과 학습 상태 저장소.

- SUPABASE_URL / SUPABASE_KEY 가 설정되면 Supabase(Postgres) 테이블 `coach_users`에 저장한다. → 재배포·절전 후에도 유지
- 없으면 앱 서버의 SQLite 파일에 저장한다. → 로컬에서는 유지되지만, Streamlit Cloud에서는 앱이 재시작되면 사라진다
비밀번호는 원문을 저장하지 않고 솔트를 붙인 PBKDF2 해시만 저장한다.

Supabase 테이블 (SQL Editor에서 한 번 실행):
    create table coach_users (
      nickname text primary key, salt text not null, pw_hash text not null,
      state jsonb not null default '{}', updated_at timestamptz default now());
    alter table coach_users enable row level security;
앱은 service_role 키로 접근하므로(서버에서만 사용) 별도 정책 없이 동작한다.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import sqlite3
from pathlib import Path

import requests

from .services import secret

NICK = re.compile(r"^[0-9A-Za-z가-힣_]{2,20}$")
LOCAL_DB = Path(__file__).resolve().parent.parent / ".localdb" / "users.db"


class StoreError(RuntimeError):
    """저장소 접근 실패."""


class SqliteStore:
    label = "앱 서버 임시 저장(SQLite) — 클라우드에서는 앱이 재시작되면 지워질 수 있어요"
    durable = False

    def __init__(self, path: Path = LOCAL_DB):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = str(path)
        with self._conn() as conn:
            conn.execute("create table if not exists coach_users (nickname text primary key, salt text, pw_hash text, "
                         "state text, updated_at text default current_timestamp)")

    def _conn(self):
        return sqlite3.connect(self.path, timeout=10)

    def get(self, nickname: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("select salt, pw_hash, state from coach_users where nickname = ?", (nickname,)).fetchone()
        return {"salt": row[0], "pw_hash": row[1], "state": json.loads(row[2] or "{}")} if row else None

    def put(self, nickname: str, salt: str, pw_hash: str, state: dict) -> None:
        with self._conn() as conn:
            conn.execute(
                "insert into coach_users (nickname, salt, pw_hash, state) values (?, ?, ?, ?) "
                "on conflict(nickname) do update set salt = excluded.salt, pw_hash = excluded.pw_hash, "
                "state = excluded.state, updated_at = current_timestamp",
                (nickname, salt, pw_hash, json.dumps(state, ensure_ascii=False)))


class SupabaseStore:
    label = "클라우드 DB(Supabase) — 다시 접속해도 유지돼요"
    durable = True

    def __init__(self, url: str, key: str):
        self.base = url.rstrip("/") + "/rest/v1/coach_users"
        self.headers = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    def get(self, nickname: str) -> dict | None:
        try:
            response = requests.get(self.base, headers=self.headers, timeout=15,
                                    params={"nickname": f"eq.{nickname}", "select": "salt,pw_hash,state"})
            response.raise_for_status()
            rows = response.json()
        except Exception as error:
            raise StoreError(f"DB 조회 실패 ({type(error).__name__})") from None
        return rows[0] if rows else None

    def put(self, nickname: str, salt: str, pw_hash: str, state: dict) -> None:
        try:
            response = requests.post(
                self.base, headers={**self.headers, "Prefer": "resolution=merge-duplicates"}, timeout=15,
                json={"nickname": nickname, "salt": salt, "pw_hash": pw_hash, "state": state})
            response.raise_for_status()
        except Exception as error:
            raise StoreError(f"DB 저장 실패 ({type(error).__name__})") from None


def build_store():
    url, key = secret("SUPABASE_URL"), secret("SUPABASE_KEY")
    return SupabaseStore(url, key) if url and key else SqliteStore()


def _hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000).hex()


def validate(nickname: str, password: str) -> str | None:
    if not NICK.match(nickname or ""):
        return "닉네임은 한글·영문·숫자 2~20자로 정해 주세요."
    if len(password or "") < 4:
        return "비밀번호는 4자 이상으로 정해 주세요."
    return None


def signup(store, nickname: str, password: str, state: dict) -> str | None:
    """성공하면 None, 실패하면 사용자에게 보여 줄 메시지."""
    problem = validate(nickname, password)
    if problem:
        return problem
    if store.get(nickname):
        return "이미 있는 닉네임이에요. 로그인하거나 다른 닉네임을 써 주세요."
    salt = os.urandom(16).hex()
    store.put(nickname, salt, _hash(password, salt), state)
    return None


def login(store, nickname: str, password: str) -> tuple[dict | None, dict | None]:
    """(저장된 상태, 인증 정보) 또는 (None, None)."""
    record = store.get(nickname) if NICK.match(nickname or "") else None
    if not record or not hmac.compare_digest(_hash(password, record["salt"]), record["pw_hash"]):
        return None, None
    state = record["state"] if isinstance(record["state"], dict) else json.loads(record["state"] or "{}")
    return state, {"nickname": nickname, "salt": record["salt"], "pw_hash": record["pw_hash"]}


def save(store, auth: dict, state: dict) -> None:
    store.put(auth["nickname"], auth["salt"], auth["pw_hash"], state)


# 연동 정보(예: Google Calendar 토큰)는 학습 상태와 따로 보관한다.
# 학습 상태는 자동 저장으로 통째로 덮어쓰기 때문에, 다른 탭에서 받은 토큰이 지워지지 않게 하려는 것.
# 키 이름에 '::'를 넣어, 사용자가 만들 수 있는 닉네임(한글·영문·숫자·_)과 절대 겹치지 않게 한다.
def get_meta(store, kind: str, nickname: str) -> dict:
    record = store.get(f"{kind}::{nickname}")
    if not record:
        return {}
    value = record["state"]
    return value if isinstance(value, dict) else json.loads(value or "{}")


def put_meta(store, kind: str, nickname: str, value: dict) -> None:
    store.put(f"{kind}::{nickname}", "-", "-", value)
