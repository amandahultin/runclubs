-- Gilla- och klickräkning för runclubs.se/events.
--
-- Kör hela filen i Supabase → SQL Editor. Den går att köra om (idempotent).
--
-- Besökare (rollen anon) kan inte läsa eller skriva tabellen direkt — bara anropa
-- funktionerna nedan via /rest/v1/rpc/<namn>. event_id är kortets id på sidan
-- (10 hex-tecken), visitor ett slumpat id som webbläsaren sparar lokalt.

create table if not exists public.event_interactions (
  id         bigint generated always as identity primary key,
  event_id   text        not null check (event_id ~ '^[0-9a-f]{10}$'),
  kind       text        not null check (kind in ('like', 'click')),
  visitor    text        not null check (char_length(visitor) between 8 and 64),
  created_at timestamptz not null default now()
);

-- En gillning per webbläsare och event.
create unique index if not exists event_interactions_one_like
  on public.event_interactions (event_id, visitor) where kind = 'like';
create index if not exists event_interactions_event on public.event_interactions (event_id, kind);
create index if not exists event_interactions_time  on public.event_interactions (created_at);

alter table public.event_interactions enable row level security;
revoke all on public.event_interactions from anon, authenticated;


-- Antal för ett event: (likes, clicks).
create or replace function public._event_counts(p_event_id text)
returns table (likes bigint, clicks bigint)
language sql stable security definer set search_path = ''
as $$
  select count(*) filter (where kind = 'like'),
         count(*) filter (where kind = 'click')
  from public.event_interactions
  where event_id = p_event_id;
$$;
revoke all on function public._event_counts(text) from public, anon, authenticated;


create or replace function public.like_event(p_event_id text, p_visitor text)
returns table (likes bigint, clicks bigint)
language plpgsql security definer set search_path = ''
as $$
begin
  insert into public.event_interactions (event_id, kind, visitor)
  values (p_event_id, 'like', p_visitor)
  on conflict (event_id, visitor) where kind = 'like' do nothing;
  return query select * from public._event_counts(p_event_id);
end;
$$;


create or replace function public.unlike_event(p_event_id text, p_visitor text)
returns table (likes bigint, clicks bigint)
language plpgsql security definer set search_path = ''
as $$
begin
  delete from public.event_interactions
  where event_id = p_event_id and visitor = p_visitor and kind = 'like';
  return query select * from public._event_counts(p_event_id);
end;
$$;


-- Klick på "Till passet". Samma webbläsare räknas max en gång per event och 10 minuter.
create or replace function public.click_event(p_event_id text, p_visitor text)
returns table (likes bigint, clicks bigint)
language plpgsql security definer set search_path = ''
as $$
begin
  if not exists (
    select 1 from public.event_interactions
    where event_id = p_event_id and visitor = p_visitor and kind = 'click'
      and created_at > now() - interval '10 minutes'
  ) then
    insert into public.event_interactions (event_id, kind, visitor)
    values (p_event_id, 'click', p_visitor);
  end if;
  return query select * from public._event_counts(p_event_id);
end;
$$;


-- Statistik för flera event på en gång (max 500). *_7d = senaste 7 dagarna,
-- för tidsviktad popularitet.
create or replace function public.get_event_stats(p_event_ids text[])
returns table (event_id text, likes bigint, clicks bigint, likes_7d bigint, clicks_7d bigint)
language sql stable security definer set search_path = ''
as $$
  select i.event_id,
         count(*) filter (where i.kind = 'like'),
         count(*) filter (where i.kind = 'click'),
         count(*) filter (where i.kind = 'like'  and i.created_at > now() - interval '7 days'),
         count(*) filter (where i.kind = 'click' and i.created_at > now() - interval '7 days')
  from public.event_interactions i
  where i.event_id = any (p_event_ids[1:500])
  group by i.event_id;
$$;


revoke all on function public.like_event(text, text)      from public;
revoke all on function public.unlike_event(text, text)    from public;
revoke all on function public.click_event(text, text)     from public;
revoke all on function public.get_event_stats(text[])     from public;
grant execute on function public.like_event(text, text)   to anon, authenticated;
grant execute on function public.unlike_event(text, text) to anon, authenticated;
grant execute on function public.click_event(text, text)  to anon, authenticated;
grant execute on function public.get_event_stats(text[])  to anon, authenticated;
