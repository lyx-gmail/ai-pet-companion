$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'service-monitor-data.ps1')
function Assert($condition, $message) { if (-not $condition) { throw $message } }
$settings = Read-MonitorSettings "PET_API_TOKEN='$('a' * 64)'`nPET_PORT=8766"
Assert ($settings.Port -eq 8766 -and $settings.Token.Length -eq 64) 'Private settings parsing failed'
Assert ((Read-MonitorSettings 'PET_PORT=http://example.org').Port -eq 8766) 'Port must stay numeric and local'
$raw = "2026-10-31 12:00:01 [INFO] 大模型收到用户消息: sk-secret-private`n2026-10-31 12:00:02 [ERROR] private-password"
$safe = @(ConvertTo-MonitorEvents $raw)
Assert ($safe.Count -eq 2) 'Expected voice and error summaries'
Assert (($safe -join '') -notmatch 'sk-secret|private-password') 'Raw log content leaked'
Assert (($safe -join '') -match '回复|请求') 'Missing useful voice event'
$offline = Get-MemoryMonitorStatus $null $null
Assert (-not $offline.Online -and $offline.ProfileText -match '无法读取') 'Offline must not retain old profile'
$online = Get-MemoryMonitorStatus @{ok=$true;llmConfigured=$true} @{revision=3;name='测试伙伴';preferences=@(@{slot='preference0';value='喜欢猫'})}
Assert ($online.Online -and $online.ProfileText -match '测试伙伴' -and $online.Revision -eq 3) 'Confirmed profile not shown'
$unknown = Get-MemoryMonitorStatus @{ok=$true;llmConfigured=$true} $null
Assert ($unknown.Online -and $unknown.ProfileText -match '无法读取') 'Auth failure must not look like empty memory'
'PASS: settings, log redaction, offline, confirmed profile, unavailable profile'
. (Join-Path $PSScriptRoot 'service-control.ps1')
$base=Split-Path -Parent $PSScriptRoot
$node=Join-Path $base '.tools/node22/node-v22.23.4-win-x64/node.exe'
$memory=[pscustomobject]@{Name='node.exe';ExecutablePath=$node;CommandLine='node backend/memory-server.cjs'}
Assert (Test-PetServiceProcess $memory $base 'memory') 'Current memory service must be manageable'
$foreign=[pscustomobject]@{Name='node.exe';ExecutablePath='C:\other\node.exe';CommandLine='node backend/memory-server.cjs'}
Assert (-not(Test-PetServiceProcess $foreign $base 'memory')) 'Foreign node process must never be stopped'
$voice=[pscustomobject]@{Name='python.exe';ExecutablePath='C:\runtime\python.exe';CommandLine=('python -c "asyncio.run(app.main())" "'+(Join-Path $base '.tools/voice-native/bin')+'"')}
Assert (Test-PetServiceProcess $voice $base 'voice') 'Project voice child should be manageable'
$voice.CommandLine='python -c "asyncio.run(app.main())" C:\other\bin'
Assert (-not(Test-PetServiceProcess $voice $base 'voice')) 'Other voice projects must be preserved'
Assert (-not(Test-PetServiceProcess $null $base 'voice')) 'Missing PID cannot prove ownership'
'PASS: service ownership refuses unrelated processes'