param([string]$Python = 'python', [string]$BuildRoot = 'E:\build\ai-pet')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$lock = Get-Content (Join-Path $projectRoot 'firmware/toolchain-lock.json') -Raw | ConvertFrom-Json
$targets = @(
    @{ Spec = $lock.sdk; Path = (Join-Path $projectRoot '.tools/esp-idf'); Recurse = $true },
    @{ Spec = $lock.firmware; Path = (Join-Path $projectRoot '.tools/upstream/xiaozhi-esp32'); Recurse = $false }
)
foreach ($target in $targets) {
    if (-not (Test-Path -LiteralPath $target.Path)) {
        $cloneArgs = @('-c','http.sslBackend=openssl','clone','--depth','1','--branch',$target.Spec.tag)
        if ($target.Recurse) { $cloneArgs += @('--recurse-submodules','--shallow-submodules') }
        & git @cloneArgs $target.Spec.repository $target.Path
        if ($LASTEXITCODE -ne 0) { throw 'Pinned source clone failed' }
    }
    $head = (& git -c "safe.directory=$($target.Path)" -C $target.Path rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $head -ne $target.Spec.commit) { throw 'Unexpected source version; preserve local work before changing it' }
}
. (Join-Path $PSScriptRoot 'firmware-paths.ps1') -BuildRoot $BuildRoot
$sdk = Join-Path $buildAlias '.tools/esp-idf'
& $Python (Join-Path $sdk 'tools/idf_tools.py') install --targets=esp32s3
if ($LASTEXITCODE -ne 0) { throw 'S3 tool installation failed' }
& $Python (Join-Path $sdk 'tools/idf_tools.py') install-python-env
if ($LASTEXITCODE -ne 0) { throw 'SDK Python environment installation failed' }
Write-Host 'Build tools ready. Run scripts/build-firmware.ps1. This script does not flash devices.'
