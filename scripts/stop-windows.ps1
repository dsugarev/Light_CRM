# Stop the CRM. Data (database volume, backups) is kept.
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
docker compose down
