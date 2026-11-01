$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$lock = Get-Content (Join-Path $projectRoot 'backend/upstream-lock.json') -Raw | ConvertFrom-Json
$nodeExe = Join-Path $projectRoot ".tools/node22/node-v$($lock.node)-win-x64/node.exe"
if (-not (Test-Path -LiteralPath $nodeExe)) { throw 'Run scripts/setup-memory.ps1 first' }
& $nodeExe (Join-Path $projectRoot 'backend/memory-server.cjs')
exit $LASTEXITCODE
