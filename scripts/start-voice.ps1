param([string]$BindIp = '127.0.0.1', [switch]$DiagnosticLogging)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot '.tools/voice-venv/Scripts/python.exe'
$nativeBin = Join-Path $projectRoot '.tools/voice-native/bin'
$serverRoot = Join-Path $projectRoot '.tools/upstream/xiaozhi-esp32-server/main/xiaozhi-server'
if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Run scripts/setup-voice.ps1 first' }
$prepareArgs = @((Join-Path $PSScriptRoot 'prepare-voice.py'), '--bind-ip', $BindIp)
if ($DiagnosticLogging) { $prepareArgs += '--diagnostic-logging' }
& $pythonExe @prepareArgs
if ($LASTEXITCODE -ne 0) { throw 'Voice configuration check failed; no server started' }
$previousPath = $env:PATH
$entry = @'
import asyncio
import os
import sys
with os.add_dll_directory(sys.argv[1]):
    import app
    asyncio.run(app.main())
'@
try {
    $env:PATH = $nativeBin + [IO.Path]::PathSeparator + $previousPath
    Push-Location -LiteralPath $serverRoot
    try {
        & $pythonExe -c $entry $nativeBin
        $voiceExitCode = $LASTEXITCODE
    } finally { Pop-Location }
} finally { $env:PATH = $previousPath }
exit $voiceExitCode
