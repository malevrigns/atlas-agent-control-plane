# Full-stack stop for Windows PowerShell. Equivalent to scripts/stop.sh.

param(
    [switch]$CleanVolumes
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if ($CleanVolumes -or $env:CLEAN_VOLUMES -eq "true") {
    docker compose down -v
} else {
    docker compose down
}
