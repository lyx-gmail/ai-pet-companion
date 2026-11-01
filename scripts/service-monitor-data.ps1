function Read-MonitorSettings([string]$Text) {
    $token = ''; $port = 8766
    if ($Text -match '(?m)^\s*PET_API_TOKEN\s*=\s*["'']?([a-fA-F0-9]{64})["'']?\s*(?:#.*)?$') { $token = $Matches[1] }
    if ($Text -match '(?m)^\s*PET_PORT\s*=\s*["'']?(\d{4,5})["'']?\s*(?:#.*)?$') {
        $candidate = [int]$Matches[1]
        if ($candidate -ge 1024 -and $candidate -le 65535) { $port = $candidate }
    }
    @{Token=$token;Port=$port}
}

function Get-MemoryMonitorStatus($Health, $Profile) {
    $result = @{Online=($null -ne $Health -and $Health.ok -eq $true); Model=$false; Revision=$null; ProfileText='无法读取当前记忆；不展示旧缓存。'}
    if (-not $result.Online) { return $result }
    $result.Model = $Health.llmConfigured -eq $true
    if ($null -eq $Profile -or $null -eq $Profile.revision) { return $result }
    $result.Revision = $Profile.revision
    $lines = @("资料版本：$($Profile.revision)")
    if ($Profile.name) { $lines += "称呼：$($Profile.name)" } else { $lines += '称呼：尚未保存' }
    $preferences = @($Profile.preferences | Select-Object -First 4)
    if ($preferences.Count) {
        $i=0; foreach ($item in $preferences) { $i++; $lines += "偏好 $i ：$($item.value)" }
    } else { $lines += '偏好：尚未保存' }
    $result.ProfileText = $lines -join "`r`n"
    $result
}

function ConvertTo-MonitorEvents([string]$Text) {
    foreach ($line in ($Text -split "`n")) {
        $summary = $null
        # Deliberately emit fixed summaries only: logs may contain transcripts and credentials.
        if ($line -match '(?i)\b(ERROR|CRITICAL)\b|Traceback') { $summary = '后端记录了错误；可打开日志目录排查' }
        elseif ($line -match '客户端断开连接|连接资源已释放') { $summary = '设备连接已断开 / 释放' }
        elseif ($line -match '大模型收到用户消息') { $summary = '收到对话请求，开始生成回复' }
        elseif ($line -match '识别结果|识别文本|ASR识别') { $summary = '语音识别产生了文本' }
        elseif ($line -match '发送音频|语音合成|TTS上报线程已启动') { $summary = '语音合成 / 音频处理活动' }
        elseif ($line -match 'MCP.*初始化|MCP.*工具|工具调用') { $summary = '设备工具 / MCP 活动' }
        elseif ($line -match 'WebSocket.*启动|websocket.*listening|启动.*服务') { $summary = '语音服务启动活动' }
        if ($summary) {
            $stamp = '--:--:--'
            if ($line -match '\b(\d{2}:\d{2}:\d{2})\b') { $stamp=$Matches[1] }
            "$stamp  $summary"
        }
    }
}

function Read-MonitorJson([string]$Url, [string]$Token = '') {
    $request = [Net.HttpWebRequest]::Create($Url)
    $request.Proxy = $null; $request.Timeout=900; $request.ReadWriteTimeout=900
    $request.AllowAutoRedirect=$false
    if ($Token) { $request.Headers['Authorization']="Bearer $Token" }
    $response=$null; $reader=$null
    try {
        $response=$request.GetResponse()
        $reader=New-Object IO.StreamReader($response.GetResponseStream(), [Text.Encoding]::UTF8)
        $reader.ReadToEnd() | ConvertFrom-Json
    } catch { return $null }
    finally { if($reader){$reader.Dispose()}; if($response){$response.Dispose()} }
}

function Get-ServiceMonitorSnapshot([string]$Root) {
    $settings=Read-MonitorSettings ([IO.File]::ReadAllText((Join-Path $Root '.env')))
    $health=Read-MonitorJson "http://127.0.0.1:$($settings.Port)/health"
    $profile=$null
    if ($health.ok -and $settings.Token) { $profile=Read-MonitorJson "http://127.0.0.1:$($settings.Port)/api/profile" $settings.Token }
    $memory=Get-MemoryMonitorStatus $health $profile
    $network=[Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties()
    $listeners=@($network.GetActiveTcpListeners())
    $voice=@($listeners | Where-Object Port -eq 8000)
    $ota=@($listeners | Where-Object Port -eq 8003)
    $connections=@($network.GetActiveTcpConnections() | Where-Object {
        $_.LocalEndPoint.Port -eq 8000 -and $_.State -eq [Net.NetworkInformation.TcpState]::Established
    }).Count
    $log=Join-Path $Root '.runtime/voice/logs/server.log'
    $events=@(); $logTime=$null
    if (Test-Path -LiteralPath $log) {
        $stream=$null; $reader=$null
        try {
            $stream=[IO.File]::Open($log, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete)
            $offset=[Math]::Max(0, $stream.Length-65536)
            [void]$stream.Seek($offset, [IO.SeekOrigin]::Begin)
            $reader=New-Object IO.StreamReader($stream, [Text.Encoding]::UTF8)
            if ($offset -gt 0) { [void]$reader.ReadLine() }
            $events=@(ConvertTo-MonitorEvents $reader.ReadToEnd() | Select-Object -Last 14)
            $logTime=(Get-Item -LiteralPath $log).LastWriteTime.ToString('MM-dd HH:mm:ss')
        } catch { $events=@('日志暂时无法读取；下次刷新重试') }
        finally { if($reader){$reader.Dispose()}; if($stream){$stream.Dispose()} }
    }
    [pscustomobject]@{Memory=$memory;Port=$settings.Port;Voice=($voice.Count -gt 0);Ota=($ota.Count -gt 0);
        VoiceAddress=(@($voice | ForEach-Object { $_.ToString() }) -join ', ');
        Connections=$connections;Events=$events;LogTime=$logTime;CheckedAt=(Get-Date).ToString('HH:mm:ss')}
}
