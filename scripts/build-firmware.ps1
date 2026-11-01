param([switch]$ConfigureOnly, [string]$BuildRoot = 'E:\build\ai-pet')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'firmware-paths.ps1') -BuildRoot $BuildRoot
# idf.py resolves junctions; GNU ld then fails on the resulting Chinese library
# paths. Build stable copies outside TEMP, retaining the project originals.
& robocopy (Join-Path $projectRoot '.tools/esp-idf') (Join-Path $nativeRoot 'esp-idf') /E /XJ /XD .git __pycache__ /NFL /NDL /NJH /NJS /R:1 /W:1 | Out-Null
if ($LASTEXITCODE -ge 8) { throw 'SDK build-copy failed' }
$env:IDF_PATH = Join-Path $nativeRoot 'esp-idf'
$idfEnv = Get-ChildItem (Join-Path $env:IDF_TOOLS_PATH 'python_env') -Directory | Where-Object Name -Like 'idf5.5_*' | Select-Object -First 1
if (-not $idfEnv) { throw 'Install ESP-IDF v5.5.1 and its Python environment first' }
$env:IDF_PYTHON_ENV_PATH = $idfEnv.FullName
$env:PATH = (Join-Path $idfEnv.FullName 'Scripts') + ';' + $env:PATH
& python (Join-Path $env:IDF_PATH 'tools/idf_tools.py') install --targets=esp32s3
if ($LASTEXITCODE -ne 0) { throw 'ESP32-S3 tool validation failed' }
& (Join-Path $env:IDF_PATH 'export.ps1')
if ($LASTEXITCODE -ne 0) { throw 'ESP-IDF activation failed' }
$source = Join-Path $nativeRoot 'xiaozhi-esp32'
& python (Join-Path $buildAlias 'firmware/prepare.py')
if ($LASTEXITCODE -ne 0) { throw 'Firmware overlay preparation failed' }
& robocopy (Join-Path $projectRoot '.tools/upstream/xiaozhi-esp32') $source /E /XJ /XD .git build __pycache__ /NFL /NDL /NJH /NJS /R:1 /W:1 | Out-Null
if ($LASTEXITCODE -ge 8) { throw 'Firmware build-copy failed' }
Copy-Item -LiteralPath (Join-Path $projectRoot 'firmware/sdkconfig.pet') -Destination (Join-Path $source 'sdkconfig.pet')
$defaults = 'sdkconfig.defaults;sdkconfig.defaults.esp32s3;sdkconfig.pet'
Push-Location $source
try {
    $compiler = Join-Path $env:IDF_TOOLS_PATH 'tools/xtensa-esp-elf/esp-14.2.0_20241119/xtensa-esp-elf/bin/xtensa-esp32s3-elf-g++.exe'
    foreach ($check in @('pet_state_checks.cc','pet_snapshot_checks.cc','pet_timeline_checks.cc','pet_checkpoint_checks.cc','pet_menu_checks.cc','pet_memory_menu_checks.cc','pet_action_checks.cc','pet_sleep_checks.cc','pet_debug_checks.cc','pet_memory_checks.cc','pet_conversation_checks.cc')) {
        & $compiler -std=c++17 -fsyntax-only (Join-Path $buildAlias "firmware/overlay/main/boards/xingzhi-cube-1.54tft-wifi/$check")
        if ($LASTEXITCODE -ne 0) { throw "Pet acceptance assertions failed: $check" }
    }
    # Upstream uses a plain GLOB: rerun CMake so newly added overlay sources
    # participate in linking, including existing incremental build directories.
    $actions = if ($ConfigureOnly) { @('reconfigure') } else { @('reconfigure','build') }
    & python (Join-Path $env:IDF_PATH 'tools/idf.py') --no-ccache -B (Join-Path $nativeRoot 'build') '-DIDF_TARGET=esp32s3' '-DCMAKE_OBJECT_PATH_MAX=128' "-DSDKCONFIG_DEFAULTS=$defaults" @actions
    if ($LASTEXITCODE -ne 0) { throw 'Firmware build/configuration failed; see output' }
    if (-not $ConfigureOnly) {
        $artifacts = Join-Path $projectRoot '.tools/firmware-artifacts'
        New-Item -ItemType Directory -Force -Path $artifacts | Out-Null
        Copy-Item -LiteralPath (Join-Path $nativeRoot 'build/xiaozhi.bin') -Destination (Join-Path $artifacts 'xiaozhi.bin')
    }
} finally { Pop-Location }
