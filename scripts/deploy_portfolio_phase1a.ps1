[CmdletBinding(DefaultParameterSetName = "Local")]
param(
    [Parameter(Mandatory = $true, ParameterSetName = "Local")]
    [string]$Workdir,

    [Parameter(Mandatory = $true, ParameterSetName = "Local")]
    [string]$DatabaseContainer,

    [Parameter(ParameterSetName = "Remote")]
    [switch]$Remote,

    [Parameter(ParameterSetName = "Remote")]
    [string]$MigrationDatabaseUrlEnvironmentVariable = "PORTFOLIO_MIGRATION_DB_URL",

    [Parameter(ParameterSetName = "Remote")]
    [string]$BootstrapDatabaseUrlEnvironmentVariable = "PORTFOLIO_BOOTSTRAP_DB_URL",

    [Parameter(ParameterSetName = "Remote")]
    [string]$PsqlCommand = "psql"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$supabaseCliVersion = "2.116.0"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$migrationsPath = Join-Path $projectRoot "supabase\migrations"
$rolesPath = Join-Path $projectRoot "supabase\roles.sql"
$bootstrapPath = Join-Path $projectRoot "supabase\bootstrap\016_grant_portfolio_auth_privileges.sql"
$migrationPath = Join-Path $projectRoot "supabase\migrations\016_create_portfolio_owner_and_holdings.sql"

foreach ($requiredPath in @($rolesPath, $bootstrapPath, $migrationPath)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "Required Phase 1A deployment file is missing: $requiredPath"
    }
}

function Assert-Phase1AMigrationScope {
    param([string]$MigrationsDirectory)

    if (-not (Test-Path -LiteralPath $MigrationsDirectory -PathType Container)) {
        throw "Phase 1A migrations directory is missing: $MigrationsDirectory"
    }

    $versions = @(
        Get-ChildItem -LiteralPath $MigrationsDirectory -File -Filter "*.sql" |
            ForEach-Object {
                if ($_.Name -notmatch '^(\d+)_') {
                    throw "Unversioned migration is not allowed in Phase 1A: $($_.Name)"
                }
                [int]$Matches[1]
            }
    )

    $newerVersions = @($versions | Where-Object { $_ -gt 16 })
    if ($newerVersions.Count -gt 0) {
        throw "Phase 1A refuses local migrations newer than 016"
    }

    $missingVersions = @(1..16 | Where-Object { $_ -notin $versions })
    if ($missingVersions.Count -gt 0) {
        throw "Phase 1A requires local migrations 001 through 016 without gaps"
    }

    $duplicateVersions = @(
        $versions |
            Group-Object |
            Where-Object { $_.Count -ne 1 }
    )
    if ($duplicateVersions.Count -gt 0) {
        throw "Phase 1A refuses duplicate migration versions"
    }
}

function Assert-SupabaseCliVersion {
    $reportedVersion = & npx.cmd -y "supabase@$supabaseCliVersion" --version
    Assert-LastExitCode "Pinned Supabase CLI version check"
    if ($reportedVersion.Trim() -ne $supabaseCliVersion) {
        throw "Expected Supabase CLI $supabaseCliVersion"
    }
}

$preflightSql = @'
do $portfolio_deployment_preflight$
declare
    v_role pg_catalog.pg_roles%rowtype;
begin
    if pg_catalog.to_regclass('supabase_migrations.schema_migrations') is null then
        raise exception 'Supabase migration history is missing';
    end if;

    if exists (
        select 1
          from pg_catalog.unnest(
            array[
                '001', '002', '003', '004', '005',
                '006', '007', '008', '009', '010',
                '011', '012', '013', '014', '015'
            ]::text[]
          ) as required(version)
         where not exists (
            select 1
              from supabase_migrations.schema_migrations as applied
             where applied.version = required.version
         )
    ) then
        raise exception 'migrations 001 through 015 must be recorded without gaps';
    end if;

    if exists (
        select 1
          from supabase_migrations.schema_migrations
         where version::bigint > 16
    ) then
        raise exception 'Phase 1A refuses a database newer than migration 016';
    end if;

    select *
      into v_role
      from pg_catalog.pg_roles
     where rolname = 'portfolio_rpc_owner';

    if not found then
        raise exception 'portfolio_rpc_owner was not created by supabase/roles.sql';
    end if;

    if v_role.rolcanlogin
       or v_role.rolsuper
       or v_role.rolcreatedb
       or v_role.rolcreaterole
       or v_role.rolinherit
       or v_role.rolreplication
       or v_role.rolbypassrls then
        raise exception 'portfolio_rpc_owner has unsafe role attributes';
    end if;

    if not pg_catalog.has_schema_privilege(
        'portfolio_rpc_owner',
        'auth',
        'USAGE'
    ) or not pg_catalog.has_function_privilege(
        'portfolio_rpc_owner',
        'auth.uid()',
        'EXECUTE'
    ) then
        raise exception 'privileged Portfolio auth bootstrap is incomplete';
    end if;

    if pg_catalog.has_table_privilege(
        'portfolio_rpc_owner',
        'auth.users',
        'SELECT'
    ) then
        raise exception 'portfolio_rpc_owner must not read auth.users';
    end if;
end
$portfolio_deployment_preflight$;
'@

$postcheckSql = @'
do $portfolio_deployment_postcheck$
begin
    if not exists (
        select 1
          from supabase_migrations.schema_migrations
         where version = '016'
    ) then
        raise exception 'migration 016 was not recorded';
    end if;

    if pg_catalog.to_regclass('public.portfolios') is null
       or pg_catalog.to_regclass('public.portfolio_holdings') is null then
        raise exception 'Portfolio Phase 1A tables are missing';
    end if;
end
$portfolio_deployment_postcheck$;
'@

function Assert-LastExitCode {
    param([string]$Operation)

    if ($LASTEXITCODE -ne 0) {
        throw "$Operation failed with exit code $LASTEXITCODE"
    }
}

# Scope checks happen before CLI execution, role creation, grants, or migrations.
Assert-Phase1AMigrationScope $migrationsPath
if ($PSCmdlet.ParameterSetName -eq "Local") {
    $resolvedWorkdir = (Resolve-Path -LiteralPath $Workdir).Path
    Assert-Phase1AMigrationScope (Join-Path $resolvedWorkdir "supabase\migrations")
}
Assert-SupabaseCliVersion

function Invoke-LocalSqlFile {
    param(
        [string]$DatabaseUser,
        [string]$SqlPath,
        [string]$Operation
    )

    Get-Content -Raw -LiteralPath $SqlPath |
        & docker exec -i $DatabaseContainer psql -X -U $DatabaseUser -d postgres -v ON_ERROR_STOP=1
    Assert-LastExitCode $Operation
}

function Invoke-LocalSqlText {
    param(
        [string]$DatabaseUser,
        [string]$SqlText,
        [string]$Operation
    )

    $SqlText |
        & docker exec -i $DatabaseContainer psql -X -U $DatabaseUser -d postgres -v ON_ERROR_STOP=1
    Assert-LastExitCode $Operation
}

function Invoke-RemoteSqlFile {
    param(
        [string]$DatabaseUrl,
        [string]$SqlPath,
        [string]$Operation
    )

    Get-Content -Raw -LiteralPath $SqlPath |
        & $PsqlCommand $DatabaseUrl -X -v ON_ERROR_STOP=1
    Assert-LastExitCode $Operation
}

function Invoke-RemoteSqlText {
    param(
        [string]$DatabaseUrl,
        [string]$SqlText,
        [string]$Operation
    )

    $SqlText |
        & $PsqlCommand $DatabaseUrl -X -v ON_ERROR_STOP=1
    Assert-LastExitCode $Operation
}

if ($PSCmdlet.ParameterSetName -eq "Local") {
    $containerRunning = & docker inspect --format "{{.State.Running}}" $DatabaseContainer
    Assert-LastExitCode "Disposable database container inspection"
    if ($containerRunning.Trim() -ne "true") {
        throw "Disposable database container is not running"
    }

    # roles.sql is applied explicitly; this workflow does not depend on db reset
    # or db push loading custom roles as an undocumented side effect.
    Invoke-LocalSqlFile "postgres" $rolesPath "Portfolio RPC role bootstrap"
    Invoke-LocalSqlFile "supabase_admin" $bootstrapPath "Privileged auth bootstrap"
    Invoke-LocalSqlText "postgres" $preflightSql "Phase 1A deployment preflight"

    & npx.cmd -y "supabase@$supabaseCliVersion" migration up --local --workdir $resolvedWorkdir
    Assert-LastExitCode "Supabase migration 016 application"

    Invoke-LocalSqlText "postgres" $postcheckSql "Phase 1A deployment postcheck"
} else {
    $migrationDatabaseUrl = [Environment]::GetEnvironmentVariable(
        $MigrationDatabaseUrlEnvironmentVariable
    )
    $bootstrapDatabaseUrl = [Environment]::GetEnvironmentVariable(
        $BootstrapDatabaseUrlEnvironmentVariable
    )

    if ([string]::IsNullOrWhiteSpace($migrationDatabaseUrl)) {
        throw "Required environment variable is missing: $MigrationDatabaseUrlEnvironmentVariable"
    }
    if ([string]::IsNullOrWhiteSpace($bootstrapDatabaseUrl)) {
        throw "Required environment variable is missing: $BootstrapDatabaseUrlEnvironmentVariable"
    }

    $stagingRoot = Join-Path (
        [IO.Path]::GetTempPath()
    ) ("market-agent-phase1a-" + [guid]::NewGuid().ToString("N"))

    try {
        New-Item -ItemType Directory -Path $stagingRoot | Out-Null
        & npx.cmd -y "supabase@$supabaseCliVersion" init --workdir $stagingRoot --yes
        Assert-LastExitCode "Isolated Phase 1A migration workdir initialization"

        $stagingMigrations = Join-Path $stagingRoot "supabase\migrations"
        New-Item -ItemType Directory -Path $stagingMigrations -Force | Out-Null
        Get-ChildItem -LiteralPath $migrationsPath -File -Filter "*.sql" |
            Where-Object { $_.Name -match '^(00[1-9]|01[0-6])_' } |
            Copy-Item -Destination $stagingMigrations
        Assert-Phase1AMigrationScope $stagingMigrations

        Invoke-RemoteSqlFile $migrationDatabaseUrl $rolesPath "Portfolio RPC role bootstrap"
        Invoke-RemoteSqlFile $bootstrapDatabaseUrl $bootstrapPath "Privileged auth bootstrap"
        Invoke-RemoteSqlText $migrationDatabaseUrl $preflightSql "Phase 1A deployment preflight"

        # The isolated workdir contains exactly migrations 001 through 016.
        # Complete 001-015 history was verified above, and no include-all
        # behavior is allowed.
        & npx.cmd -y "supabase@$supabaseCliVersion" db push `
            --db-url $migrationDatabaseUrl `
            --workdir $stagingRoot
        Assert-LastExitCode "Supabase migration 016 application"

        Invoke-RemoteSqlText $migrationDatabaseUrl $postcheckSql "Phase 1A deployment postcheck"
    } finally {
        if (Test-Path -LiteralPath $stagingRoot) {
            Remove-Item -LiteralPath $stagingRoot -Recurse -Force
        }
    }
}

Write-Output "Portfolio Phase 1A deployment gate completed."
