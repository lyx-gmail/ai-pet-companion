param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$voicePython = Join-Path $projectRoot '.tools/voice-venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $voicePython)) {
    & $Python -c "import sys; assert sys.version_info[:2] == (3,12), 'Use Python 3.12 for the pinned Windows voice environment'"
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 required' }
    & $Python -m venv (Join-Path $projectRoot '.tools/voice-venv')
    if ($LASTEXITCODE -ne 0) { throw 'Voice environment creation failed' }
}
& $voicePython -c "import sys; assert sys.version_info[:2] == (3,12), 'Existing voice environment must use Python 3.12'"
if ($LASTEXITCODE -ne 0) { throw 'Existing voice environment version mismatch' }
& $voicePython (Join-Path $PSScriptRoot 'setup-voice-source.py')
if ($LASTEXITCODE -ne 0) { throw 'Pinned voice source unavailable; existing source preserved' }
& $voicePython -m pip install --disable-pip-version-check -r (Join-Path $projectRoot 'backend/locks/voice-requirements-win-py312.txt')
if ($LASTEXITCODE -ne 0) { throw 'Voice dependency installation failed' }
& $voicePython (Join-Path $PSScriptRoot 'setup-voice-native.py')
if ($LASTEXITCODE -ne 0) { throw 'Native audio preparation failed' }
& $voicePython (Join-Path $PSScriptRoot 'check-voice-native.py')
if ($LASTEXITCODE -ne 0) { throw 'Native audio verification failed' }
Write-Output 'Voice runtime prerequisites ready. Speech models, private config and device integration are separate steps.'
