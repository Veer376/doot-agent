-- Project setup
-- ------------------------------------------------------------
-- Enable UUID generation (gen_random_uuid())
create extension if not exists pgcrypto;

-- Domain types / enums
-- ------------------------------------------------------------
-- ThreadStatus enum mirrors LangGraph ThreadStatus values.
-- Values: 'idle' | 'busy' | 'interrupted' | 'error'
do $$ begin
  create type thread_status as enum ('idle', 'busy', 'interrupted', 'error');
exception when duplicate_object then null; end $$;


-- Application users table (credits & subscription)
-- ------------------------------------------------------------
-- Source of truth for identity remains auth.users. This table stores
-- app-specific fields used by the UI and is auto-provisioned on signup.
create table if not exists public.users (
  id uuid primary key references auth.users(id) on delete cascade,
  email text,
  credits_available integer not null default 0,
  subscription_status text default 'inactive',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Keep users.updated_at fresh on UPDATE
create or replace function public._touch_users_updated_at() returns trigger as $$
begin
  new.updated_at = now();
  return new;
end; $$ language plpgsql;

drop trigger if exists trg_touch_users_updated_at on public.users;
create trigger trg_touch_users_updated_at
before update on public.users
for each row execute function public._touch_users_updated_at();

-- Auto-provision public.users on auth signup
create or replace function public.handle_new_user() returns trigger
language plpgsql
security definer
as $$
begin
  insert into public.users (id, email)
  values (new.id, new.email)
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
after insert on auth.users
for each row execute function public.handle_new_user();

-- RLS for users: self-select and self-update only
alter table public.users enable row level security;

do $$ begin
  create policy users_self_select on public.users
    for select using (id = auth.uid());
exception when duplicate_object then null; end $$;

do $$ begin
  create policy users_self_update on public.users
    for update using (id = auth.uid()) with check (id = auth.uid());
exception when duplicate_object then null; end $$;

-- Assistants (LangGraph Assistant shape)
-- ------------------------------------------------------------
-- JSONB: PostgreSQL's binary JSON. Great for flexible config/metadata.
-- We CHECK that config is always an object.
create table if not exists public.agents (
  agent_id uuid primary key default gen_random_uuid(),  -- required
  user_id uuid not null references auth.users(id) on delete cascade,

  graph_id text not null,                                   -- required
  config jsonb not null default '{}'::jsonb,                -- required (object)
  created_at timestamptz not null default now(),            -- required
  updated_at timestamptz not null default now(),            -- required
  metadata jsonb not null default '{}'::jsonb,              -- required

  context jsonb,                                            -- optional
  description text,                                         -- optional
  name text,                                                -- optional
  version int
);

create index if not exists idx_user on public.agents(user_id);
create index if not exists idx_agents_graph on public.agents(graph_id);
create index if not exists idx_agents_updated_at on public.agents(updated_at desc);

-- Keep agents.updated_at current
create or replace function public._touch_agent_updated_at() returns trigger as $$
begin
  new.updated_at = now();
  return new;
end; $$ language plpgsql;

drop trigger if exists trg_touch_agent_updated_at on public.agents;
create trigger trg_touch_agent_updated_at
before update on public.agents
for each row execute function public._touch_agent_updated_at();

-- RLS: only owner can read/write agents
alter table public.agents enable row level security;

do $$ begin
  create policy agents_owner_all on public.agents
    for all using (user_id = auth.uid())
    with check (user_id = auth.uid());
exception when duplicate_object then null; end $$;

-- Threads (LangGraph Thread shape)
-- ------------------------------------------------------------
-- metadata: required JSON object storing thread meta
-- config: optional JSON object for per-thread overrides
-- values: optional JSON object or array for graph state
-- interrupts: optional JSON object for raised interrupts
create table if not exists public.threads (
  thread_id uuid primary key default gen_random_uuid(),      -- required
  user_id uuid not null references auth.users(id) on delete cascade,

  created_at timestamptz not null default now(),             -- required
  updated_at timestamptz not null default now(),             -- required
  metadata jsonb not null default '{}'::jsonb,               -- required
  status thread_status not null default 'idle',              -- required

  config jsonb,                                              -- optional
  interrupts jsonb,                                          -- optional
  values jsonb,                                              -- optional

  -- optional convenience pointer (not part of SDK response)
  agent_id uuid references public.agents(agent_id) on delete set null,

  -- Validate JSON shapes only when present
  constraint chk_threads_interrupts_is_object
    check (interrupts is null or jsonb_typeof(interrupts) = 'object'),
  constraint chk_threads_values_type_ok
    check (values is null or jsonb_typeof(values) in ('object','array'))
);

create index if not exists idx_threads_user_updated on public.threads(user_id, updated_at desc);
create index if not exists idx_threads_status on public.threads(status);
create index if not exists idx_threads_agent on public.threads(agent_id);

-- Keep threads.updated_at current
create or replace function public._touch_thread_updated_at() returns trigger as $$
begin
  new.updated_at = now();
  return new;
end; $$ language plpgsql;

drop trigger if exists trg_touch_thread_updated_at on public.threads;
create trigger trg_touch_thread_updated_at
before update on public.threads
for each row execute function public._touch_thread_updated_at();

-- RLS: only owner can read/write threads
alter table public.threads enable row level security;

do $$ begin
  create policy threads_owner_all on public.threads
    for all using (user_id = auth.uid())
    with check (user_id = auth.uid());
exception when duplicate_object then null; end $$;