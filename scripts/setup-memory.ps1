$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$lock = Get-Content (Join-Path $projectRoot 'backend/upstream-lock.json') -Raw | ConvertFrom-Json
$tools = Join-Path $projectRoot '.tools'
$nodeFolder = Join-Path $tools "node22/node-v$($lock.node)-win-x64"
$nodeExe = Join-Path $nodeFolder 'node.exe'
if (-not (Test-Path -LiteralPath $nodeExe)) {
    $zipName = "node-v$($lock.node)-win-x64.zip"
    $downloadFolder = Join-Path $tools 'downloads'
    New-Item -ItemType Directory -Force -Path $downloadFolder | Out-Null
    $zipPath = Join-Path $downloadFolder $zipName
    $base = "https://nodejs.org/dist/v$($lock.node)/"
    Invoke-WebRequest -Uri ($base + $zipName) -OutFile $zipPath
    $checksums = (Invoke-WebRequest -Uri ($base + 'SHASUMS256.txt')).Content
    $expected = (($checksums -split "`n" | Where-Object { $_.Trim().EndsWith($zipName) }) -split '\s+')[0]
    if (-not $expected -or (Get-FileHash -Algorithm SHA256 -LiteralPath $zipPath).Hash.ToLower() -ne $expected) { throw 'Node archive checksum mismatch' }
    Expand-Archive -LiteralPath $zipPath -DestinationPath (Join-Path $tools 'node22') -Force
}
$upstreamRoot = Join-Path $tools 'upstream/MemoryConstellations'
if (-not (Test-Path -LiteralPath (Join-Path $upstreamRoot '.git'))) {
    & git -c http.sslBackend=openssl clone $lock.memory.repository $upstreamRoot
    if ($LASTEXITCODE -ne 0) { throw 'Clone failed' }
}
$head = (& git -C $upstreamRoot rev-parse HEAD).Trim()
if ($head -ne $lock.memory.commit) {
    & git -C $upstreamRoot -c http.sslBackend=openssl fetch origin $lock.memory.commit --depth 1
    if ($LASTEXITCODE -ne 0) { throw 'Pinned commit fetch failed' }
    & git -C $upstreamRoot checkout --detach $lock.memory.commit
    if ($LASTEXITCODE -ne 0) { throw 'Pinned checkout failed; preserve local changes before retrying' }
}
$npm = Join-Path $nodeFolder 'node_modules/npm/bin/npm-cli.js'
$installLock = Join-Path $projectRoot 'backend/locks/memory-package-lock.json'
if (Test-Path -LiteralPath $installLock) { Copy-Item -LiteralPath $installLock -Destination (Join-Path $upstreamRoot 'package-lock.json') }
Push-Location $upstreamRoot
try {
    if (Test-Path -LiteralPath 'package-lock.json') { $installCommand = 'ci' } else { $installCommand = 'install' }
    & $nodeExe $npm $installCommand --ignore-scripts --no-audit --no-fund --registry=https://registry.npmjs.org --cache=(Join-Path $tools 'npm-cache')
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
    Push-Location 'node_modules/better-sqlite3'
    try {
        & $nodeExe '../prebuild-install/bin.js'
        if ($LASTEXITCODE -ne 0) { throw 'SQLite native binary unavailable; do not silently use a different runtime' }
    } finally { Pop-Location }
} finally { Pop-Location }
& $nodeExe (Join-Path $PSScriptRoot 'init-private.cjs')
if ($LASTEXITCODE -ne 0) { throw 'Private configuration initialization failed' }
Write-Host 'Ready. Fill PET_LLM_BASE_URL, PET_LLM_MODEL and PET_LLM_API_KEY in .env locally.'
