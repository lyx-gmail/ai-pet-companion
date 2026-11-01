param([switch]$RunLive)
$ErrorActionPreference='Stop'
if(-not $RunLive){throw 'Use -RunLive to explicitly interrupt and restore the local pet services.'}
. (Join-Path $PSScriptRoot 'service-monitor-data.ps1')
. (Join-Path $PSScriptRoot 'service-control.ps1')
$base=Split-Path -Parent $PSScriptRoot
function Assert($value,$message){if(-not $value){throw $message}}
$evidence=[ordered]@{checkedAt=(Get-Date).ToString('o');allDisconnected=$false;allConnected=$false;
    repeatConnectReusesProcesses=$false;memoryDisconnectPreservesVoice=$false;
    voiceDisconnectPreservesMemory=$false;foreignPortPreserved=$false;restoredOnline=$false}
$sentinel=$null
try {
    [void](Invoke-PetServiceControl $base all disconnect)
    $s=Get-ServiceMonitorSnapshot $base
    Assert (-not $s.Memory.Online -and -not $s.Voice -and -not $s.Ota) 'All disconnect failed'
    $evidence.allDisconnected=$true
    [void](Invoke-PetServiceControl $base all connect)
    $s=Get-ServiceMonitorSnapshot $base
    Assert ($s.Memory.Online -and $s.Voice -and $s.Ota) 'All connect failed'
    $evidence.allConnected=$true
    $before=@(Get-PetServiceProcesses $base memory; Get-PetServiceProcesses $base voice) | Sort-Object ProcessId | ForEach-Object ProcessId
    [void](Invoke-PetServiceControl $base all connect)
    $after=@(Get-PetServiceProcesses $base memory; Get-PetServiceProcesses $base voice) | Sort-Object ProcessId | ForEach-Object ProcessId
    Assert (($before -join ',') -eq ($after -join ',')) 'Repeat connect created another process'
    $evidence.repeatConnectReusesProcesses=$true
    [void](Invoke-PetServiceControl $base memory disconnect)
    $s=Get-ServiceMonitorSnapshot $base
    Assert (-not $s.Memory.Online -and $s.Voice -and $s.Ota) 'Memory disconnect affected voice'
    $evidence.memoryDisconnectPreservesVoice=$true
    [void](Invoke-PetServiceControl $base memory connect)
    [void](Invoke-PetServiceControl $base voice disconnect)
    $s=Get-ServiceMonitorSnapshot $base
    Assert ($s.Memory.Online -and -not $s.Voice -and -not $s.Ota) 'Voice disconnect affected memory'
    $evidence.voiceDisconnectPreservesMemory=$true
    $sentinel=New-Object Net.Sockets.TcpListener([Net.IPAddress]::Loopback,8000)
    $sentinel.Start()
    $refused=$false
    try {[void](Invoke-PetServiceControl $base voice connect)}catch{ $refused=$_.Exception.Message -eq 'PORT_OWNED_BY_OTHER_PROGRAM' }
    Assert ($refused -and $sentinel.Server.IsBound -and @(Get-PetServiceProcesses $base voice).Count -eq 0) 'Foreign listener was not preserved'
    $evidence.foreignPortPreserved=$true
} finally {
    if($sentinel){$sentinel.Stop()}
    [void](Invoke-PetServiceControl $base all connect)
    $s=Get-ServiceMonitorSnapshot $base
    $evidence.restoredOnline=$s.Memory.Online -and $s.Voice -and $s.Ota
    [IO.File]::WriteAllText((Join-Path $base 'evaluation/service-control-check.json'),($evidence|ConvertTo-Json)+"`n",(New-Object Text.UTF8Encoding($false)))
}
Assert $evidence.restoredOnline 'Services were not restored'
$evidence | ConvertTo-Json
