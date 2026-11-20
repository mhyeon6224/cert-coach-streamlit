-- Supabase 대시보드 > SQL Editor 에 붙여 넣고 Run 을 한 번 누르세요.
create table if not exists coach_users (
  nickname   text primary key,
  salt       text not null,
  pw_hash    text not null,
  state      jsonb not null default '{}',
  updated_at timestamptz default now()
);
-- 외부(브라우저)에서 직접 읽지 못하게 잠급니다. 앱은 서버 전용 키로만 접근합니다.
alter table coach_users enable row level security;
-- 서버 전용 키(service_role)가 Data API로 이 테이블을 쓸 수 있게 권한을 줍니다.
grant all on table coach_users to service_role;
