$ErrorActionPreference = 'Stop'
$python = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) {
  $systemPython = Get-Command python -ErrorAction SilentlyContinue
  if (-not $systemPython) { throw 'Install Python 3.12 or newer, then run Alpha again.' }
  $version = & $systemPython.Source -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")'
  $parts = $version.Split('.') | ForEach-Object { [int]$_ }
  if ($parts[0] -lt 3 -or ($parts[0] -eq 3 -and $parts[1] -lt 12)) {
    throw 'Project Alpha requires Python 3.12 or newer.'
  }
  Write-Host 'Preparing Alpha once: creating a local environment and installing pinned requirements...' -ForegroundColor Yellow
  & $systemPython.Source -m venv (Join-Path $PSScriptRoot '.venv')
  if ($LASTEXITCODE -ne 0) { throw 'Could not create Alpha virtual environment.' }
  & $python -m pip install -r (Join-Path $PSScriptRoot 'requirements.lock')
  if ($LASTEXITCODE -ne 0) { throw 'Could not install Alpha requirements.' }
}

Push-Location $PSScriptRoot
try {
  & $python -m alpha_app.bootstrap
  if ($LASTEXITCODE -ne 0) { throw 'Project Alpha demo data setup failed.' }
  Write-Host 'Project Alpha is starting at http://127.0.0.1:8000. Press Ctrl+C to stop.' -ForegroundColor Green
  $previousBrowserFlag = $env:ALPHA_OPEN_BROWSER
  $env:ALPHA_OPEN_BROWSER = '1'
  & $python -m uvicorn alpha_app.main:app --host 127.0.0.1 --port 8000
}
finally {
  if ($null -eq $previousBrowserFlag) { Remove-Item Env:ALPHA_OPEN_BROWSER -ErrorAction SilentlyContinue }
  else { $env:ALPHA_OPEN_BROWSER = $previousBrowserFlag }
  Pop-Location
}
