# Full-stack start for Windows PowerShell.
# Equivalent to scripts/start.sh: generate secrets, then docker compose up.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
}

function Get-RandomHex {
    $bytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    return ([System.BitConverter]::ToString($bytes) -replace "-", "").ToLowerInvariant()
}

function Get-EnvValue([string]$Key) {
    $line = Select-String -Path ".env" -Pattern "^$Key=" | Select-Object -Last 1
    if (-not $line) { return "" }
    return $line.Line.Substring($Key.Length + 1)
}

function Set-EnvValue([string]$Key, [string]$Value) {
    $content = Get-Content ".env" -Raw
    if ($content -match "(?m)^$Key=") {
        $content = [regex]::Replace($content, "(?m)^$Key=.*$", "$Key=$Value")
        Set-Content -Path ".env" -Value $content -NoNewline
    } else {
        Add-Content -Path ".env" -Value "`n$Key=$Value"
    }
}

$atlasKey = Get-EnvValue "ATLAS_API_KEY"
if ([string]::IsNullOrWhiteSpace($atlasKey) -or $atlasKey -eq "change-me") {
    $atlasKey = Get-RandomHex
    Set-EnvValue "ATLAS_API_KEY" $atlasKey
}

$postgresSecret = Get-EnvValue "POSTGRES_PASSWORD"
if ($postgresSecret -eq "postgres") {
    Write-Error @"
Legacy POSTGRES_PASSWORD=postgres detected. AtlasAgent will not rotate an existing
database password automatically. Back up or migrate the database, then set a strong
POSTGRES_PASSWORD and matching DATABASE_URL in .env. For disposable local data, run
scripts/stop.ps1 -CleanVolumes first, then replace postgres with change-me.
"@
}
if ([string]::IsNullOrWhiteSpace($postgresSecret) -or $postgresSecret -eq "change-me") {
    $postgresSecret = Get-RandomHex
    Set-EnvValue "POSTGRES_PASSWORD" $postgresSecret
}

$databaseUrl = Get-EnvValue "DATABASE_URL"
if ([string]::IsNullOrWhiteSpace($databaseUrl) -or $databaseUrl -like "postgresql*" -or $databaseUrl -like "*:change-me@postgres:5432/atlas_agents") {
    Set-EnvValue "DATABASE_URL" "file:/app/data/atlas.db"
}

$build = $env:BUILD -eq "true"
if ($build) {
    docker compose up -d --build --wait --wait-timeout 180
} else {
    docker compose up -d --wait --wait-timeout 180
}

docker compose ps

$gatewayPort = if ($env:NGINX_PORT) { $env:NGINX_PORT } else { "8088" }

Write-Host @"

AtlasAgent is starting.

Gateway:
  http://localhost:$gatewayPort

Useful checks:
  curl http://localhost:$gatewayPort/api/status
  curl -H "X-Atlas-API-Key: $atlasKey" http://localhost:$gatewayPort/api/status/database

Web login API Key:
  $atlasKey
"@
