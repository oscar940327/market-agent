-- Run against a disposable Supabase database after migrations 001-016.
-- The transaction is rolled back so no test Auth user or Portfolio survives.

begin;

create extension if not exists pgtap with schema extensions;
grant usage on schema extensions to authenticated, anon;
grant execute on all functions in schema extensions to authenticated, anon;

set local search_path = extensions, public, pg_catalog;

select extensions.plan(40);

select extensions.has_table(
    'public',
    'portfolios',
    '016 creates public.portfolios'
);
select extensions.has_table(
    'public',
    'portfolio_holdings',
    '016 creates public.portfolio_holdings'
);
select extensions.ok(
    exists (
        select 1
          from information_schema.columns
         where table_schema = 'public'
           and table_name = 'portfolio_holdings'
           and column_name = 'last_transaction_id'
           and is_nullable = 'YES'
    ),
    'last_transaction_id remains nullable in 016'
);
select extensions.ok(
    not exists (
        select 1
          from pg_catalog.pg_constraint as constraint_record
          join pg_catalog.pg_attribute as attribute_record
            on attribute_record.attrelid = constraint_record.conrelid
           and attribute_record.attnum = any (constraint_record.conkey)
         where constraint_record.conrelid = 'public.portfolio_holdings'::regclass
           and constraint_record.contype = 'f'
           and attribute_record.attname = 'last_transaction_id'
    ),
    'last_transaction_id has no foreign key in 016'
);
select extensions.ok(
    (
        select pg_catalog.bool_and(class_record.relrowsecurity)
          from pg_catalog.pg_class as class_record
         where class_record.oid in (
            'public.portfolios'::regclass,
            'public.portfolio_holdings'::regclass
         )
    ),
    'RLS is enabled on both 016 tables'
);
select extensions.ok(
    (
        select pg_catalog.bool_and(class_record.relforcerowsecurity)
          from pg_catalog.pg_class as class_record
         where class_record.oid in (
            'public.portfolios'::regclass,
            'public.portfolio_holdings'::regclass
         )
    ),
    'FORCE RLS is enabled on both 016 tables'
);
select extensions.ok(
    (
        select not role_record.rolcanlogin
           and not role_record.rolsuper
           and not role_record.rolcreatedb
           and not role_record.rolcreaterole
           and not role_record.rolinherit
           and not role_record.rolreplication
           and not role_record.rolbypassrls
          from pg_catalog.pg_roles as role_record
         where role_record.rolname = 'portfolio_rpc_owner'
    ),
    'portfolio_rpc_owner has dedicated non-login non-bypass attributes'
);
select extensions.ok(
    not pg_catalog.pg_has_role(
        'portfolio_rpc_owner',
        'service_role',
        'MEMBER'
    )
    and not exists (
        select 1
          from pg_catalog.pg_auth_members as membership
          join pg_catalog.pg_roles as granted_role
            on granted_role.oid = membership.roleid
         where granted_role.rolname = 'portfolio_rpc_owner'
           and membership.set_option
    )
    and not pg_catalog.pg_has_role(
        'authenticated',
        'portfolio_rpc_owner',
        'SET'
    )
    and not pg_catalog.pg_has_role(
        'anon',
        'portfolio_rpc_owner',
        'SET'
    ),
    'temporary SET membership is gone and request roles cannot assume RPC owner'
);
select extensions.ok(
    not pg_catalog.has_schema_privilege(
        'portfolio_rpc_owner',
        'public',
        'CREATE'
    ),
    'portfolio_rpc_owner cannot create arbitrary public schema objects'
);
select extensions.ok(
    (
        select pg_catalog.bool_and(owner_role.rolname <> 'portfolio_rpc_owner')
          from pg_catalog.pg_class as class_record
          join pg_catalog.pg_roles as owner_role
            on owner_role.oid = class_record.relowner
         where class_record.oid in (
            'public.portfolios'::regclass,
            'public.portfolio_holdings'::regclass
         )
    ),
    'portfolio_rpc_owner does not own Portfolio tables'
);
select extensions.is(
    (
        select pg_catalog.count(*)
          from pg_catalog.pg_proc as function_record
          join pg_catalog.pg_namespace as namespace_record
            on namespace_record.oid = function_record.pronamespace
         where namespace_record.nspname = 'public'
           and function_record.proname in (
                'create_portfolio',
                'archive_portfolio',
                'restore_portfolio'
           )
    ),
    3::bigint,
    '016 exposes exactly one signature for each approved mutation RPC'
);
select extensions.ok(
    (
        select pg_catalog.bool_and(function_record.prosecdef)
          from pg_catalog.pg_proc as function_record
          join pg_catalog.pg_namespace as namespace_record
            on namespace_record.oid = function_record.pronamespace
         where namespace_record.nspname = 'public'
           and function_record.proname in (
                'create_portfolio',
                'archive_portfolio',
                'restore_portfolio'
           )
    ),
    'all approved RPCs are SECURITY DEFINER'
);
select extensions.ok(
    (
        select pg_catalog.bool_and(owner_role.rolname = 'portfolio_rpc_owner')
          from pg_catalog.pg_proc as function_record
          join pg_catalog.pg_namespace as namespace_record
            on namespace_record.oid = function_record.pronamespace
          join pg_catalog.pg_roles as owner_role
            on owner_role.oid = function_record.proowner
         where namespace_record.nspname = 'public'
           and function_record.proname in (
                'create_portfolio',
                'archive_portfolio',
                'restore_portfolio'
           )
    ),
    'all approved RPCs are owned by portfolio_rpc_owner'
);
select extensions.ok(
    (
        select pg_catalog.bool_and(
            function_record.proconfig @> array['search_path=pg_catalog']::text[]
        )
          from pg_catalog.pg_proc as function_record
          join pg_catalog.pg_namespace as namespace_record
            on namespace_record.oid = function_record.pronamespace
         where namespace_record.nspname = 'public'
           and function_record.proname in (
                'create_portfolio',
                'archive_portfolio',
                'restore_portfolio'
           )
    ),
    'all approved RPCs fix search_path=pg_catalog'
);
select extensions.ok(
    not exists (
        select 1
          from pg_catalog.pg_class as class_record
          cross join lateral pg_catalog.aclexplode(
            coalesce(
                class_record.relacl,
                pg_catalog.acldefault('r', class_record.relowner)
            )
          ) as privilege_record
         where class_record.oid in (
            'public.portfolios'::regclass,
            'public.portfolio_holdings'::regclass
         )
           and privilege_record.grantee = 0
    )
    and (
        select pg_catalog.bool_and(
            not pg_catalog.has_table_privilege(
                'anon',
                checked_table,
                checked_privilege
            )
        )
          from (
            values ('public.portfolios'), ('public.portfolio_holdings')
          ) as tables(checked_table)
          cross join (
            values
                ('SELECT'),
                ('INSERT'),
                ('UPDATE'),
                ('DELETE'),
                ('TRUNCATE'),
                ('REFERENCES'),
                ('TRIGGER')
          ) as privileges(checked_privilege)
    ),
    'PUBLIC and anon have no Portfolio table privileges'
);
select extensions.ok(
    pg_catalog.has_table_privilege('authenticated', 'public.portfolios', 'SELECT')
    and pg_catalog.has_table_privilege(
        'authenticated',
        'public.portfolio_holdings',
        'SELECT'
    ),
    'authenticated can directly SELECT both owner-scoped tables'
);
select extensions.ok(
    (
        select pg_catalog.bool_and(
            not pg_catalog.has_table_privilege(
                'authenticated',
                checked_table,
                checked_privilege
            )
        )
          from (
            values ('public.portfolios'), ('public.portfolio_holdings')
          ) as tables(checked_table)
          cross join (
            values
                ('INSERT'),
                ('UPDATE'),
                ('DELETE'),
                ('TRUNCATE'),
                ('REFERENCES'),
                ('TRIGGER')
          ) as privileges(checked_privilege)
    ),
    'authenticated has no direct Portfolio mutation privileges'
);
select extensions.ok(
    pg_catalog.has_table_privilege(
        'portfolio_rpc_owner',
        'public.portfolios',
        'SELECT'
    )
    and pg_catalog.has_table_privilege(
        'portfolio_rpc_owner',
        'public.portfolios',
        'INSERT'
    )
    and pg_catalog.has_table_privilege(
        'portfolio_rpc_owner',
        'public.portfolios',
        'UPDATE'
    )
    and not pg_catalog.has_table_privilege(
        'portfolio_rpc_owner',
        'public.portfolios',
        'DELETE'
    ),
    'portfolio_rpc_owner has only the Portfolio privileges needed by 016 RPCs'
);
select extensions.ok(
    (
        select pg_catalog.bool_and(
            not pg_catalog.has_table_privilege(
                'portfolio_rpc_owner',
                'public.portfolio_holdings',
                checked_privilege
            )
        )
          from (
            values
                ('SELECT'),
                ('INSERT'),
                ('UPDATE'),
                ('DELETE'),
                ('TRUNCATE'),
                ('REFERENCES'),
                ('TRIGGER')
          ) as privileges(checked_privilege)
    ),
    'portfolio_rpc_owner has no Holding privilege in 016'
);
select extensions.ok(
    not exists (
        select 1
          from pg_catalog.pg_proc as function_record
          join pg_catalog.pg_namespace as namespace_record
            on namespace_record.oid = function_record.pronamespace
          cross join lateral pg_catalog.aclexplode(
            coalesce(
                function_record.proacl,
                pg_catalog.acldefault('f', function_record.proowner)
            )
          ) as privilege_record
         where namespace_record.nspname = 'public'
           and function_record.proname in (
                'create_portfolio',
                'archive_portfolio',
                'restore_portfolio'
           )
           and privilege_record.grantee = 0
           and privilege_record.privilege_type = 'EXECUTE'
    )
    and (
        select pg_catalog.bool_and(
            not pg_catalog.has_function_privilege(
                'anon',
                checked_function,
                'EXECUTE'
            )
        )
          from (
            values
                ('public.create_portfolio(text,text,text)'),
                ('public.archive_portfolio(uuid)'),
                ('public.restore_portfolio(uuid)')
          ) as functions(checked_function)
    ),
    'PUBLIC and anon cannot execute Portfolio mutation RPCs'
);
select extensions.ok(
    (
        select pg_catalog.bool_and(
            pg_catalog.has_function_privilege(
                'authenticated',
                checked_function,
                'EXECUTE'
            )
        )
          from (
            values
                ('public.create_portfolio(text,text,text)'),
                ('public.archive_portfolio(uuid)'),
                ('public.restore_portfolio(uuid)')
          ) as functions(checked_function)
    ),
    'authenticated can execute only the approved Portfolio RPCs'
);
select extensions.ok(
    pg_catalog.to_regclass('public.portfolio_transactions') is null,
    '016 does not create portfolio_transactions'
);
select extensions.ok(
    pg_catalog.to_regclass('public.investment_decisions') is null,
    '016 does not create investment_decisions'
);
select extensions.ok(
    pg_catalog.has_schema_privilege(
        'portfolio_rpc_owner',
        'auth',
        'USAGE'
    )
    and pg_catalog.has_function_privilege(
        'portfolio_rpc_owner',
        'auth.uid()',
        'EXECUTE'
    )
    and not pg_catalog.has_table_privilege(
        'portfolio_rpc_owner',
        'auth.users',
        'SELECT'
    )
    and not pg_catalog.has_table_privilege(
        'portfolio_rpc_owner',
        'auth.users',
        'INSERT'
    )
    and not pg_catalog.has_table_privilege(
        'portfolio_rpc_owner',
        'auth.users',
        'UPDATE'
    )
    and not pg_catalog.has_table_privilege(
        'portfolio_rpc_owner',
        'auth.users',
        'DELETE'
    ),
    'RPC owner can resolve auth.uid without auth.users table access'
);
select extensions.ok(
    not exists (
        select 1
          from pg_catalog.pg_constraint as constraint_record
         where constraint_record.conrelid = 'public.portfolio_holdings'::regclass
           and constraint_record.confrelid = pg_catalog.to_regclass(
                'public.portfolio_transactions'
           )
    ),
    '016 contains no Holding-to-Transaction foreign key'
);

insert into auth.users (
    id,
    aud,
    role,
    email,
    encrypted_password,
    raw_app_meta_data,
    raw_user_meta_data,
    created_at,
    updated_at
)
values
    (
        '10000000-0000-4000-8000-000000000001',
        'authenticated',
        'authenticated',
        'portfolio-owner-a@example.invalid',
        '',
        '{"provider":"email","providers":["email"]}'::jsonb,
        '{}'::jsonb,
        pg_catalog.now(),
        pg_catalog.now()
    ),
    (
        '20000000-0000-4000-8000-000000000002',
        'authenticated',
        'authenticated',
        'portfolio-owner-b@example.invalid',
        '',
        '{"provider":"email","providers":["email"]}'::jsonb,
        '{}'::jsonb,
        pg_catalog.now(),
        pg_catalog.now()
    );

-- auth.users.confirmed_at is generated by the target Supabase stack. The
-- fixture intentionally does not insert a value or add a compatibility column.

set local role authenticated;
select pg_catalog.set_config(
    'request.jwt.claim.sub',
    '10000000-0000-4000-8000-000000000001',
    true
);
select pg_catalog.set_config('request.jwt.claim.role', 'authenticated', true);

select extensions.lives_ok(
    $$select public.create_portfolio('Owner A Portfolio', 'USD', 'UTC')$$,
    'owner A can create an owner-scoped Portfolio through the RPC'
);
select extensions.is(
    (select pg_catalog.count(*) from public.portfolios),
    1::bigint,
    'owner A can read their own Portfolio'
);
select pg_catalog.set_config(
    'portfolio_test.portfolio_id',
    (select id::text from public.portfolios limit 1),
    true
);
select extensions.lives_ok(
    pg_catalog.format(
        'select public.archive_portfolio(%L::uuid)',
        pg_catalog.current_setting('portfolio_test.portfolio_id')
    ),
    'owner A can archive their own Portfolio'
);
select extensions.is(
    (
        select status::text
          from public.portfolios
         where id = pg_catalog.current_setting(
            'portfolio_test.portfolio_id'
         )::uuid
    ),
    'archived'::text,
    'archive changes only the owner-visible Portfolio lifecycle state'
);
select extensions.lives_ok(
    pg_catalog.format(
        'select public.archive_portfolio(%L::uuid)',
        pg_catalog.current_setting('portfolio_test.portfolio_id')
    ),
    'repeated archive is idempotent'
);

reset role;
set local role authenticated;
select pg_catalog.set_config(
    'request.jwt.claim.sub',
    '20000000-0000-4000-8000-000000000002',
    true
);
select extensions.is(
    (select pg_catalog.count(*) from public.portfolios),
    0::bigint,
    'owner B cannot read owner A Portfolio rows'
);
select extensions.throws_ok(
    pg_catalog.format(
        'select public.archive_portfolio(%L::uuid)',
        pg_catalog.current_setting('portfolio_test.portfolio_id')
    ),
    'P0001',
    'portfolio_not_found',
    'owner B cannot mutate owner A Portfolio through an RPC'
);
select extensions.throws_ok(
    $$
        insert into public.portfolios (owner_id, name)
        values (
            '20000000-0000-4000-8000-000000000002',
            'Forbidden direct insert'
        )
    $$,
    '42501',
    'permission denied for table portfolios',
    'authenticated cannot directly insert even an own Portfolio row'
);

reset role;
set local role anon;
select pg_catalog.set_config('request.jwt.claim.sub', '', true);
select pg_catalog.set_config('request.jwt.claim.role', 'anon', true);
select extensions.throws_ok(
    $$select * from public.portfolios$$,
    '42501',
    'permission denied for table portfolios',
    'anon direct SQL SELECT is denied without table privilege'
);
select extensions.throws_ok(
    $$select public.create_portfolio('Anon Portfolio', 'USD', 'UTC')$$,
    '42501',
    'permission denied for function create_portfolio',
    'anon cannot execute create_portfolio'
);

reset role;
set local role authenticated;
select pg_catalog.set_config('request.jwt.claim.sub', '', true);
select pg_catalog.set_config('request.jwt.claim.role', 'authenticated', true);
select extensions.throws_ok(
    $$select public.create_portfolio('Missing identity', 'USD', 'UTC')$$,
    'P0001',
    'auth_required',
    'authenticated role without a verified auth identity is rejected'
);

select pg_catalog.set_config(
    'request.jwt.claim.sub',
    '10000000-0000-4000-8000-000000000001',
    true
);
select pg_catalog.set_config('request.jwt.claim.role', 'authenticated', true);
select extensions.throws_ok(
    pg_catalog.format(
        $sql$
            insert into public.portfolio_holdings (
                owner_id,
                portfolio_id,
                ticker,
                quantity,
                average_cost,
                version
            )
            values (
                '10000000-0000-4000-8000-000000000001',
                %L::uuid,
                'VOO',
                1,
                100,
                1
            )
        $sql$,
        pg_catalog.current_setting('portfolio_test.portfolio_id')
    ),
    '42501',
    'permission denied for table portfolio_holdings',
    '016 exposes no authenticated Holding write path'
);
select extensions.lives_ok(
    pg_catalog.format(
        'select public.restore_portfolio(%L::uuid)',
        pg_catalog.current_setting('portfolio_test.portfolio_id')
    ),
    'owner A can restore their own Portfolio'
);
select extensions.is(
    (
        select status::text
          from public.portfolios
         where id = pg_catalog.current_setting(
            'portfolio_test.portfolio_id'
         )::uuid
    ),
    'active'::text,
    'restore returns the owner Portfolio to active'
);
select extensions.is(
    (select pg_catalog.count(*) from public.portfolio_holdings),
    0::bigint,
    '016 lifecycle RPCs never create Holding rows'
);

reset role;

select * from extensions.finish();

rollback;
