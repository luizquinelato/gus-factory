# =================================================================
# gus.ps1 - CLI global para todos os projetos GUS
# =================================================================
# Source ONCE no seu $PROFILE:
#   . C:\Workspace\gus-factory\helms\gus.ps1
#
# DOCKER      gus dkup      [proj...] | all | all-dev | all-prod
#             gus dkdown    [proj...] | all | all-dev | all-prod  [-v remove volumes]
#             gus dkstart   [proj...] | all | all-dev | all-prod
#             gus dkstop    [proj...] | all | all-dev | all-prod
#             gus dkrestart [proj...] | all | all-dev | all-prod
#             gus dks       [proj...] | all   -- docker ps filtrado
#             gus dkl       [proj...] | all   -- logs em nova aba
#
# MIGRATIONS  gus dbm  [proj...] | all  -- aplica pendentes
#             gus dbmv {proj} <ver>     -- aplica ate versao
#             gus dbmc {proj} <nome>    -- cria migration
#             gus dbs  [proj...] | all  -- status migrations
#             gus dbr  [proj...] | all  -- rollback total
#             gus dbrv {proj} <ver>     -- rollback ate versao
#
# VENVS       gus venvs [proj...] | all  [--force] [--backend] [--auth] [--frontend] [--frontend-etl]
#
# APP         gus rat  [proj...] | all  -- back+auth+front+etl (abas, janela atual)
#             gus ratp [proj...] | all  -- nova janela por projeto
#             gus back|auth|front|etl [proj...] | all
#
# NAV         gus cdb|cdbs|cda|cdf|cde {proj|proj-dev}
#
# Novos projetos em ports.yml funcionam automaticamente.
# =================================================================

$GUS_BLUEPRINT = Split-Path -Parent $PSScriptRoot
$GUS_PORTS_YML = Join-Path $GUS_BLUEPRINT "helms\ports.yml"

# UTF-8 no console e nos subprocessos Python (evita emojis garbled)
# chcp 65001  → code page UTF-8 no nível do Windows (necessário além do [Console]::OutputEncoding)
$null = chcp 65001
$OutputEncoding                    = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding          = [System.Text.Encoding]::UTF8
[Console]::InputEncoding           = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING              = "utf-8"
$env:PYTHONUTF8                    = "1"

# --- Load projects from ports.yml via Python -----------------------
function _gus-projects {
    $portsFile = $GUS_PORTS_YML
    # Write Python to a temp file (more reliable than -c multi-line on Windows)
    $tmpPy = [System.IO.Path]::GetTempFileName() -replace '\.tmp$', '.py'
    @'
import json, sys
try:
    import yaml
    with open(sys.argv[1]) as f:
        data = yaml.safe_load(f)
    out = {}
    for k, v in data.get("projects", {}).items():
        out[k] = {"label": v.get("label", k), "root": v.get("root", ""),
                  "color": v.get("color", "White"),
                  "alias": v.get("alias", k),
                  "prod": v.get("prod", {}), "dev": v.get("dev", {}),
                  "extra_ports": v.get("extra_ports", []),
                  "extra_ports_dev": v.get("extra_ports_dev", [])}
    print(json.dumps(out))
except Exception:
    sys.exit(1)
'@ | Out-File -FilePath $tmpPy -Encoding UTF8
    $json = python $tmpPy $portsFile 2>$null
    $rc   = $LASTEXITCODE
    Remove-Item $tmpPy -ErrorAction SilentlyContinue
    if ($rc -ne 0 -or -not $json) {
        Write-Host "[gus] Erro ao ler ports.yml - verifique Python+PyYAML" -ForegroundColor Red
        return @{}
    }
    $obj = $json | ConvertFrom-Json
    $ht  = @{}
    $obj.PSObject.Properties | ForEach-Object { $ht[$_.Name] = $_.Value }
    return $ht
}

# --- Resolve alias or key → canonical project key -----------------
# Returns $null if not found. Strips no suffix — caller handles -dev.
function _gus-resolve-key {
    param([string]$name, [hashtable]$all)
    if ($all.ContainsKey($name)) { return $name }
    foreach ($k in $all.Keys) {
        if ($all[$k].alias -eq $name) { return $k }
    }
    return $null
}

# --- Resolve arguments → array of {proj, env} ---------------------
# Supports: proj  proj-dev  all  all-dev  all-prod
function _gus-resolve2 {
    param([string[]]$Names, [hashtable]$All)
    $result = [System.Collections.ArrayList]::new()
    if (-not $Names -or $Names.Count -eq 0) {
        Write-Host "[gus] Argumento obrigatorio. Use: all | all-dev | all-prod | {proj} | {proj}-dev" -ForegroundColor Red
        return ,$result
    }
    foreach ($arg in $Names) {
        switch ($arg) {
            'all'      { foreach ($k in ($All.Keys | Sort-Object)) { [void]$result.Add(@{ proj=$k; env='prod' }); [void]$result.Add(@{ proj=$k; env='dev' }) } }
            'all-prod' { foreach ($k in ($All.Keys | Sort-Object)) { [void]$result.Add(@{ proj=$k; env='prod' }) } }
            'all-dev'  { foreach ($k in ($All.Keys | Sort-Object)) { [void]$result.Add(@{ proj=$k; env='dev'  }) } }
            default {
                $p = $arg; $e = 'prod'
                if ($arg -match '^(.+)-dev$') { $p = $Matches[1]; $e = 'dev' }
                $realKey = _gus-resolve-key $p $All
                if ($realKey) { [void]$result.Add(@{ proj=$realKey; env=$e }) }
                else { Write-Host "[gus] '$arg' nao encontrado (disponiveis: $($All.Keys -join ', '))" -ForegroundColor Yellow }
            }
        }
    }
    return ,$result
}

# --- Docker helpers ------------------------------------------------
function _gus-dk-header {
    param([string]$proj, [string]$label, [string]$action)
    $dashes  = [string]::new([char]0x2500, 19)
    $fullbar = [string]::new([char]0x2500, 2 * 19 + 2 + $proj.Length)
    Write-Host ""
    Write-Host ""
    Write-Host "$dashes $proj $dashes" -ForegroundColor Yellow
    Write-Host "[gus/$proj] $label DB — $action" -ForegroundColor Yellow
    Write-Host $fullbar -ForegroundColor Yellow
}

function _gus-docker-up {
    param([string]$proj, [string]$root, [string]$env)
    $compose = if ($env -eq 'dev') { 'docker-compose.db.dev.yml' } else { 'docker-compose.db.yml' }
    $label   = if ($env -eq 'dev') { 'DEV' } else { 'PROD' }
    _gus-dk-header $proj $label 'up'
    if (-not (Test-Path (Join-Path $root $compose))) { Write-Host "[gus/$proj] $compose nao encontrado em $root" -ForegroundColor Yellow; return }
    Push-Location $root; docker compose -f $compose up -d; Pop-Location
}

function _gus-docker-down {
    param([string]$proj, [string]$root, [string]$env, [bool]$removeVolumes = $false)
    $compose = if ($env -eq 'dev') { 'docker-compose.db.dev.yml' } else { 'docker-compose.db.yml' }
    $label   = if ($env -eq 'dev') { 'DEV' } else { 'PROD' }
    $action  = if ($removeVolumes) { 'down -v' } else { 'down' }
    _gus-dk-header $proj $label $action
    if (-not (Test-Path (Join-Path $root $compose))) { Write-Host "[gus/$proj] $compose nao encontrado em $root" -ForegroundColor Yellow; return }
    Push-Location $root
    if ($removeVolumes) { docker compose -f $compose down --volumes }
    else                { docker compose -f $compose down }
    Pop-Location
}

function _gus-docker-simple {
    param([string]$action, [string]$proj, [string]$root, [string]$env)
    $compose = if ($env -eq 'dev') { 'docker-compose.db.dev.yml' } else { 'docker-compose.db.yml' }
    $label   = if ($env -eq 'dev') { 'DEV' } else { 'PROD' }
    _gus-dk-header $proj $label $action
    if (-not (Test-Path (Join-Path $root $compose))) { Write-Host "[gus/$proj] $compose nao encontrado em $root" -ForegroundColor Yellow; return }
    Push-Location $root; docker compose -f $compose $action; Pop-Location
}

# --- List ----------------------------------------------------------
function _gus-list {
    param([hashtable]$projects)
    Write-Host ""
    Write-Host "  Projetos em helms/ports.yml:" -ForegroundColor Cyan
    foreach ($k in ($projects.Keys | Sort-Object)) {
        $p        = $projects[$k]
        $aliasTag = if ($p.alias -and $p.alias -ne $k) { "  (alias: $($p.alias))" } else { "" }
        Write-Host ("    {0,-22}" -f $k) -ForegroundColor $p.color -NoNewline
        Write-Host ("{0,-18}" -f $aliasTag) -ForegroundColor DarkGray -NoNewline
        Write-Host "back:$($p.prod.svc.backend)  front:$($p.prod.svc.frontend)  db:$($p.prod.db.port)  $($p.root)"
    }
    Write-Host ""
}

# --- Docker status / logs ------------------------------------------
function _gus-docker-status {
    param([object[]]$pairs)
    Write-Host ""; Write-Host "  Docker containers:" -ForegroundColor Cyan
    if ($pairs -and $pairs.Count -gt 0) {
        $fa = [System.Collections.ArrayList]::new()
        foreach ($pair in $pairs) { [void]$fa.AddRange(@('--filter', "name=$($pair.proj)")) }
        docker ps --format "table {{.Names}}`t{{.Status}}`t{{.Ports}}" @fa
    } else { docker ps --format "table {{.Names}}`t{{.Status}}`t{{.Ports}}" }
    Write-Host ""
}

function _gus-docker-logs-tab {
    param([object[]]$pairs, [hashtable]$all)
    foreach ($pair in $pairs) {
        $root    = $all[$pair.proj].root
        $compose = if ($pair.env -eq 'dev') { 'docker-compose.db.dev.yml' } else { 'docker-compose.db.yml' }
        $title   = "$($pair.proj)-logs$(if($pair.env -eq 'dev'){'-dev'})"
        $cmd     = "Set-Location '$root'; docker compose -f $compose logs -f"
        $enc     = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($cmd))
        & wt.exe -w 0 new-tab --title $title -- powershell.exe -NoExit -EncodedCommand $enc
    }
}

# --- Navigation (cdb / cdbs / cda / cdf / cde) --------------------
function _gus-cd2 {
    param([string]$dest, [string]$arg, [hashtable]$all)
    $proj = $arg
    if ($arg -match '^(.+)-dev$') { $proj = $Matches[1] }
    $proj = _gus-resolve-key $proj $all
    if (-not $proj) { Write-Host "[gus] '$arg' nao encontrado. Use: gus list" -ForegroundColor Red; return }
    $root = $all[$proj].root
    $target = switch ($dest) {
        'back'  { @("$root\services\backend-service",         "$root\services\backend")         | Where-Object { Test-Path $_ } | Select-Object -First 1 }
        'backs' { @("$root\services\backend-service\scripts", "$root\services\backend\scripts") | Where-Object { Test-Path $_ } | Select-Object -First 1 }
        'auth'  { @("$root\services\auth-service",            "$root\services\auth")            | Where-Object { Test-Path $_ } | Select-Object -First 1 }
        'front' { @("$root\services\frontend-app",            "$root\services\frontend")        | Where-Object { Test-Path $_ } | Select-Object -First 1 }
        'etl'   { @("$root\services\frontend-etl",            "$root\services\etl")             | Where-Object { Test-Path $_ } | Select-Object -First 1 }
        default { $root }
    }
    if ($target -and (Test-Path $target)) { Set-Location $target; Write-Host "[gus/$proj] $target" -ForegroundColor Cyan }
    else { Write-Host "[gus/$proj] Pasta nao encontrada em $root\services\" -ForegroundColor Yellow }
}

# --- DB Migrations -------------------------------------------------
function _gus-db-runner {
    param([string]$proj, [string]$env, [string]$action, [string]$extra, [hashtable]$all)
    if (-not $all.ContainsKey($proj)) {
        Write-Host "[gus] Projeto '$proj' nao encontrado. Use: gus list" -ForegroundColor Red; return
    }
    $p    = $all[$proj]
    $root = $p.root
    $db   = if ($env -eq 'dev') { $p.dev.db } else { $p.prod.db }
    $dbUrl = "postgresql://$($db.user):$($db.pass)@localhost:$($db.port)/$($db.name)"

    # Localiza migration_runner.py (backend-service ou backend)
    $runner = @(
        "$root\services\backend-service\scripts\migration_runner.py",
        "$root\services\backend\scripts\migration_runner.py"
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $runner) {
        Write-Host "[gus/$proj] migration_runner.py nao encontrado em services\backend*\scripts\" -ForegroundColor Red; return
    }

    # Localiza Python (prefere venv do backend)
    $py = @(
        "$root\services\backend-service\.venv\Scripts\python.exe",
        "$root\services\backend\.venv\Scripts\python.exe",
        "$root\services\backend-service\venv\Scripts\python.exe",
        "$root\services\backend\venv\Scripts\python.exe"
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $py) { $py = "python" }

    $label = if ($env -eq 'dev') { 'DEV' } else { 'PROD' }
    $dashes = [string]::new([char]0x2500, 19)
    $fullbar = [string]::new([char]0x2500, 2 * 19 + 2 + $proj.Length)
    Write-Host ""
    Write-Host ""
    Write-Host "$dashes $proj $dashes" -ForegroundColor Yellow
    Write-Host "[gus/$proj] $label DB — $action" -ForegroundColor Yellow
    Write-Host $fullbar -ForegroundColor Yellow
    Push-Location $root
    $env:DATABASE_URL = $dbUrl
    $env:APP_ENV      = $env
    $cfg    = if ($env -eq 'dev') { $p.dev } else { $p.prod }
    $extras = if ($env -eq 'dev') { $p.extra_ports_dev } else { $p.extra_ports }
    _gus-inject-env $cfg $extras
    switch ($action) {
        'apply'         { & $py $runner --apply-all }
        'apply-version' { & $py $runner --apply-to $extra }
        'status'        { & $py $runner --status }
        'create'        { & $py $runner --new $extra }
        'rollback'      {
            if ($extra -eq '0000') { & $py $runner --rollback-to $extra --confirm }
            else                   { & $py $runner --rollback-to $extra }
        }
    }
    Pop-Location
}

# --- venv Setup ----------------------------------------------------
function _gus-venv-runner {
    param([string]$proj, [hashtable]$all, [string[]]$flags)
    if (-not $all.ContainsKey($proj)) {
        Write-Host "[gus] Projeto '$proj' nao encontrado. Use: gus list" -ForegroundColor Red; return
    }
    $root    = $all[$proj].root
    $script  = "$root\scripts\setup_envs.py"
    $dashes  = [string]::new([char]0x2500, 19)
    $fullbar = [string]::new([char]0x2500, 2 * 19 + 2 + $proj.Length)
    Write-Host ""
    Write-Host ""
    Write-Host "$dashes $proj $dashes" -ForegroundColor Yellow
    Write-Host "[gus/$proj] venvs$(if ($flags) { ' ' + ($flags -join ' ') })" -ForegroundColor Yellow
    Write-Host $fullbar -ForegroundColor Yellow
    if (-not (Test-Path $script)) {
        Write-Host "[gus/$proj] scripts\setup_envs.py nao encontrado em $root" -ForegroundColor Red; return
    }
    & python $script @flags
}

# --- Cleanup externos (Qdrant / RabbitMQ) -------------------------
function _gus-cleanup {
    param([string]$kind, [string]$arg, [hashtable]$all)
    $proj = $arg; $denv = 'prod'
    if ($arg -match '^(.+)-dev$') { $proj = $Matches[1]; $denv = 'dev' }
    $proj = _gus-resolve-key $proj $all
    if (-not $proj) { Write-Host "[gus] '$arg' nao encontrado. Use: gus list" -ForegroundColor Red; return }

    $p      = $all[$proj]
    $root   = $p.root
    $extras = if ($denv -eq 'dev') { $p.extra_ports_dev } else { $p.extra_ports }

    $runner = @(
        "$root\services\backend-service\scripts\migration_runner.py",
        "$root\services\backend\scripts\migration_runner.py"
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $runner) { Write-Host "[gus/$proj] migration_runner.py nao encontrado" -ForegroundColor Red; return }

    $py = @(
        "$root\services\backend-service\.venv\Scripts\python.exe",
        "$root\services\backend\.venv\Scripts\python.exe",
        "$root\services\backend-service\venv\Scripts\python.exe",
        "$root\services\backend\venv\Scripts\python.exe"
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $py) { $py = "python" }

    $label   = if ($denv -eq 'dev') { 'DEV' } else { 'PROD' }
    $dashes  = [string]::new([char]0x2500, 19)
    $fullbar = [string]::new([char]0x2500, 2 * 19 + 2 + $proj.Length)
    Write-Host ""
    Write-Host ""
    Write-Host "$dashes $proj $dashes" -ForegroundColor Yellow

    if ($kind -eq 'qdrant') {
        $ep = $extras | Where-Object { $_.name -match '^qdrant(_dev)?$' } | Select-Object -First 1
        if (-not $ep) { Write-Host "[gus/$proj] Qdrant nao configurado em extra_ports" -ForegroundColor Yellow; return }
        $env:QDRANT_URL = "http://localhost:$($ep.port)"
        Write-Host "[gus/$proj] $label Qdrant cleanup :$($ep.port)" -ForegroundColor Yellow
        Write-Host $fullbar -ForegroundColor Yellow
        & $py $runner --qdrant-cleanup --confirm
    } else {
        $amqp = $extras | Where-Object { $_.name -match '^rabbitmq_amqp' } | Select-Object -First 1
        $mgmt = $extras | Where-Object { $_.name -match '^rabbitmq_mgmt' } | Select-Object -First 1
        if (-not $mgmt) { Write-Host "[gus/$proj] RabbitMQ nao configurado em extra_ports" -ForegroundColor Yellow; return }
        $cfg = if ($denv -eq 'dev') { $p.dev } else { $p.prod }
        $env:RABBITMQ_HOST            = "localhost"
        $env:RABBITMQ_PORT            = "$($amqp.port)"
        $env:RABBITMQ_MANAGEMENT_PORT = "$($mgmt.port)"
        $env:RABBITMQ_USER            = if ($cfg.rabbit) { $cfg.rabbit.user  } else { 'guest' }
        $env:RABBITMQ_PASSWORD        = if ($cfg.rabbit) { $cfg.rabbit.pass  } else { 'guest' }
        $env:RABBITMQ_VHOST           = if ($cfg.rabbit) { $cfg.rabbit.vhost } else { '/'     }
        Write-Host "[gus/$proj] $label RabbitMQ cleanup  amqp:$($amqp.port)  mgmt:$($mgmt.port)" -ForegroundColor Yellow
        Write-Host $fullbar -ForegroundColor Yellow
        & $py $runner --rabbit-cleanup --confirm
    }
}

# --- venv activate -------------------------------------------------
function _gus-activate-venv {
    if     (Test-Path ".\.venv\Scripts\Activate.ps1") { .\.venv\Scripts\Activate.ps1 }
    elseif (Test-Path ".\venv\Scripts\Activate.ps1")  { .\venv\Scripts\Activate.ps1  }
}

# --- Inject all env vars from ports.yml (overrides .env files) -----
function _gus-inject-env {
    param([object]$cfg, [object[]]$extras)

    # DB
    $db = $cfg.db
    if ($db) {
        $env:POSTGRES_HOST     = 'localhost'
        $env:POSTGRES_PORT     = [string]$db.port
        $env:POSTGRES_DATABASE = $db.name
        $env:POSTGRES_USER     = $db.user
        $env:POSTGRES_PASSWORD = $db.pass
        if ($db.replica) {
            $env:POSTGRES_REPLICA_HOST = 'localhost'
            $env:POSTGRES_REPLICA_PORT = [string]$db.replica
        } else {
            Remove-Item Env:POSTGRES_REPLICA_HOST -ErrorAction SilentlyContinue
            Remove-Item Env:POSTGRES_REPLICA_PORT -ErrorAction SilentlyContinue
        }
        # Hardening: aliases legacy (plumo-style) + DATABASE_URL completa
        # Protege contra vars stale de sessoes anteriores de dbm/dbr
        $env:DB_HOST      = 'localhost'
        $env:DB_PORT      = [string]$db.port
        $env:DB_NAME      = $db.name
        $env:DB_USER      = $db.user
        $env:DB_PASSWORD  = $db.pass
        $env:DATABASE_URL = "postgresql://$($db.user):$($db.pass)@localhost:$($db.port)/$($db.name)"
    }

    # Service URLs
    $env:BACKEND_SERVICE_URL = "http://localhost:$($cfg.svc.backend)"
    $env:AUTH_SERVICE_URL    = "http://localhost:$($cfg.svc.auth)"
    if ($cfg.svc.frontend)     { $env:FRONTEND_URL     = "http://localhost:$($cfg.svc.frontend)" }
    if ($cfg.svc.etl_frontend) { $env:FRONTEND_ETL_URL = "http://localhost:$($cfg.svc.etl_frontend)" }

    # Redis
    $redis = $extras | Where-Object { $_.name -match '^redis' } | Select-Object -First 1
    if ($redis) {
        $env:REDIS_HOST = 'localhost'
        $env:REDIS_PORT = [string]$redis.port
        $env:REDIS_URL  = "redis://localhost:$($redis.port)/0"
    } else {
        Remove-Item Env:REDIS_HOST -ErrorAction SilentlyContinue
        Remove-Item Env:REDIS_PORT -ErrorAction SilentlyContinue
        Remove-Item Env:REDIS_URL  -ErrorAction SilentlyContinue
    }

    # Qdrant
    $qdrant     = $extras | Where-Object { $_.name -match '^qdrant' -and $_.name -notmatch 'grpc' } | Select-Object -First 1
    $qdrantGrpc = $extras | Where-Object { $_.name -match '^qdrant' -and $_.name -match 'grpc'    } | Select-Object -First 1
    if ($qdrant) {
        $env:QDRANT_HOST = 'localhost'
        $env:QDRANT_PORT = [string]$qdrant.port
        $env:QDRANT_URL  = "http://localhost:$($qdrant.port)"
    } else {
        Remove-Item Env:QDRANT_HOST -ErrorAction SilentlyContinue
        Remove-Item Env:QDRANT_PORT -ErrorAction SilentlyContinue
        Remove-Item Env:QDRANT_URL  -ErrorAction SilentlyContinue
    }
    if ($qdrantGrpc) {
        $env:QDRANT_GRPC_PORT = [string]$qdrantGrpc.port
    } else {
        Remove-Item Env:QDRANT_GRPC_PORT -ErrorAction SilentlyContinue
    }

    # RabbitMQ
    $rabbit     = $extras | Where-Object { $_.name -match '^rabbitmq_amqp' } | Select-Object -First 1
    $rabbitMgmt = $extras | Where-Object { $_.name -match '^rabbitmq_mgmt' } | Select-Object -First 1
    if ($rabbit) {
        $env:RABBITMQ_HOST            = 'localhost'
        $env:RABBITMQ_PORT            = [string]$rabbit.port
        $env:RABBITMQ_USER            = if ($cfg.rabbit) { $cfg.rabbit.user  } else { 'etl_user'     }
        $env:RABBITMQ_PASSWORD        = if ($cfg.rabbit) { $cfg.rabbit.pass  } else { 'etl_password' }
        $env:RABBITMQ_VHOST           = if ($cfg.rabbit) { $cfg.rabbit.vhost } else { 'pulse_etl'    }
    } else {
        Remove-Item Env:RABBITMQ_HOST            -ErrorAction SilentlyContinue
        Remove-Item Env:RABBITMQ_PORT            -ErrorAction SilentlyContinue
        Remove-Item Env:RABBITMQ_USER            -ErrorAction SilentlyContinue
        Remove-Item Env:RABBITMQ_PASSWORD        -ErrorAction SilentlyContinue
        Remove-Item Env:RABBITMQ_VHOST           -ErrorAction SilentlyContinue
    }
    if ($rabbitMgmt) {
        $env:RABBITMQ_MANAGEMENT_PORT = [string]$rabbitMgmt.port
    } else {
        Remove-Item Env:RABBITMQ_MANAGEMENT_PORT -ErrorAction SilentlyContinue
    }
}

# --- Service runner direto (chamado dentro de abas via GUS_DIRECT) -
function _gus-svc-direct {
    param([string]$svc, [string]$proj, [string]$env, [hashtable]$all)
    if (-not $all.ContainsKey($proj)) { Write-Host "[gus] '$proj' nao encontrado. Use: gus list" -ForegroundColor Red; return }
    $p      = $all[$proj]
    $root   = $p.root
    $cfg    = if ($env -eq 'dev') { $p.dev }    else { $p.prod }
    $appEnv = if ($env -eq 'dev') { 'dev' }     else { 'prod' }
    $color  = if ($env -eq 'dev') { 'Yellow' }  else { 'Green' }
    $label  = if ($env -eq 'dev') { 'DEV' }     else { 'PROD' }
    $extras = if ($env -eq 'dev') { $p.extra_ports_dev } else { $p.extra_ports }
    switch ($svc) {
        'back' {
            $port = $cfg.svc.backend
            $dir  = @("$root\services\backend-service", "$root\services\backend") | Where-Object { Test-Path $_ } | Select-Object -First 1
            if (-not $dir) { Write-Host "[gus/$proj] pasta backend nao encontrada" -ForegroundColor Yellow; return }
            Set-Location $dir; Write-Host "[gus/$proj] $label Backend :$port" -ForegroundColor $color
            _gus-activate-venv; $env:APP_ENV = $appEnv
            _gus-inject-env $cfg $extras
            python -m uvicorn app.main:app --reload --port $port
        }
        'auth' {
            $port = $cfg.svc.auth
            $dir  = @("$root\services\auth-service", "$root\services\auth") | Where-Object { Test-Path $_ } | Select-Object -First 1
            if (-not $dir) { Write-Host "[gus/$proj] pasta auth nao encontrada" -ForegroundColor Yellow; return }
            Set-Location $dir; Write-Host "[gus/$proj] $label Auth :$port" -ForegroundColor $color
            _gus-activate-venv; $env:APP_ENV = $appEnv
            _gus-inject-env $cfg $extras
            python -m uvicorn app.main:app --reload --port $port
        }
        'front' {
            $port = $cfg.svc.frontend; $backPort = $cfg.svc.backend
            $dir  = @("$root\services\frontend-app", "$root\services\frontend") | Where-Object { Test-Path $_ } | Select-Object -First 1
            if (-not $dir) { Write-Host "[gus/$proj] pasta frontend nao encontrada" -ForegroundColor Yellow; return }
            Set-Location $dir; Write-Host "[gus/$proj] $label Frontend :$port" -ForegroundColor $color
            $env:VITE_API_URL = "http://localhost:$backPort"; $env:APP_ENV = $appEnv
            npm run dev -- --port $port --mode $appEnv
        }
        'etl' {
            $port = $cfg.svc.etl_frontend
            $dir  = @("$root\services\frontend-etl", "$root\services\etl") | Where-Object { Test-Path $_ } | Select-Object -First 1
            if (-not $dir) { Write-Host "[gus/$proj] pasta etl nao encontrada" -ForegroundColor Yellow; return }
            Set-Location $dir; Write-Host "[gus/$proj] $label ETL :$port" -ForegroundColor $color
            $env:APP_ENV = $appEnv; npm run dev -- --port $port --mode $appEnv
        }
        default { Write-Host "[gus] Servico '$svc' invalido. Use: back | auth | front | etl" -ForegroundColor Red }
    }
}

# --- Abre abas no WT atual (uma aba por tabDef) --------------------
# tabDefs: array de @{ svc='back'; proj='pulse'; env='prod' }
function _gus-open-tabs {
    param([object[]]$tabDefs)
    $gusPsl = Join-Path $GUS_BLUEPRINT "helms\gus.ps1"
    $wtArgs = [System.Collections.ArrayList]::new()
    [void]$wtArgs.AddRange(@('-w', '0'))
    $first = $true
    foreach ($t in $tabDefs) {
        $sfx   = if ($t.env -eq 'dev') { '-dev' } else { '' }
        $title = "$($t.proj)-$($t.svc)$sfx"
        $cmd   = "`$env:GUS_DIRECT='1'; . '$gusPsl'; gus $($t.svc) $($t.proj)$sfx"
        $enc   = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($cmd))
        if (-not $first) { [void]$wtArgs.Add(';') }
        [void]$wtArgs.AddRange(@('new-tab', '--title', $title, '--', 'powershell.exe', '-NoExit', '-EncodedCommand', $enc))
        $first = $false
    }
    & wt.exe @wtArgs
}

# --- Abre nova janela WT por projeto (ratp) -----------------------
function _gus-open-project-window {
    param([string]$proj, [string]$env, [hashtable]$all)
    $p    = $all[$proj]
    $cfg  = if ($env -eq 'dev') { $p.dev } else { $p.prod }
    $svcs = [System.Collections.ArrayList]@('back', 'auth', 'front')
    if ($cfg.svc.etl_frontend) { [void]$svcs.Add('etl') }
    $gusPsl = Join-Path $GUS_BLUEPRINT "helms\gus.ps1"
    $wtArgs = [System.Collections.ArrayList]::new()
    [void]$wtArgs.AddRange(@('-w', 'new'))
    $first = $true
    foreach ($s in $svcs) {
        $sfx   = if ($env -eq 'dev') { '-dev' } else { '' }
        $title = "$proj-$s$sfx"
        $cmd   = "`$env:GUS_DIRECT='1'; . '$gusPsl'; gus $s $proj$sfx"
        $enc   = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($cmd))
        if (-not $first) { [void]$wtArgs.Add(';') }
        [void]$wtArgs.AddRange(@('new-tab', '--title', $title, '--', 'powershell.exe', '-NoExit', '-EncodedCommand', $enc))
        $first = $false
    }
    & wt.exe @wtArgs
    $lbl = if ($env -eq 'dev') { 'DEV' } else { 'PROD' }
    $col = if ($env -eq 'dev') { 'Yellow' } else { 'Green' }
    Write-Host "[gus/$proj] Nova janela $lbl ($($svcs.Count) abas)" -ForegroundColor $col
}

# --- Help ----------------------------------------------------------
function _gus-help {
    param([hashtable]$projects)
    Write-Host ""
    Write-Host "  ============================================================" -ForegroundColor Cyan
    Write-Host "   GUS CLI  --  Workspace Manager" -ForegroundColor Cyan
    Write-Host "  ============================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  Projetos:" -ForegroundColor White
    foreach ($k in ($projects.Keys | Sort-Object)) {
        $p = $projects[$k]
        Write-Host "    * " -NoNewline
        Write-Host ("{0,-22}" -f $k) -ForegroundColor $p.color -NoNewline
        if ($p.alias -and $p.alias -ne $k) { Write-Host "(→ $($p.alias))  " -ForegroundColor DarkGray -NoNewline }
        Write-Host "$($p.label)"
    }
    Write-Host ""
    Write-Host "  DOCKER  (args: proj | proj-dev | all = todos | all-dev = so DEV | all-prod = so PROD)" -ForegroundColor White
    Write-Host "    gus dkup      [proj...]        Cria e sobe containers DB"
    Write-Host "    gus dkdown    [proj...] [-v]   Derruba containers DB  (-v remove volumes tambem)"
    Write-Host "    gus dkstart   [proj...]        Inicia containers existentes"
    Write-Host "    gus dkstop    [proj...]        Para containers (mantém containers criados)"
    Write-Host "    gus dkrestart [proj...]        Reinicia containers existentes"
    Write-Host "    gus dks       [proj...]        docker ps filtrado por projeto"
    Write-Host "    gus dkl       [proj...]        docker logs em nova aba por projeto"
    Write-Host ""
    Write-Host "  MIGRATIONS  (args: proj | proj-dev | all = todos | all-dev = so DEV | all-prod = so PROD)" -ForegroundColor White
    Write-Host "    gus dbm  [proj...]              Aplica migrations pendentes"
    Write-Host "    gus dbmv {proj|proj-dev} <ver>  Aplica ate versao especifica"
    Write-Host "    gus dbmc {proj|proj-dev} <nome> Cria nova migration"
    Write-Host "    gus dbs  [proj...]              Status das migrations"
    Write-Host "    gus dbr  [proj...]              Rollback total (ate 0000)"
    Write-Host "    gus dbrv {proj|proj-dev} <ver>  Rollback ate versao especifica"
    Write-Host ""
    Write-Host "  VENVS  (args: proj... | all = todos)  [sem sufixo dev/prod]" -ForegroundColor White
    Write-Host "    gus venvs [proj...] | all              Instala/atualiza todos os venvs"
    Write-Host "    gus venvs [proj...] --force            Recria venvs do zero"
    Write-Host "    gus venvs [proj...] --backend          Somente backend"
    Write-Host "    gus venvs [proj...] --auth             Somente auth-service"
    Write-Host "    gus venvs [proj...] --frontend         Somente frontend"
    Write-Host "    gus venvs [proj...] --frontend-etl     Somente frontend-etl"
    Write-Host ""
    Write-Host "  APP  (args: proj | proj-dev | all = todos | all-dev = so DEV | all-prod = so PROD)" -ForegroundColor White
    Write-Host "    gus rat  [proj...]   back + auth + front + etl (abas, janela atual)"
    Write-Host "    gus ratp [proj...]   nova janela WT por projeto com todos os servicos"
    Write-Host "    gus back [proj...]   aba do backend"
    Write-Host "    gus auth [proj...]   aba do auth-service"
    Write-Host "    gus front [proj...]  aba do frontend"
    Write-Host "    gus etl  [proj...]   aba do ETL frontend"
    Write-Host ""
    Write-Host "  NAV  (muda diretorio na aba atual)" -ForegroundColor White
    Write-Host "    gus cdb  {proj|proj-dev}   cd para services/backend*"
    Write-Host "    gus cdbs {proj|proj-dev}   cd para services/backend*/scripts"
    Write-Host "    gus cda  {proj|proj-dev}   cd para services/auth*"
    Write-Host "    gus cdf  {proj|proj-dev}   cd para services/frontend*"
    Write-Host "    gus cde  {proj|proj-dev}   cd para services/etl*"
    Write-Host "    gus list                   lista projetos com portas"
    Write-Host ""
    Write-Host "  CLEANUP  (requer Qdrant/RabbitMQ em extra_ports do projeto)" -ForegroundColor White
    Write-Host "    gus qdc  {proj|proj-dev}   Delete todas as Qdrant collections"
    Write-Host "    gus rbc  {proj|proj-dev}   Delete todas as filas RabbitMQ"
    Write-Host ""
    Write-Host "  Exemplos:" -ForegroundColor DarkGray
    Write-Host "    gus dkup pulse plumo             # sobe DB PROD de pulse e plumo"
    Write-Host "    gus dkup all                     # sobe PROD+DEV de todos os projetos"
    Write-Host "    gus dkup all-dev                 # sobe DB DEV de todos os projetos"
    Write-Host "    gus dkup all-prod                # sobe DB PROD de todos os projetos"
    Write-Host "    gus dkdown pulse pulse-dev       # derruba pulse PROD e DEV"
    Write-Host "    gus dkdown pulse -v              # derruba pulse PROD e remove volumes"
    Write-Host "    gus dkdown -v pulse pulse-dev    # -v pode ser em qualquer posicao"
    Write-Host "    gus dkstop all                   # para todos sem remover containers"
    Write-Host "    gus dkstart all                  # inicia containers parados"
    Write-Host "    gus dkrestart pulse-dev          # reinicia pulse DEV"
    Write-Host "    gus dks all                      # status containers de todos"
    Write-Host "    gus dbm all-dev              # migra DEV de todos"
    Write-Host "    gus dbmv pulse-dev 0003      # aplica ate 0003 no pulse DEV"
    Write-Host "    gus dbmc pulse add_audit_log # cria migration no pulse PROD"
    Write-Host "    gus dbrv pulse-dev 0001      # rollback ate 0001 no pulse DEV"
    Write-Host "    gus venvs all                # instala venvs de todos os projetos"
    Write-Host "    gus venvs pulse plumo        # instala venvs de pulse e plumo"
    Write-Host "    gus venvs pulse --backend    # somente backend do pulse"
    Write-Host "    gus venvs all --force        # recria todos os venvs do zero"
    Write-Host "    gus rat pulse-dev            # abre 3 abas pulse DEV"
    Write-Host "    gus ratp saas-blueprint-v1 pulse  # nova janela por projeto"
    Write-Host "    gus back pulse-dev           # aba backend pulse DEV"
    Write-Host "    gus cdb pulse-dev            # cd para backend do pulse DEV"
    Write-Host "    gus cdbs saas-blueprint-v1   # cd para backend/scripts do saas-blueprint-v1"
    Write-Host ""
    Write-Host "  Fonte da verdade: helms/ports.yml" -ForegroundColor DarkGray
    Write-Host ""
}

# --- Main Router ---------------------------------------------------
function gus {
    $all = _gus-projects
    if ($args.Count -eq 0) { _gus-help $all; return }
    $cmd  = $args[0]
    $rest = @($args | Select-Object -Skip 1)

    switch ($cmd) {
        'help' { _gus-help $all }
        'list' { _gus-list $all }

        # ── Docker ────────────────────────────────────────────────────
        'dkup' {
            $pairs = _gus-resolve2 $rest $all
            foreach ($pair in $pairs) { _gus-docker-up $pair.proj $all[$pair.proj].root $pair.env }
        }
        'dkdown' {
            $removeVols = $rest -contains '-v'
            $targets    = @($rest | Where-Object { $_ -ne '-v' })
            $pairs = _gus-resolve2 $targets $all
            foreach ($pair in $pairs) { _gus-docker-down $pair.proj $all[$pair.proj].root $pair.env $removeVols }
        }
        'dkstart' {
            $pairs = _gus-resolve2 $rest $all
            foreach ($pair in $pairs) { _gus-docker-simple 'start' $pair.proj $all[$pair.proj].root $pair.env }
        }
        'dkstop' {
            $pairs = _gus-resolve2 $rest $all
            foreach ($pair in $pairs) { _gus-docker-simple 'stop' $pair.proj $all[$pair.proj].root $pair.env }
        }
        'dkrestart' {
            $pairs = _gus-resolve2 $rest $all
            foreach ($pair in $pairs) { _gus-docker-simple 'restart' $pair.proj $all[$pair.proj].root $pair.env }
        }
        'dks' {
            if ($rest.Count -eq 0) { Write-Host "[gus] Uso: gus dks {proj...} | all | all-dev | all-prod" -ForegroundColor Yellow; return }
            _gus-docker-status (_gus-resolve2 $rest $all)
        }
        'dkl' {
            if ($rest.Count -eq 0) { Write-Host "[gus] Uso: gus dkl {proj...} | all | all-dev | all-prod" -ForegroundColor Yellow; return }
            _gus-docker-logs-tab (_gus-resolve2 $rest $all) $all
        }

        # ── Migrations ────────────────────────────────────────────────
        'dbm' {
            if ($rest.Count -eq 0) { Write-Host "[gus] Uso: gus dbm {proj...} | all | all-dev | all-prod" -ForegroundColor Yellow; return }
            $pairs = _gus-resolve2 $rest $all
            foreach ($pair in $pairs) { _gus-db-runner $pair.proj $pair.env 'apply' '' $all }
        }
        'dbmv' {
            if ($rest.Count -lt 2) { Write-Host "[gus] Uso: gus dbmv {proj|proj-dev} <versao>  ex: gus dbmv pulse-dev 3" -ForegroundColor Yellow; return }
            $p = $rest[0]; $e = 'prod'; if ($p -match '^(.+)-dev$') { $p = $Matches[1]; $e = 'dev' }
            $p = _gus-resolve-key $p $all; if (-not $p) { Write-Host "[gus] '$($rest[0])' nao encontrado. Use: gus list" -ForegroundColor Red; return }
            $ver = ([string]$rest[1]).PadLeft(4, '0')
            _gus-db-runner $p $e 'apply-version' $ver $all
        }
        'dbmc' {
            if ($rest.Count -lt 2) { Write-Host "[gus] Uso: gus dbmc {proj|proj-dev} <nome>  ex: gus dbmc pulse add_audit" -ForegroundColor Yellow; return }
            $p = $rest[0]; $e = 'prod'; if ($p -match '^(.+)-dev$') { $p = $Matches[1]; $e = 'dev' }
            $p = _gus-resolve-key $p $all; if (-not $p) { Write-Host "[gus] '$($rest[0])' nao encontrado. Use: gus list" -ForegroundColor Red; return }
            _gus-db-runner $p $e 'create' $rest[1] $all
        }
        'dbs' {
            if ($rest.Count -eq 0) { Write-Host "[gus] Uso: gus dbs {proj...} | all | all-dev | all-prod" -ForegroundColor Yellow; return }
            $pairs = _gus-resolve2 $rest $all
            foreach ($pair in $pairs) { _gus-db-runner $pair.proj $pair.env 'status' '' $all }
        }
        'dbr' {
            if ($rest.Count -eq 0) { Write-Host "[gus] Uso: gus dbr {proj...} | all | all-dev | all-prod" -ForegroundColor Yellow; return }
            $pairs = _gus-resolve2 $rest $all
            foreach ($pair in $pairs) { _gus-db-runner $pair.proj $pair.env 'rollback' '0000' $all }
        }
        'dbrv' {
            if ($rest.Count -lt 2) { Write-Host "[gus] Uso: gus dbrv {proj|proj-dev} <versao>  ex: gus dbrv pulse 1" -ForegroundColor Yellow; return }
            $p = $rest[0]; $e = 'prod'; if ($p -match '^(.+)-dev$') { $p = $Matches[1]; $e = 'dev' }
            $p = _gus-resolve-key $p $all; if (-not $p) { Write-Host "[gus] '$($rest[0])' nao encontrado. Use: gus list" -ForegroundColor Red; return }
            $ver = ([string]$rest[1]).PadLeft(4, '0')
            _gus-db-runner $p $e 'rollback' $ver $all
        }

        # ── App (tabs) ────────────────────────────────────────────────
        'rat' {
            if ($rest.Count -eq 0) { Write-Host "[gus] Uso: gus rat {proj...} | all | all-dev | all-prod" -ForegroundColor Yellow; return }
            $pairs = _gus-resolve2 $rest $all
            $defs  = [System.Collections.ArrayList]::new()
            foreach ($pair in $pairs) {
                $cfg = if ($pair.env -eq 'dev') { $all[$pair.proj].dev } else { $all[$pair.proj].prod }
                foreach ($s in @('back','auth','front')) { [void]$defs.Add(@{svc=$s;proj=$pair.proj;env=$pair.env}) }
                if ($cfg.svc.etl_frontend) { [void]$defs.Add(@{svc='etl';proj=$pair.proj;env=$pair.env}) }
            }
            _gus-open-tabs $defs
        }
        'ratp' {
            if ($rest.Count -eq 0) { Write-Host "[gus] Uso: gus ratp {proj...} | all | all-dev | all-prod" -ForegroundColor Yellow; return }
            $pairs = _gus-resolve2 $rest $all
            foreach ($pair in $pairs) { _gus-open-project-window $pair.proj $pair.env $all }
        }
        { $_ -in 'back','auth','front','etl' } {
            if ($rest.Count -eq 0) { Write-Host "[gus] Uso: gus $cmd {proj...} | all | all-dev | all-prod" -ForegroundColor Yellow; return }
            if ($env:GUS_DIRECT -eq '1') {
                # Ja dentro de uma aba — executa direto sem abrir mais abas
                $p = $rest[0]; $e = 'prod'; if ($p -match '^(.+)-dev$') { $p = $Matches[1]; $e = 'dev' }
                _gus-svc-direct $cmd $p $e $all
            } else {
                $pairs = _gus-resolve2 $rest $all
                $defs  = @(foreach ($pair in $pairs) { @{svc=$cmd;proj=$pair.proj;env=$pair.env} })
                _gus-open-tabs $defs
            }
        }

        # ── Navegacao ─────────────────────────────────────────────────
        'cdb'  { if ($rest.Count -eq 0) { Write-Host "[gus] Uso: gus cdb  {proj|proj-dev}" -ForegroundColor Yellow; return }; _gus-cd2 'back'  $rest[0] $all }
        'cdbs' { if ($rest.Count -eq 0) { Write-Host "[gus] Uso: gus cdbs {proj|proj-dev}" -ForegroundColor Yellow; return }; _gus-cd2 'backs' $rest[0] $all }
        'cda'  { if ($rest.Count -eq 0) { Write-Host "[gus] Uso: gus cda  {proj|proj-dev}" -ForegroundColor Yellow; return }; _gus-cd2 'auth'  $rest[0] $all }
        'cdf'  { if ($rest.Count -eq 0) { Write-Host "[gus] Uso: gus cdf  {proj|proj-dev}" -ForegroundColor Yellow; return }; _gus-cd2 'front' $rest[0] $all }
        'cde'  { if ($rest.Count -eq 0) { Write-Host "[gus] Uso: gus cde  {proj|proj-dev}" -ForegroundColor Yellow; return }; _gus-cd2 'etl'   $rest[0] $all }

        # ── Venvs ─────────────────────────────────────────────────────
        'venvs' {
            $flags   = @($rest | Where-Object { $_ -like '--*' })
            $targets = @($rest | Where-Object { $_ -notlike '--*' })
            if ($targets.Count -eq 0) {
                Write-Host "[gus] Uso: gus venvs {proj...} | all  [--force] [--backend] [--auth] [--frontend] [--frontend-etl]" -ForegroundColor Yellow; return
            }
            $projList = if ($targets -contains 'all') { $all.Keys | Sort-Object } else {
                $targets | ForEach-Object {
                    $rk = _gus-resolve-key $_ $all
                    if (-not $rk) { Write-Host "[gus] '$_' nao encontrado. Use: gus list" -ForegroundColor Yellow }
                    $rk
                } | Where-Object { $_ }
            }
            foreach ($projName in $projList) { _gus-venv-runner $projName $all $flags }
        }

        # ── Cleanup ───────────────────────────────────────────────────
        'qdc' {
            if ($rest.Count -eq 0) { Write-Host "[gus] Uso: gus qdc {proj|proj-dev}" -ForegroundColor Yellow; return }
            _gus-cleanup 'qdrant' $rest[0] $all
        }
        'rbc' {
            if ($rest.Count -eq 0) { Write-Host "[gus] Uso: gus rbc {proj|proj-dev}" -ForegroundColor Yellow; return }
            _gus-cleanup 'rabbit' $rest[0] $all
        }

        default { Write-Host "[gus] Comando '$cmd' desconhecido. Use: gus help" -ForegroundColor Red }
    }
}
