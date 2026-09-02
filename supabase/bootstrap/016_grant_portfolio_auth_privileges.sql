-- Privileged prerequisite for migration 016.
-- Run after supabase/roles.sql and before migration 016 using a database role
-- that owns, or has grant options on, both the auth schema and auth.uid().

do $portfolio_auth_grant_preflight$
begin
    if not exists (
        select 1
          from pg_catalog.pg_roles
         where rolname = 'portfolio_rpc_owner'
    ) then
        raise exception 'portfolio_rpc_owner must exist before auth grants';
    end if;

    if not pg_catalog.has_schema_privilege(
        current_user,
        'auth',
        'USAGE WITH GRANT OPTION'
    ) or not pg_catalog.has_function_privilege(
        current_user,
        'auth.uid()',
        'EXECUTE WITH GRANT OPTION'
    ) then
        raise exception using
            message = 'current database role cannot grant portfolio auth prerequisites',
            hint = 'Run this bootstrap as the auth object owner or a database superuser; never use service_role or broaden PUBLIC grants.';
    end if;

    if pg_catalog.pg_has_role(
        'portfolio_rpc_owner',
        'service_role',
        'MEMBER'
    ) then
        raise exception 'portfolio_rpc_owner must not inherit service_role';
    end if;
end
$portfolio_auth_grant_preflight$;

grant usage on schema auth to portfolio_rpc_owner;
grant execute on function auth.uid() to portfolio_rpc_owner;

do $portfolio_auth_grant_postcheck$
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
        raise exception 'portfolio auth prerequisite grants did not take effect';
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
$portfolio_auth_grant_postcheck$;
