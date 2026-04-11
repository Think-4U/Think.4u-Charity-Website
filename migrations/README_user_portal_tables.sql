-- Run this in Supabase SQL Editor to support the new user portal features.

alter table if exists public.users
    add column if not exists name text,
    add column if not exists role text default 'donor',
    add column if not exists email_verified boolean default false;

alter table if exists public.donations
    add column if not exists user_id bigint;

alter table if exists public.volunteers
    add column if not exists user_id bigint,
    add column if not exists interest text;

create table if not exists public.notifications (
    id bigserial primary key,
    user_id bigint not null,
    title text not null,
    body text not null,
    created_at timestamptz default now()
);

create table if not exists public.appointments (
    id bigserial primary key,
    user_id bigint not null,
    name text,
    email text,
    appointment_date text not null,
    appointment_time text not null,
    purpose text not null,
    notes text,
    status text default 'pending',
    created_at timestamptz default now()
);

create table if not exists public.grievances (
    id bigserial primary key,
    user_id bigint not null,
    name text,
    email text,
    issue_type text not null,
    subject text not null,
    message text not null,
    status text default 'open',
    admin_note text,
    updated_at timestamptz,
    created_at timestamptz default now()
);

create table if not exists public.volunteer_events (
    id bigserial primary key,
    program_id bigint references public.programs(id) on delete set null,
    title text not null,
    description text,
    location text,
    event_date text,
    created_at timestamptz default now()
);

create table if not exists public.event_participants (
    id bigserial primary key,
    event_id bigint not null references public.volunteer_events(id) on delete cascade,
    user_id bigint not null references public.users(id) on delete cascade,
    name text,
    email text,
    role text not null default 'donor',
    status text not null default 'registered',
    created_at timestamptz default now(),
    unique (event_id, user_id)
);

create table if not exists public.event_certificates (
    id bigserial primary key,
    event_id bigint not null references public.volunteer_events(id) on delete cascade,
    user_id bigint not null references public.users(id) on delete cascade,
    status text not null default 'pending',
    certificate_url text,
    review_note text,
    reviewed_by_user_id bigint references public.users(id) on delete set null,
    reviewed_at timestamptz,
    created_at timestamptz default now(),
    unique (event_id, user_id)
);

create table if not exists public.fundraisers (
    id bigserial primary key,
    title text not null,
    description text,
    target_amount numeric default 0,
    raised_amount numeric default 0,
    status text default 'active',
    updated_at timestamptz,
    created_at timestamptz default now()
);
