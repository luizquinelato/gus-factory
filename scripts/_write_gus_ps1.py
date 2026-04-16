"""
Regenerate helms/gus.ps1 with UTF-8 BOM encoding (required by Windows PS 5.1).

Run this script if gus.ps1 is ever corrupted or needs to be updated.
The output file is self-contained and reads helms/ports.yml at runtime.
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT  = os.path.join(ROOT, "helms", "gus.ps1")

CONTENT = r"""# =================================================================
# gus.ps1 - CLI global para todos os projetos GUS
# =================================================================
# Source ONCE no seu $PROFILE:
#   . C:\Workspace\gus-factory\helms\gus.ps1
#
# Uso:
#   gus help                         -- ajuda e lista de projetos
#   gus list                         -- projetos com portas
#   gus dkup   [proj...]             -- Docker up   PROD
#   gus dkdown [proj...]             -- Docker down PROD
#   gus dkup-dev   [proj...]         -- Docker up   DEV
#   gus dkdown-dev [proj...]         -- Docker down DEV
#   gus status [proj...]             -- docker ps filtrado
#   gus logs   {proj} [svc]          -- docker logs -f
#   gus cd     {proj} [back|front|auth]  -- navegar para pasta
#   gus run    {svc} {proj|proj-dev} -- rodar servico (sufixo -dev = ambiente dev)
#
# Novos projetos registrados em ports.yml funcionam automaticamente.
# =================================================================

$GUS_BLUEPRINT = Split-Path -Parent $PSScriptRoot
$GUS_PORTS_YML = Join-Path $GUS_BLUEPRINT "helms\ports.yml"

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
                  "prod": v.get("prod", {}), "dev": v.get("dev", {})}
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
function _gus-resolve-key {
    param([string]$name, [hashtable]$all)
    if ($all.ContainsKey($name)) { return $name }
    foreach ($k in $all.Keys) {
        if ($all[$k].alias -eq $name) { return $k }
    }
    return $null
}

# --- Resolve which projects to operate on --------------------------
function _gus-resolve {
    param([string[]]$Names, [hashtable]$All)
    if (-not $Names -or $Names.Count -eq 0) { return @($All.Keys | Sort-Object) }
    $valid = @()
    foreach ($n in $Names) {
        $rk = _gus-resolve-key $n $All
        if ($rk) { $valid += $rk }
        else { Write-Host "[gus] '$n' nao encontrado (disponiveis: $($All.Keys -join ', '))" -ForegroundColor Yellow }
    }
    return $valid
}

# --- Docker up/down ------------------------------------------------
function _gus-docker-up {
    param([string]$proj, [string]$root, [string]$env)
    $compose = if ($env -eq 'dev') { 'docker-compose.db.dev.yml' } else { 'docker-compose.db.yml' }
    $file    = Join-Path $root $compose
    if (-not (Test-Path $file)) { Write-Host "[gus/$proj] $compose nao encontrado em $root" -ForegroundColor Yellow; return }
    Push-Location $root; docker compose -f $compose up -d; Pop-Location
    Write-Host "[gus/$proj] $(if($env-eq'dev'){'DEV'}else{'PROD'}) DB up" -ForegroundColor Green
}

function _gus-docker-down {
    param([string]$proj, [string]$root, [string]$env)
    $compose = if ($env -eq 'dev') { 'docker-compose.db.dev.yml' } else { 'docker-compose.db.yml' }
    $file    = Join-Path $root $compose
    if (-not (Test-Path $file)) { Write-Host "[gus/$proj] $compose nao encontrado em $root" -ForegroundColor Yellow; return }
    Push-Location $root; docker compose -f $compose down; Pop-Location
    Write-Host "[gus/$proj] $(if($env-eq'dev'){'DEV'}else{'PROD'}) DB stopped" -ForegroundColor Red
}

# --- List ----------------------------------------------------------
function _gus-list {
    param([hashtable]$projects)
    Write-Host ""
    Write-Host "  Projetos em helms/ports.yml:" -ForegroundColor Cyan
    foreach ($k in ($projects.Keys | Sort-Object)) {
        $p = $projects[$k]
        Write-Host ("    {0,-12} back:{1}  front:{2}  db:{3}  {4}" -f $k, $p.prod.svc.backend, $p.prod.svc.frontend, $p.prod.db.port, $p.root) -ForegroundColor $p.color
    }
    Write-Host ""
}

# --- Status --------------------------------------------------------
function _gus-status {
    param([string[]]$selected)
    Write-Host ""; Write-Host "  Docker containers ativos:" -ForegroundColor Cyan
    if ($selected -and $selected.Count -gt 0) {
        $fa = @(); foreach ($s in $selected) { $fa += "--filter"; $fa += "name=$s" }
        docker ps --format "table {{.Names}}`t{{.Status}}`t{{.Ports}}" @fa
    } else {
        docker ps --format "table {{.Names}}`t{{.Status}}`t{{.Ports}}"
    }
    Write-Host ""
}

# --- CD ------------------------------------------------------------
function _gus-cd {
    param([string]$proj, [string]$sub, [hashtable]$projects)
    if (-not $projects.ContainsKey($proj)) { Write-Host "[gus] '$proj' nao encontrado. Use: gus list" -ForegroundColor Red; return }
    $root   = $projects[$proj].root
    $target = switch -Regex ($sub) {
        '^(back|backend)$'      {
            @("$root\services\backend-service", "$root\services\backend") |
            Where-Object { Test-Path $_ } | Select-Object -First 1
        }
        '^(front|frontend)$'    {
            @("$root\services\frontend-app", "$root\services\frontend") |
            Where-Object { Test-Path $_ } | Select-Object -First 1
        }
        '^(auth|auth-service)$' {
            @("$root\services\auth-service", "$root\services\auth") |
            Where-Object { Test-Path $_ } | Select-Object -First 1
        }
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
    Write-Host "[gus/$proj] $label DB — $action" -ForegroundColor Cyan
    Push-Location $root
    $env:DATABASE_URL = $dbUrl
    switch ($action) {
        'apply'    { & $py $runner --apply-all }
        'status'   { & $py $runner --status }
        'new'      { & $py $runner --new $extra }
        'rollback' {
            if ($extra -eq '0000') { & $py $runner --rollback-to $extra --confirm }
            else                   { & $py $runner --rollback-to $extra }
        }
    }
    Pop-Location
}

# --- Run (self-contained: reads ports.yml, zero dependency on profile) ----
function _gus-activate-venv {
    # Tenta .venv primeiro (novo padrao), depois venv (legado)
    if     (Test-Path ".\.venv\Scripts\Activate.ps1") { .\.venv\Scripts\Activate.ps1 }
    elseif (Test-Path ".\venv\Scripts\Activate.ps1")  { .\venv\Scripts\Activate.ps1  }
}

function _gus-run {
    param([string]$svc, [string]$proj, [string]$env, [hashtable]$all)
    if (-not $all.ContainsKey($proj)) {
        Write-Host "[gus] Projeto '$proj' nao encontrado. Use: gus list" -ForegroundColor Red; return
    }
    $p      = $all[$proj]
    $root   = $p.root
    $cfg    = if ($env -eq 'dev') { $p.dev }  else { $p.prod }
    $appEnv = if ($env -eq 'dev') { 'dev' }   else { 'prod' }
    $color  = if ($env -eq 'dev') { 'Yellow' } else { 'Green' }
    $label  = if ($env -eq 'dev') { 'DEV' }   else { 'PROD' }

    switch -Regex ($svc) {
        '^(back|backend)$' {
            $port = $cfg.svc.backend
            $dir  = @("$root\services\backend-service", "$root\services\backend") |
                    Where-Object { Test-Path $_ } | Select-Object -First 1
            if (-not $dir) { Write-Host "[gus/$proj] pasta backend nao encontrada em $root\services\" -ForegroundColor Yellow; return }
            Set-Location $dir
            Write-Host "[gus/$proj] $label Backend :$port" -ForegroundColor $color
            _gus-activate-venv
            $env:APP_ENV = $appEnv
            python -m uvicorn app.main:app --reload --port $port
        }
        '^(auth|auth-service)$' {
            $port = $cfg.svc.auth
            $dir  = @("$root\services\auth-service", "$root\services\auth") |
                    Where-Object { Test-Path $_ } | Select-Object -First 1
            if (-not $dir) { Write-Host "[gus/$proj] pasta auth nao encontrada em $root\services\" -ForegroundColor Yellow; return }
            Set-Location $dir
            Write-Host "[gus/$proj] $label Auth :$port" -ForegroundColor $color
            _gus-activate-venv
            $env:APP_ENV = $appEnv
            python -m uvicorn app.main:app --reload --port $port
        }
        '^(front|frontend)$' {
            $port     = $cfg.svc.frontend
            $backPort = $cfg.svc.backend
            $dir      = @("$root\services\frontend-app", "$root\services\frontend") |
                        Where-Object { Test-Path $_ } | Select-Object -First 1
            if (-not $dir) { Write-Host "[gus/$proj] pasta frontend nao encontrada em $root\services\" -ForegroundColor Yellow; return }
            Set-Location $dir
            Write-Host "[gus/$proj] $label Frontend :$port" -ForegroundColor $color
            $env:VITE_API_URL = "http://localhost:$backPort"
            $env:APP_ENV      = $appEnv
            if ($env -eq 'dev') { npm run dev -- --port $port } else { npm run dev }
        }
        '^rat$' {
            $gusPsl = Join-Path $GUS_BLUEPRINT "helms\gus.ps1"
            $sfx    = if ($env -eq 'dev') { '-dev' } else { '' }
            _gus-docker-up $proj $root $env

            # EncodedCommand elimina quoting hell (PowerShell -> wt -> powershell.exe)
            $encAuth  = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes(". '$gusPsl'; gus auth  $proj$sfx"))
            $encBack  = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes(". '$gusPsl'; gus back  $proj$sfx"))
            $encFront = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes(". '$gusPsl'; gus front $proj$sfx"))

            # Uma unica chamada wt com 3 abas -- ';' como elemento do array e o separador de acao do wt
            $wtArgs = @(
                '-w', '0',
                'new-tab', '--title', "$proj-auth$sfx",  '--', 'powershell.exe', '-NoExit', '-EncodedCommand', $encAuth,  ';',
                'new-tab', '--title', "$proj-back$sfx",  '--', 'powershell.exe', '-NoExit', '-EncodedCommand', $encBack,  ';',
                'new-tab', '--title', "$proj-front$sfx", '--', 'powershell.exe', '-NoExit', '-EncodedCommand', $encFront
            )
            & wt.exe @wtArgs
            Write-Host "[gus/$proj] $label aberto (3 abas)!" -ForegroundColor $color
        }
        default { Write-Host "[gus] Servico '$svc' invalido. Use: back | front | auth | rat" -ForegroundColor Red }
    }
}

# --- Help ----------------------------------------------------------
function _gus-help {
    param([hashtable]$projects)
    Write-Host ""
    Write-Host "  ============================================================" -ForegroundColor Cyan
    Write-Host "   GUS CLI  --  Workspace Manager" -ForegroundColor Cyan
    Write-Host "  ============================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  Projetos disponíveis:" -ForegroundColor White
    foreach ($k in ($projects.Keys | Sort-Object)) {
        $p = $projects[$k]
        Write-Host ("    * {0,-12}" -f $k) -ForegroundColor $p.color -NoNewline
        Write-Host " $($p.label)"
    }
    Write-Host ""
    Write-Host "  Comandos Docker:" -ForegroundColor White
    Write-Host "    gus dkup       [proj...]   Sobe DB PROD  (sem args = todos)"
    Write-Host "    gus dkdown     [proj...]   Derruba DB PROD"
    Write-Host "    gus dkup-dev   [proj...]   Sobe DB DEV"
    Write-Host "    gus dkdown-dev [proj...]   Derruba DB DEV"
    Write-Host "    gus status     [proj...]   docker ps filtrado por projeto"
    Write-Host "    gus logs       {proj} [svc]   docker logs -f"
    Write-Host ""
    Write-Host "  Navegacao e execucao:" -ForegroundColor White
    Write-Host "    gus list                        Lista projetos com portas"
    Write-Host "    gus cd     {proj} [back|front|auth]   cd para pasta"
    Write-Host "    gus run    {svc} {proj|proj-dev}   Roda servico (svc: back|front|auth|rat)"
    Write-Host "    gus back|front|auth|rat {proj|proj-dev}   Atalhos diretos"
    Write-Host "    (gus.ps1 e independente do powershell_profile.ps1)"
    Write-Host ""
    Write-Host "  Banco de dados (migrations):" -ForegroundColor White
    Write-Host "    gus dbm {proj|proj-dev}              Aplica migrations pendentes"
    Write-Host "    gus dbm {proj|proj-dev} status       Status das migrations"
    Write-Host "    gus dbm {proj|proj-dev} new <nome>   Cria nova migration"
    Write-Host "    gus dbs {proj|proj-dev}              Alias para dbm ... status"
    Write-Host "    gus dbr {proj|proj-dev} [versao]     Rollback ate versao  (sem versao = reset total)"
    Write-Host ""
    Write-Host "  Exemplos:" -ForegroundColor DarkGray
    Write-Host "    gus dkup pulse plumo            # sobe DB PROD de pulse e plumo"
    Write-Host "    gus dkup plurus plurus-dev      # sobe PROD e DEV do plurus juntos"
    Write-Host "    gus dkdown                      # derruba todos os DBs PROD"
    Write-Host "    gus dkup-dev plurus             # sobe DB DEV do plurus"
    Write-Host "    gus status                      # todos os containers ativos"
    Write-Host "    gus cd pulse back               # cd para services/backend do pulse"
    Write-Host "    gus run back pulse-dev          # roda backend do pulse em DEV"
    Write-Host "    gus run rat plumo               # sobe tudo do plumo em PROD"
    Write-Host "    gus rat pulse-dev               # atalho: sobe tudo do pulse em DEV"
    Write-Host "    gus back plurus-dev             # atalho: roda backend plurus em DEV"
    Write-Host "    gus logs pulse                  # logs docker PROD do pulse"
    Write-Host "    gus dbm plurus                  # roda migrations PROD do plurus"
    Write-Host "    gus dbm plurus-dev status       # status migrations DEV do plurus"
    Write-Host "    gus dbr plurus 0001             # rollback ao 0001 em PROD"
    Write-Host ""
    Write-Host "  Novos projetos (via create_project.py) funcionam automaticamente." -ForegroundColor DarkGray
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
        'help'         { _gus-help $all }
        'list'         { _gus-list $all }
        'dkup' {
            if (-not $rest -or $rest.Count -eq 0) {
                foreach ($p in ($all.Keys | Sort-Object)) { _gus-docker-up $p $all[$p].root 'prod' }
            } else {
                foreach ($arg in $rest) {
                    $e = 'prod'; $p = $arg
                    if ($arg -match '^(.+)-dev$') { $p = $Matches[1]; $e = 'dev' }
                    if ($all.ContainsKey($p)) { _gus-docker-up $p $all[$p].root $e }
                    else { Write-Host "[gus] '$arg' nao encontrado (disponiveis: $($all.Keys -join ', '))" -ForegroundColor Yellow }
                }
            }
        }
        'dkdown' {
            if (-not $rest -or $rest.Count -eq 0) {
                foreach ($p in ($all.Keys | Sort-Object)) { _gus-docker-down $p $all[$p].root 'prod' }
            } else {
                foreach ($arg in $rest) {
                    $e = 'prod'; $p = $arg
                    if ($arg -match '^(.+)-dev$') { $p = $Matches[1]; $e = 'dev' }
                    if ($all.ContainsKey($p)) { _gus-docker-down $p $all[$p].root $e }
                    else { Write-Host "[gus] '$arg' nao encontrado (disponiveis: $($all.Keys -join ', '))" -ForegroundColor Yellow }
                }
            }
        }
        'dkup-dev' {
            $names = @(foreach ($arg in $rest) { if ($arg -match '^(.+)-dev$') { $Matches[1] } else { $arg } })
            $sel = _gus-resolve $names $all
            foreach ($p in $sel) { _gus-docker-up $p $all[$p].root 'dev' }
        }
        'dkdown-dev' {
            $names = @(foreach ($arg in $rest) { if ($arg -match '^(.+)-dev$') { $Matches[1] } else { $arg } })
            $sel = _gus-resolve $names $all
            foreach ($p in $sel) { _gus-docker-down $p $all[$p].root 'dev' }
        }
        'status'       { _gus-status (_gus-resolve $rest $all) }
        'logs'         {
            if ($rest.Count -eq 0) { Write-Host "[gus] Uso: gus logs {proj} [svc]" -ForegroundColor Yellow; return }
            $proj = $rest[0]; $svc = if ($rest.Count -gt 1) { $rest[1] } else { $null }
            if (-not $all.ContainsKey($proj)) { Write-Host "[gus] '$proj' nao encontrado" -ForegroundColor Red; return }
            Push-Location $all[$proj].root
            if ($svc) { docker compose -f docker-compose.db.yml logs -f $svc } else { docker compose -f docker-compose.db.yml logs -f }
            Pop-Location
        }
        'cd'           {
            if ($rest.Count -eq 0) { Write-Host "[gus] Uso: gus cd {proj} [back|front|auth]" -ForegroundColor Yellow; return }
            _gus-cd $rest[0] (if ($rest.Count -gt 1) { $rest[1] } else { '' }) $all
        }
        'dbm' {
            if ($rest.Count -eq 0) { Write-Host "[gus] Uso: gus dbm {proj|proj-dev} [status|new <nome>]" -ForegroundColor Yellow; return }
            $proj = $rest[0]; $denv = 'prod'
            if ($proj -match '^(.+)-dev$') { $proj = $Matches[1]; $denv = 'dev' }
            $sub  = if ($rest.Count -gt 1) { $rest[1] } else { 'apply' }
            $name = if ($rest.Count -gt 2) { $rest[2] } else { '' }
            switch ($sub) {
                'status' { _gus-db-runner $proj $denv 'status' '' $all }
                'new'    { if (-not $name) { $name = Read-Host "[gus] Nome da migration" }; _gus-db-runner $proj $denv 'new' $name $all }
                default  { _gus-db-runner $proj $denv 'apply' '' $all }
            }
        }
        'dbs' {
            if ($rest.Count -eq 0) { Write-Host "[gus] Uso: gus dbs {proj|proj-dev}" -ForegroundColor Yellow; return }
            $proj = $rest[0]; $denv = 'prod'
            if ($proj -match '^(.+)-dev$') { $proj = $Matches[1]; $denv = 'dev' }
            _gus-db-runner $proj $denv 'status' '' $all
        }
        'dbr' {
            if ($rest.Count -eq 0) { Write-Host "[gus] Uso: gus dbr {proj|proj-dev} [versao]  ex: gus dbr plurus 0001  (sem versao = reset total)" -ForegroundColor Yellow; return }
            $proj = $rest[0]; $denv = 'prod'
            if ($proj -match '^(.+)-dev$') { $proj = $Matches[1]; $denv = 'dev' }
            $ver = if ($rest.Count -gt 1) { $rest[1] } else { '0000' }
            _gus-db-runner $proj $denv 'rollback' $ver $all
        }
        'run'          {
            if ($rest.Count -lt 2) { Write-Host "[gus] Uso: gus run {svc} {proj|proj-dev}" -ForegroundColor Yellow; return }
            $proj = $rest[1]; $env = 'prod'
            if ($proj -match '^(.+)-dev$') { $proj = $Matches[1]; $env = 'dev' }
            _gus-run $rest[0] $proj $env $all
        }
        # --- Atalhos diretos: gus rat|back|front|auth {proj|proj-dev} ---
        { $_ -in 'rat','back','front','auth' } {
            if ($rest.Count -eq 0) { Write-Host "[gus] Uso: gus $cmd {proj}  ou  gus $cmd {proj}-dev" -ForegroundColor Yellow; return }
            $proj = $rest[0]; $env = 'prod'
            if ($proj -match '^(.+)-dev$') { $proj = $Matches[1]; $env = 'dev' }
            _gus-run $cmd $proj $env $all
        }
        default        { Write-Host "[gus] Comando '$cmd' desconhecido. Use: gus help" -ForegroundColor Red }
    }
}
"""

with open(OUT, "w", encoding="utf-8-sig", newline="\n") as f:
    f.write(CONTENT.lstrip("\n"))

print(f"[OK] Written {OUT} ({len(CONTENT)} chars, UTF-8 BOM)")

print("[OK] Done. To load: add the following line to your $PROFILE:")
print(f"     . {OUT}")
