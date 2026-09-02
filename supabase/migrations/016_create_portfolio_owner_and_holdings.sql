-- Portfolio Phase 1A foundation only.
-- Transactions, transaction foreign keys, decisions, and Holding mutation RPCs
-- are intentionally deferred to later approved migrations.
--
-- Privileged prerequisite:
--   1. apply supabase/roles.sql;
--   2. run supabase/bootstrap/016_grant_portfolio_auth_privileges.sql as the
--      auth schema/function owner or a database superuser;
--   3. apply this migration with the standard migration runner.

do $portfolio_role$
declare
    v_role pg_catalog.pg_roles%rowtype;
begin
    select *
      into v_role
      from pg_catalog.pg_roles
     where rolname = 'portfolio_rpc_owner';

    if not found then
        create role portfolio_rpc_owner
            nologin
            nosuperuser
            nocreatedb
            nocreaterole
            noinherit
            noreplication
            nobypassrls;
    elsif v_role.rolcanlogin
       or v_role.rolsuper
       or v_role.rolcreatedb
       or v_role.rolcreaterole
       or v_role.rolinherit
       or v_role.rolreplication
       or v_role.rolbypassrls then
        raise exception 'portfolio_rpc_owner has unsafe role attributes';
    end if;

    if not pg_catalog.pg_has_role(
        current_user,
        'portfolio_rpc_owner',
        'MEMBER WITH ADMIN OPTION'
    ) then
        raise exception 'migration runner lacks ADMIN OPTION on portfolio_rpc_owner';
    end if;

    if pg_catalog.pg_has_role(
        'portfolio_rpc_owner',
        'service_role',
        'MEMBER'
    ) then
        raise exception 'portfolio_rpc_owner must not inherit service_role';
    end if;

    if pg_catalog.pg_has_role(
        'authenticated',
        'portfolio_rpc_owner',
        'SET'
    ) or pg_catalog.pg_has_role(
        'anon',
        'portfolio_rpc_owner',
        'SET'
    ) then
        raise exception 'request roles must not assume portfolio_rpc_owner';
    end if;

    if exists (
        select 1
          from pg_catalog.pg_auth_members as membership
          join pg_catalog.pg_roles as granted_role
            on granted_role.oid = membership.roleid
         where granted_role.rolname = 'portfolio_rpc_owner'
           and membership.set_option
    ) then
        raise exception 'portfolio_rpc_owner has a pre-existing SET membership';
    end if;
end
$portfolio_role$;

create table public.portfolios (
    id uuid primary key default pg_catalog.gen_random_uuid(),
    owner_id uuid not null,
    name varchar(80) not null,
    base_currency char(3) not null default 'USD',
    timezone varchar(64) not null default 'UTC',
    status varchar(16) not null default 'active',
    created_at timestamptz not null default pg_catalog.now(),
    updated_at timestamptz not null default pg_catalog.now(),
    constraint portfolios_owner_id_fkey
        foreign key (owner_id)
        references auth.users (id)
        on delete restrict,
    constraint portfolios_owner_id_id_key unique (owner_id, id),
    constraint portfolios_name_check check (
        name = pg_catalog.btrim(name)
        and pg_catalog.char_length(name) between 1 and 80
    ),
    constraint portfolios_base_currency_check check (base_currency = 'USD'),
    constraint portfolios_timezone_check check (
        timezone = pg_catalog.btrim(timezone)
        and pg_catalog.char_length(timezone) between 1 and 64
    ),
    constraint portfolios_status_check check (status in ('active', 'archived'))
);

create index portfolios_owner_status_created_at_idx
    on public.portfolios (owner_id, status, created_at desc);

create table public.portfolio_holdings (
    owner_id uuid not null,
    portfolio_id uuid not null,
    ticker varchar(12) not null,
    quantity numeric(28,8) not null,
    average_cost numeric(20,8) not null,
    last_transaction_id uuid null,
    version bigint not null,
    created_at timestamptz not null default pg_catalog.now(),
    updated_at timestamptz not null default pg_catalog.now(),
    constraint portfolio_holdings_pkey
        primary key (owner_id, portfolio_id, ticker),
    constraint portfolio_holdings_owner_portfolio_fkey
        foreign key (owner_id, portfolio_id)
        references public.portfolios (owner_id, id)
        on delete restrict,
    constraint portfolio_holdings_ticker_check check (
        ticker = pg_catalog.upper(ticker)
        and ticker ~ '^[A-Z0-9][A-Z0-9.-]{0,11}$'
    ),
    constraint portfolio_holdings_quantity_check check (quantity > 0),
    constraint portfolio_holdings_average_cost_check check (average_cost > 0),
    constraint portfolio_holdings_version_check check (version > 0)
);

alter table public.portfolios enable row level security;
alter table public.portfolios force row level security;
alter table public.portfolio_holdings enable row level security;
alter table public.portfolio_holdings force row level security;

create policy portfolios_select_own
    on public.portfolios
    for select
    to authenticated
    using (owner_id = (select auth.uid()));

create policy portfolios_select_own_rpc
    on public.portfolios
    for select
    to portfolio_rpc_owner
    using (owner_id = (select auth.uid()));

create policy portfolios_insert_own_rpc
    on public.portfolios
    for insert
    to portfolio_rpc_owner
    with check (owner_id = (select auth.uid()));

create policy portfolios_update_own_rpc
    on public.portfolios
    for update
    to portfolio_rpc_owner
    using (owner_id = (select auth.uid()))
    with check (owner_id = (select auth.uid()));

create policy portfolio_holdings_select_own
    on public.portfolio_holdings
    for select
    to authenticated
    using (owner_id = (select auth.uid()));

-- These policies are intentionally inert in 016: portfolio_rpc_owner receives no
-- privilege on portfolio_holdings until an approved atomic projection RPC exists.
create policy portfolio_holdings_insert_own_rpc
    on public.portfolio_holdings
    for insert
    to portfolio_rpc_owner
    with check (owner_id = (select auth.uid()));

create policy portfolio_holdings_update_own_rpc
    on public.portfolio_holdings
    for update
    to portfolio_rpc_owner
    using (owner_id = (select auth.uid()))
    with check (owner_id = (select auth.uid()));

create policy portfolio_holdings_delete_own_rpc
    on public.portfolio_holdings
    for delete
    to portfolio_rpc_owner
    using (owner_id = (select auth.uid()));

revoke all on table public.portfolios
    from public, anon, authenticated, portfolio_rpc_owner;
revoke all on table public.portfolio_holdings
    from public, anon, authenticated, portfolio_rpc_owner;

grant select on table public.portfolios, public.portfolio_holdings
    to authenticated;
grant select, insert, update on table public.portfolios
    to portfolio_rpc_owner;

grant usage on schema public to portfolio_rpc_owner;

do $portfolio_auth_boundary$
begin
    if not pg_catalog.has_schema_privilege(
        'portfolio_rpc_owner',
        'auth',
        'USAGE'
    ) or not pg_catalog.has_function_privilege(
        'portfolio_rpc_owner',
        'auth.uid()',
        'EXECUTE'
    ) then
        raise exception using
            message = 'portfolio_rpc_owner cannot resolve auth.uid()',
            hint = 'Apply supabase/bootstrap/016_grant_portfolio_auth_privileges.sql with the required auth object grant options before migration 016.';
    end if;

    if exists (
        select 1
          from (
            values
                ('SELECT'),
                ('INSERT'),
                ('UPDATE'),
                ('DELETE'),
                ('TRUNCATE'),
                ('REFERENCES'),
                ('TRIGGER'),
                ('MAINTAIN')
          ) as checked_privileges(privilege_name)
         where pg_catalog.has_table_privilege(
            'portfolio_rpc_owner',
            'auth.users',
            checked_privileges.privilege_name
         )
    ) then
        raise exception 'portfolio_rpc_owner must not access auth.users';
    end if;
end
$portfolio_auth_boundary$;

create function public.create_portfolio(
    p_name text,
    p_base_currency text default 'USD',
    p_timezone text default 'UTC'
)
returns public.portfolios
language plpgsql
security definer
set search_path = pg_catalog
as $create_portfolio$
declare
    v_owner_id uuid := auth.uid();
    v_name text;
    v_timezone text;
    v_portfolio public.portfolios;
begin
    if v_owner_id is null then
        raise exception using
            errcode = 'P0001',
            message = 'auth_required';
    end if;

    v_name := pg_catalog.btrim(p_name);
    if p_name is null
       or pg_catalog.char_length(v_name) < 1
       or pg_catalog.char_length(v_name) > 80 then
        raise exception using
            errcode = '22023',
            message = 'validation_error:name';
    end if;

    if p_base_currency is distinct from 'USD' then
        raise exception using
            errcode = '22023',
            message = 'validation_error:base_currency';
    end if;

    v_timezone := pg_catalog.btrim(p_timezone);
    if p_timezone is null
       or pg_catalog.char_length(v_timezone) < 1
       or pg_catalog.char_length(v_timezone) > 64
       or not exists (
            select 1
              from pg_catalog.pg_timezone_names as timezone_name
             where timezone_name.name = v_timezone
       ) then
        raise exception using
            errcode = '22023',
            message = 'validation_error:timezone';
    end if;

    insert into public.portfolios (
        owner_id,
        name,
        base_currency,
        timezone
    )
    values (
        v_owner_id,
        v_name,
        p_base_currency,
        v_timezone
    )
    returning * into v_portfolio;

    return v_portfolio;
end
$create_portfolio$;

create function public.archive_portfolio(p_portfolio_id uuid)
returns public.portfolios
language plpgsql
security definer
set search_path = pg_catalog
as $archive_portfolio$
declare
    v_owner_id uuid := auth.uid();
    v_portfolio public.portfolios;
begin
    if v_owner_id is null then
        raise exception using
            errcode = 'P0001',
            message = 'auth_required';
    end if;

    select portfolio.*
      into v_portfolio
      from public.portfolios as portfolio
     where portfolio.id = p_portfolio_id
       and portfolio.owner_id = v_owner_id
     for update;

    if not found then
        raise exception using
            errcode = 'P0001',
            message = 'portfolio_not_found';
    end if;

    if v_portfolio.status <> 'archived' then
        update public.portfolios as portfolio
           set status = 'archived',
               updated_at = pg_catalog.now()
         where portfolio.id = p_portfolio_id
           and portfolio.owner_id = v_owner_id
        returning portfolio.* into v_portfolio;
    end if;

    return v_portfolio;
end
$archive_portfolio$;

create function public.restore_portfolio(p_portfolio_id uuid)
returns public.portfolios
language plpgsql
security definer
set search_path = pg_catalog
as $restore_portfolio$
declare
    v_owner_id uuid := auth.uid();
    v_portfolio public.portfolios;
begin
    if v_owner_id is null then
        raise exception using
            errcode = 'P0001',
            message = 'auth_required';
    end if;

    select portfolio.*
      into v_portfolio
      from public.portfolios as portfolio
     where portfolio.id = p_portfolio_id
       and portfolio.owner_id = v_owner_id
     for update;

    if not found then
        raise exception using
            errcode = 'P0001',
            message = 'portfolio_not_found';
    end if;

    if v_portfolio.status <> 'active' then
        update public.portfolios as portfolio
           set status = 'active',
               updated_at = pg_catalog.now()
         where portfolio.id = p_portfolio_id
           and portfolio.owner_id = v_owner_id
        returning portfolio.* into v_portfolio;
    end if;

    return v_portfolio;
end
$restore_portfolio$;

revoke all on function public.create_portfolio(text, text, text)
    from public, anon;
revoke all on function public.archive_portfolio(uuid)
    from public, anon;
revoke all on function public.restore_portfolio(uuid)
    from public, anon;

grant execute on function public.create_portfolio(text, text, text)
    to authenticated;
grant execute on function public.archive_portfolio(uuid)
    to authenticated;
grant execute on function public.restore_portfolio(uuid)
    to authenticated;

-- PostgreSQL requires the new function owner to have CREATE on the containing
-- schema and the migration runner to have SET TRUE membership in the new owner.
-- Both grants are temporary and are removed in this transaction.
grant create on schema public to portfolio_rpc_owner;

grant portfolio_rpc_owner to current_user
    with inherit false, set true
    granted by current_user;

do $portfolio_owner_transfer_boundary$
begin
    if not pg_catalog.pg_has_role(
        current_user,
        'portfolio_rpc_owner',
        'SET'
    ) then
        raise exception 'migration runner cannot SET ROLE portfolio_rpc_owner';
    end if;
end
$portfolio_owner_transfer_boundary$;

alter function public.create_portfolio(text, text, text)
    owner to portfolio_rpc_owner;
alter function public.archive_portfolio(uuid)
    owner to portfolio_rpc_owner;
alter function public.restore_portfolio(uuid)
    owner to portfolio_rpc_owner;

revoke portfolio_rpc_owner from current_user
    granted by current_user;
revoke create on schema public from portfolio_rpc_owner;

do $portfolio_schema_boundary$
begin
    if pg_catalog.has_schema_privilege(
        'portfolio_rpc_owner',
        'public',
        'CREATE'
    ) then
        raise exception 'portfolio_rpc_owner must not retain public schema CREATE';
    end if;

    if exists (
        select 1
          from pg_catalog.pg_auth_members as membership
          join pg_catalog.pg_roles as granted_role
            on granted_role.oid = membership.roleid
         where granted_role.rolname = 'portfolio_rpc_owner'
           and membership.set_option
    ) then
        raise exception 'temporary portfolio_rpc_owner SET membership remains';
    end if;

    if pg_catalog.pg_has_role(
        'authenticated',
        'portfolio_rpc_owner',
        'SET'
    ) or pg_catalog.pg_has_role(
        'anon',
        'portfolio_rpc_owner',
        'SET'
    ) then
        raise exception 'request roles must not assume portfolio_rpc_owner';
    end if;

    if exists (
        select 1
          from pg_catalog.pg_roles as role_record
         where role_record.rolname = 'portfolio_rpc_owner'
           and (
                role_record.rolcanlogin
                or role_record.rolbypassrls
           )
    ) then
        raise exception 'portfolio_rpc_owner role attributes changed';
    end if;
end
$portfolio_schema_boundary$;

comment on table public.portfolios is
    'Owner-scoped portfolio containers. Phase 1A foundation.';
comment on table public.portfolio_holdings is
    'Current portfolio projection. No write path exists in migration 016.';
comment on column public.portfolio_holdings.last_transaction_id is
    'Nullable and intentionally has no transaction FK until migration 017.';
