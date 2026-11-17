# Start the CRM on Windows (Docker Desktop). Run: .\scripts\start-windows.ps1
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error 'Docker is required: https://docs.docker.com/get-docker/'
}

function New-Secret {
    $bytes = New-Object byte[] 24
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    -join ($bytes | ForEach-Object { $_.ToString('x2') })
}

if (-not (Test-Path .env)) {
    (Get-Content .env.example) `
        -replace '^POSTGRES_PASSWORD=.*', "POSTGRES_PASSWORD=$(New-Secret)" `
        -replace '^CRM_MIGRATOR_PASSWORD=.*', "CRM_MIGRATOR_PASSWORD=$(New-Secret)" `
        -replace '^CRM_APP_PASSWORD=.*', "CRM_APP_PASSWORD=$(New-Secret)" |
        Set-Content -Encoding utf8 .env
    Write-Host 'Created .env with generated database passwords.'
}

docker compose up --build --detach
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$envFile = Get-Content .env
$port = (($envFile | Select-String '^CRM_HTTPS_PORT=(.*)').Matches.Groups[1].Value)
$siteHost = (($envFile | Select-String '^CRM_SITE_ADDRESS=(.*)').Matches.Groups[1].Value)
if (-not $port) { $port = '443' }
if (-not $siteHost) { $siteHost = 'localhost' }
$url = if ($port -eq '443') { "https://$siteHost" } else { "https://${siteHost}:$port" }

Write-Host 'Waiting for the CRM to become ready...'
for ($i = 0; $i -lt 90; $i++) {
    curl.exe --silent --fail --insecure "$url/api/health/ready" *> $null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "CRM is running at $url"
        exit 0
    }
    Start-Sleep -Seconds 2
}
Write-Error 'The CRM did not become ready in time. Check: docker compose logs'
