function Test-PetServiceProcess($Process, [string]$Root, [string]$Service) {
    if ($null -eq $Process -or -not $Process.CommandLine -or -not $Process.ExecutablePath) { return $false }
    $command=[string]$Process.CommandLine
    if ($Service -eq 'memory') {
        $nodeRoot=(Join-Path $Root '.tools/node22/')
        return ($Process.Name -eq 'node.exe' -and
            $Process.ExecutablePath.StartsWith($nodeRoot,[StringComparison]::OrdinalIgnoreCase) -and
            $command -match '(?i)(?:^|[\\/\s"''])backend[\\/]memory-server\.cjs(?:[\s"'']|$)')
    }
    if ($Service -eq 'voice') {
        $native=[regex]::Escape((Join-Path $Root '.tools/voice-native/bin'))
        return ($Process.Name -eq 'python.exe' -and
            $command.Contains('asyncio.run(app.main())') -and $command -match ($native+'(?:[\s"'']|$)'))
    }
    return $false
}

function Get-PetServiceProcesses([string]$Root, [string]$Service) {
    $name=if($Service -eq 'memory'){'node.exe'}else{'python.exe'}
    Get-CimInstance Win32_Process -Filter "Name='$name'" | Where-Object { Test-PetServiceProcess $_ $Root $Service }
}

function Assert-PetServicePorts([string]$Root, [string]$Service, [int[]]$Ports) {
    foreach ($listener in @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -in $Ports })) {
        $process=Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)" -ErrorAction SilentlyContinue
        if (-not(Test-PetServiceProcess $process $Root $Service)) { throw 'PORT_OWNED_BY_OTHER_PROGRAM' }
    }
}

function Get-PetVoiceBind([string]$Root) {
    $path=Join-Path $Root '.tools/upstream/xiaozhi-esp32-server/main/xiaozhi-server/data/.config.yaml'
    try { $config=[IO.File]::ReadAllText($path) | ConvertFrom-Json } catch { throw 'VOICE_CONFIG_REQUIRED' }
    if ($config._pet_generated_version -ne 1 -or $config.server.ip -notmatch '^\d{1,3}(\.\d{1,3}){3}$') { throw 'VOICE_CONFIG_REQUIRED' }
    # Keep the explicit existing address. prepare-voice.py revalidates local/RFC1918 binding.
    [string]$config.server.ip
}

function Invoke-PetServiceControl([string]$Root, [ValidateSet('memory','voice','all')][string]$Service,
    [ValidateSet('connect','disconnect')][string]$Action) {
    $gate=New-Object Threading.Mutex($false,'Local\AIPetServiceControl')
    $entered=$false
    try {
        $entered=$gate.WaitOne(0)
        if (-not $entered) { throw 'CONTROL_BUSY' }
        $services=if($Service -eq 'all') {
            if($Action -eq 'connect'){@('memory','voice')}else{@('voice','memory')}
        } else { @($Service) }
        foreach ($target in $services) {
            $settings=Read-MonitorSettings ([IO.File]::ReadAllText((Join-Path $Root '.env')))
            $ports=if($target -eq 'memory'){@([int]$settings.Port)}else{@(8000,8003)}
            $owned=@(Get-PetServiceProcesses $Root $target)
            if ($Action -eq 'disconnect') {
                foreach ($process in ($owned | Sort-Object ProcessId -Descending)) {
                    $fresh=Get-CimInstance Win32_Process -Filter "ProcessId=$($process.ProcessId)" -ErrorAction SilentlyContinue
                    if ($null -eq $fresh) { continue }
                    # A Python launcher may exit just after its child is stopped.
                    # Recheck that transient CIM record; never signal a changed identity.
                    if ($fresh.CreationDate -eq $process.CreationDate -and -not(Test-PetServiceProcess $fresh $Root $target)) {
                        Start-Sleep -Milliseconds 200
                        $fresh=Get-CimInstance Win32_Process -Filter "ProcessId=$($process.ProcessId)" -ErrorAction SilentlyContinue
                        if ($null -eq $fresh) { continue }
                    }
                    if ($fresh.CreationDate -ne $process.CreationDate -or -not(Test-PetServiceProcess $fresh $Root $target)) {
                        throw 'PROCESS_IDENTITY_CHANGED'
                    }
                    Stop-Process -Id $fresh.ProcessId -ErrorAction Stop
                }
                $deadline=[DateTime]::Now.AddSeconds(5)
                do {
                    if (@(Get-PetServiceProcesses $Root $target).Count -eq 0) { break }
                    Start-Sleep -Milliseconds 200
                } while ([DateTime]::Now -lt $deadline)
                if (@(Get-PetServiceProcesses $Root $target).Count) { throw 'STOP_NOT_FINISHED' }
                Assert-PetServicePorts $Root $target $ports
                continue
            }
            Assert-PetServicePorts $Root $target $ports
            if ($owned.Count -eq 0) {
                $entry=if($target -eq 'memory'){'start.ps1'}else{'start-voice.ps1'}
                $arguments='-NoProfile -ExecutionPolicy Bypass -File "'+(Join-Path $Root "scripts/$entry")+'"'
                if ($target -eq 'voice') { $arguments+=' -BindIp '+(Get-PetVoiceBind $Root)+' -DiagnosticLogging' }
                $logs=Join-Path $Root '.runtime/service-control'
                [void][IO.Directory]::CreateDirectory($logs)
                $stamp=(Get-Date).ToString('yyyyMMdd-HHmmss-fff')
                $launched=Start-Process powershell.exe -ArgumentList $arguments -WorkingDirectory $Root -WindowStyle Hidden -PassThru `
                    -RedirectStandardOutput (Join-Path $logs "$target-$stamp.out.log") `
                    -RedirectStandardError (Join-Path $logs "$target-$stamp.err.log")
            }
            $ready=$false; $deadline=[DateTime]::Now.AddSeconds(35)
            do {
                $active=@([Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners() | ForEach-Object Port)
                if (@($ports | Where-Object { $_ -notin $active }).Count -eq 0) {
                    Assert-PetServicePorts $Root $target $ports
                    if ($target -eq 'voice' -or (Read-MonitorJson "http://127.0.0.1:$($settings.Port)/health").ok) { $ready=$true; break }
                }
                Start-Sleep -Milliseconds 400
            } while ([DateTime]::Now -lt $deadline)
            if (-not $ready) { throw 'START_NOT_READY' }
        }
        $name=switch($Service){'all'{'全部服务'}'memory'{'记忆服务'}'voice'{'语音后端'}}
        if($Action -eq 'connect'){ "$name 已连接（本地服务已启动）" }else{ "$name 已断开（本地服务已停止）" }
    } finally { if($entered){$gate.ReleaseMutex()}; $gate.Dispose() }
}

function Get-PetControlError([string]$Code) {
    switch -Regex ($Code) {
        'PORT_OWNED_BY_OTHER_PROGRAM' { '端口被其他程序占用；已保留该程序。'; break }
        'PROCESS_IDENTITY_CHANGED' { '进程归属发生变化，已停止操作。'; break }
        'VOICE_CONFIG_REQUIRED' { '未找到有效语音配置，请先完成局域网配置。'; break }
        'START_NOT_READY' { '服务尚未就绪，请查看日志；再次连接会复用现有进程。'; break }
        'STOP_NOT_FINISHED' { '服务尚未完全停止，请稍后刷新。'; break }
        'CONTROL_BUSY' { '另一项连接操作正在进行，请稍候。'; break }
        default { '操作未完成，请查看本地启动日志。' }
    }
}
