-- Applied before migration 016. PostgreSQL 17 automatically gives the role
-- creator ADMIN TRUE, INHERIT FALSE, SET FALSE membership in a role it creates.
-- Migration 016 temporarily adds SET TRUE only for function ownership transfer.

do $portfolio_role_bootstrap$
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
        raise exception 'portfolio_rpc_owner exists with unsafe role attributes';
    end if;
end
$portfolio_role_bootstrap$;
