create extension if not exists pgcrypto;

insert into storage.buckets (id, name, public)
values ('scholar-archive', 'scholar-archive', true)
on conflict (id) do update set public = excluded.public;

create table if not exists public.documents (
  id bigint generated always as identity primary key,
  slug text not null unique,
  title text not null,
  author_display text,
  publication_year integer,
  century_label text,
  language text,
  journal_or_book text,
  volume text,
  issue text,
  page_range text,
  doi text,
  summary text,
  pipeline_version text,
  status text not null default 'published',
  storage_bucket text not null default 'scholar-archive',
  source_pdf_path text,
  digitalized_pdf_path text,
  korean_pdf_path text,
  cover_image_path text,
  page_count integer not null default 0,
  requested_page_count integer not null default 0,
  rights_assessment text,
  source_hash text,
  published_at timestamptz,
  updated_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);

create table if not exists public.authors (
  id bigint generated always as identity primary key,
  display_name text not null,
  sort_name text not null unique,
  birth_year integer,
  death_year integer,
  created_at timestamptz not null default now()
);

create table if not exists public.document_authors (
  document_id bigint not null references public.documents(id) on delete cascade,
  author_id bigint not null references public.authors(id) on delete cascade,
  ordinal integer not null default 1,
  primary key (document_id, author_id)
);

create table if not exists public.document_pages (
  id bigint generated always as identity primary key,
  document_id bigint not null references public.documents(id) on delete cascade,
  page_number integer not null,
  image_path text,
  digitalized_tex_path text,
  digitalized_text text,
  korean_text text,
  structure_json_path text,
  created_at timestamptz not null default now(),
  unique (document_id, page_number)
);

create table if not exists public.document_assets (
  id bigint generated always as identity primary key,
  document_id bigint not null references public.documents(id) on delete cascade,
  asset_type text not null,
  storage_bucket text not null,
  storage_path text not null,
  mime_type text,
  byte_size bigint,
  created_at timestamptz not null default now(),
  unique (document_id, storage_path)
);

create table if not exists public.document_metadata_snapshots (
  document_id bigint primary key references public.documents(id) on delete cascade,
  raw_pdf_metadata jsonb not null default '{}'::jsonb,
  deterministic_metadata jsonb not null default '{}'::jsonb,
  ai_metadata jsonb not null default '{}'::jsonb,
  effective_metadata jsonb not null default '{}'::jsonb,
  rights_metadata jsonb not null default '{}'::jsonb,
  layout_profile jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

alter table public.documents enable row level security;
alter table public.authors enable row level security;
alter table public.document_authors enable row level security;
alter table public.document_pages enable row level security;
alter table public.document_assets enable row level security;
alter table public.document_metadata_snapshots enable row level security;

drop policy if exists "public read documents" on public.documents;
create policy "public read documents" on public.documents
for select
to anon, authenticated
using (true);

drop policy if exists "public read authors" on public.authors;
create policy "public read authors" on public.authors
for select
to anon, authenticated
using (true);

drop policy if exists "public read document_authors" on public.document_authors;
create policy "public read document_authors" on public.document_authors
for select
to anon, authenticated
using (true);

drop policy if exists "public read document_pages" on public.document_pages;
create policy "public read document_pages" on public.document_pages
for select
to anon, authenticated
using (true);

drop policy if exists "public read document_assets" on public.document_assets;
create policy "public read document_assets" on public.document_assets
for select
to anon, authenticated
using (true);

drop policy if exists "public read document_metadata_snapshots" on public.document_metadata_snapshots;
create policy "public read document_metadata_snapshots" on public.document_metadata_snapshots
for select
to anon, authenticated
using (true);

drop policy if exists "public read storage objects" on storage.objects;
create policy "public read storage objects" on storage.objects
for select
to anon, authenticated
using (bucket_id = 'scholar-archive');
