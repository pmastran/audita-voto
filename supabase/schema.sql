-- Audita Voto: tabelas isoladas. Execute SOMENTE em projeto Supabase exclusivo.
-- Linhas públicas são somente leitura; apenas o job com credencial secreta escreve.
create table if not exists public.av_catalogos (
  chave text primary key,
  conteudo jsonb not null,
  url_origem text not null,
  atualizado_em timestamptz not null default now(),
  constraint av_catalogos_chave_chk check (chave = 'tse2026bu')
);
create table if not exists public.av_relatorios (
  chave_relatorio text primary key,
  uf text not null check (uf ~ '^[A-Z]{2}$'),
  turno smallint not null check (turno in (1,2)),
  modo text not null check (modo in ('completo','nominal')),
  comparecimento_minimo integer not null check (comparecimento_minimo between 0 and 9999),
  minimo_secoes integer not null check (minimo_secoes between 2 and 20),
  mesmo_municipio boolean not null,
  sha512_oficial text not null check (sha512_oficial ~ '^[0-9a-f]{128}$'),
  arquivo_url text not null,
  versao_parser text not null,
  executado_em timestamptz not null,
  relatorio jsonb not null,
  publicado boolean not null default false,
  criado_em timestamptz not null default now()
);
create index if not exists av_relatorios_filtros_idx
 on public.av_relatorios (uf,turno,modo,comparecimento_minimo,minimo_secoes,mesmo_municipio,executado_em desc) where publicado;
alter table public.av_catalogos enable row level security;
alter table public.av_relatorios enable row level security;
revoke all on table public.av_catalogos, public.av_relatorios from public, anon, authenticated;
grant select on table public.av_catalogos, public.av_relatorios to anon, authenticated;
grant select, insert, update, delete on table public.av_catalogos, public.av_relatorios to service_role;
drop policy if exists av_catalogos_leitura_publica on public.av_catalogos;
create policy av_catalogos_leitura_publica on public.av_catalogos
 for select to anon, authenticated using (true);
drop policy if exists av_relatorios_somente_publicados on public.av_relatorios;
create policy av_relatorios_somente_publicados on public.av_relatorios
 for select to anon, authenticated using (publicado is true);
