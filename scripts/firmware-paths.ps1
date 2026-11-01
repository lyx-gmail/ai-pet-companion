param([string]$BuildRoot = 'E:\build\ai-pet')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$nativeRoot = [IO.Path]::GetFullPath($BuildRoot)
$tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\','/')
if ($nativeRoot -match '[^\x20-\x7e]' -or
    $nativeRoot.Equals($tempRoot,[StringComparison]::OrdinalIgnoreCase) -or
    $nativeRoot.StartsWith($tempRoot + '\',[StringComparison]::OrdinalIgnoreCase)) {
    throw 'BuildRoot must be an ASCII directory outside TEMP, for example E:\build\ai-pet'
}
# Refuse redirected parents so a seemingly safe path cannot resolve into TEMP.
for ($parent = $nativeRoot; $parent; $parent = Split-Path -Parent $parent) {
    if (Test-Path -LiteralPath $parent) {
        $item = Get-Item -LiteralPath $parent -Force
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw "BuildRoot parents must be real directories: $parent"
        }
    }
}
New-Item -ItemType Directory -Force -Path $nativeRoot | Out-Null
$buildAlias = Join-Path $nativeRoot 'workspace'
if (Test-Path -LiteralPath $buildAlias) {
    $item = Get-Item -LiteralPath $buildAlias -Force
    if ($item.LinkType -ne 'Junction' -or $item.Target -ne $projectRoot) {
        throw 'Unexpected build workspace alias; preserving existing files'
    }
} else {
    New-Item -ItemType Junction -Path $buildAlias -Target $projectRoot | Out-Null
}
$env:IDF_TOOLS_PATH = Join-Path $buildAlias '.tools/espressif'
$env:PYTHONUTF8 = '1'
