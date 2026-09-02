# Portfolio Phase 1A Deployment

This runbook applies the approved Phase 1A database foundation in a fixed order:

1. Apply `supabase/roles.sql` with the migration database identity.
2. Apply `supabase/bootstrap/016_grant_portfolio_auth_privileges.sql` with an identity that has grant options on the `auth` schema and `auth.uid()`.
3. Require every migration from 001 through 015 in database history.
4. Apply migrations through 016 with Supabase CLI.
5. Verify migration 016 and both Phase 1A tables.

The deployment script stops on the first failed command. It uses the integration-tested Supabase CLI version `2.116.0` and does not use a Supabase service-role API key.

## Prerequisites

- Migrations 001 through 015 are already recorded in `supabase_migrations.schema_migrations`.
- The migration identity can create `portfolio_rpc_owner` and receives the PostgreSQL role membership needed by migration 016.
- The privileged bootstrap identity can grant `USAGE` on schema `auth` and `EXECUTE` on `auth.uid()`.
- Node.js/npm can run the pinned package `supabase@2.116.0` through `npx.cmd`.
- Remote mode also requires `psql`.

Do not substitute a Supabase service-role API key for either database identity. Keep connection strings in the operator environment or CI secret store and never commit or deliberately print them.

Remote mode must pass each database URL to native `psql` and Supabase CLI processes because those tools require a connection argument. The script does not log the values, but an operating-system administrator may be able to inspect native process arguments while a command is running. Use an isolated CI runner or controlled operator host, short-lived least-privilege credentials, and rotate credentials after deployment when required by policy.

## Disposable Local Gate

Start a fresh local Supabase workdir with only migrations 001 through 015 applied. Copy migration 016 into that workdir without applying it, then run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\deploy_portfolio_phase1a.ps1 `
  -Workdir 'E:\path\to\disposable-workdir' `
  -DatabaseContainer 'supabase_db_disposable-project-id'
```

Before any database command, the script rejects missing, duplicate, unversioned, or newer-than-016 local migrations. It then explicitly streams `supabase/roles.sql` to `psql` as `postgres`, streams the privileged bootstrap as `supabase_admin`, performs the database-history preflight, and only then runs pinned `supabase@2.116.0 migration up --local`.

After deployment, run the unchanged database and request-path gates:

```powershell
docker cp supabase/tests/016_portfolio_owner_and_holdings_test.sql `
  supabase_db_disposable-project-id:/tmp/016_portfolio_test.sql
docker exec supabase_db_disposable-project-id `
  psql -U postgres -d postgres -X -v ON_ERROR_STOP=1 `
  -f /tmp/016_portfolio_test.sql
python -B -m pytest tests/test_portfolio_phase1a_postgrest.py `
  -q -p no:cacheprovider
```

The pgTAP result must be 40/40. The PostgREST test requires disposable values in the four `PORTFOLIO_TEST_*` environment variables. Never commit or print those values.

## Remote Operator Workflow

Provision both URLs through a protected operator environment or CI secret store:

- `PORTFOLIO_MIGRATION_DB_URL`: standard database migration identity.
- `PORTFOLIO_BOOTSTRAP_DB_URL`: privileged database identity with the required `auth` grant options.

Run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\deploy_portfolio_phase1a.ps1 -Remote
```

The script applies `roles.sql` explicitly before the privileged bootstrap. It creates an isolated temporary Supabase workdir containing exactly migrations 001 through 016, then runs pinned `supabase@2.116.0 db push` without `--include-all` or `--include-roles`. The database preflight has already required all of 001-015, while the isolated workdir contains no 017 or later migration. This prevents the Phase 1A command from applying future migrations or backfilling missing history.

## Failure Handling

- A gap anywhere in migrations 001-015, a local migration newer than 016, a missing or unsafe RPC role, incomplete auth grants, or a failed native command stops the workflow before migration 016.
- Re-running is supported: role creation and auth grants are idempotent, and Supabase skips a recorded migration.
- If bootstrap succeeds but migration fails, fix the migration error and rerun the same command. Do not broaden PUBLIC, service-role, or `auth.users` privileges.
- Phase 1B remains forbidden until this workflow, pgTAP, PostgREST/JWT, and legacy regressions all pass QA.
