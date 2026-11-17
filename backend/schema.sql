-- ApplyLaunch database (PostgreSQL; designed for Supabase: auth + Postgres + row-level security).
-- Only structured facts are stored. No HTML pages or PDFs are archived.
-- STATUS: designed, NOT deployed or tested here.

create extension if not exists pg_trgm;

-- ---------- public catalogue (written only by the workers with the service key) ----------
create table sources (
  id text primary key, name text not null, type text, country text, cc char(2), url text not null,
  status text not null check (status in ('verified','unverified','js_required','blocked_robots','unreachable','no_listing')),
  quality smallint default 0, listing jsonb default '[]', adapter jsonb, via text,
  discovered date, vetted date, consecutive_fails smallint default 0
);
create table positions (
  id bigint primary key, source_id text references sources(id) on delete set null,
  title text not null, inst text, city text, cc char(2) not null, type text not null,
  funding text, deadline date, salary int, currency char(3), duration text, fee text, ielts numeric(2,1),
  url text not null unique, hub text, supervisors text[], topics text,
  first_seen date not null, last_seen date not null,
  tsv tsvector generated always as (to_tsvector('simple', coalesce(title,'')||' '||coalesce(inst,'')||' '||coalesce(city,'')||' '||coalesce(topics,''))) stored
);
create index on positions using gin (tsv);
create index on positions (cc, type, deadline);
create table professors (
  id bigint primary key, openalex text unique, orcid text, name text not null, uni text not null, cc char(2) not null,
  dept text, rank text, topics text[], keywords text[],
  email text, email_source_url text,                 -- only e-mails printed on an official page / public ORCID record
  page text, group_url text, linkedin_url text,      -- LinkedIn: link only, never scraped
  status smallint not null default 3 check (status between 1 and 4),
  contact_method text check (contact_method in ('email','portal')),
  accepts text, evidence_text text, evidence_url text, evidence_date date, checked date not null
);
create index on professors (cc, status);
create index on professors using gin (name gin_trgm_ops);
create table crawl_runs (id bigserial primary key, kind text, started timestamptz default now(), stats jsonb);

-- ---------- user data (row-level security: each user sees only their own rows) ----------
create table profiles (
  user_id uuid primary key references auth.users on delete cascade,
  display_name text, lang text default 'en', profile jsonb not null default '{}', created_at timestamptz default now()
);
create table saved_positions (user_id uuid references auth.users on delete cascade, position_id bigint references positions(id) on delete cascade, created_at timestamptz default now(), primary key (user_id, position_id));
create table saved_professors (user_id uuid references auth.users on delete cascade, professor_id bigint references professors(id) on delete cascade, created_at timestamptz default now(), primary key (user_id, professor_id));
create table notification_prefs (
  user_id uuid primary key references auth.users on delete cascade,
  email_enabled boolean default false, frequency text default 'weekly' check (frequency in ('daily','weekly')),
  filters jsonb default '{}', last_sent timestamptz
);
alter table profiles enable row level security;            create policy own on profiles for all using (user_id = auth.uid()) with check (user_id = auth.uid());
alter table saved_positions enable row level security;     create policy own on saved_positions for all using (user_id = auth.uid()) with check (user_id = auth.uid());
alter table saved_professors enable row level security;    create policy own on saved_professors for all using (user_id = auth.uid()) with check (user_id = auth.uid());
alter table notification_prefs enable row level security;  create policy own on notification_prefs for all using (user_id = auth.uid()) with check (user_id = auth.uid());
alter table positions enable row level security;           create policy read_all on positions for select using (true);
alter table professors enable row level security;          create policy read_all on professors for select using (true);
alter table sources enable row level security;             -- no public policy: sources stay private

-- ---------- hybrid search entry point ----------
create or replace function search_positions(q text, p_cc char(2) default null, p_type text default null, lim int default 50)
returns setof positions language sql stable as $$
  select * from positions
  where (deadline is null or deadline >= current_date)
    and (q is null or q = '' or tsv @@ websearch_to_tsquery('simple', q))
    and (p_cc is null or cc = p_cc) and (p_type is null or type = p_type)
  order by deadline nulls last limit lim $$;
