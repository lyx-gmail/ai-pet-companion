param([switch]$Check, [switch]$SmokeTest)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'service-monitor-data.ps1')
if ($Check) {
    $s=Get-ServiceMonitorSnapshot $root
    # CLI verification intentionally excludes personal memory and raw logs.
    [pscustomobject]@{MemoryOnline=$s.Memory.Online;ModelConfigured=$s.Memory.Model;
        ProfileReadable=($null -ne $s.Memory.Revision);VoiceListening=$s.Voice;OtaListening=$s.Ota;
        TcpConnections=$s.Connections;EventCount=$s.Events.Count;CheckedAt=$s.CheckedAt} | ConvertTo-Json
    exit
}
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[Windows.Forms.Application]::EnableVisualStyles()
$form=New-Object Windows.Forms.Form
$form.Text='AI 宠物 · 服务控制'; $form.ClientSize=New-Object Drawing.Size(840,820)
$form.MinimumSize=New-Object Drawing.Size(800,860); $form.StartPosition='CenterScreen'
$form.Font=New-Object Drawing.Font('Microsoft YaHei UI',10)
$layout=New-Object Windows.Forms.TableLayoutPanel
$layout.Dock='Fill'; $layout.Padding=New-Object Windows.Forms.Padding(20); $layout.ColumnCount=1; $layout.RowCount=9
foreach ($height in @(45,34,92,92,27,152,38,150,40)) {
    [void]$layout.RowStyles.Add((New-Object Windows.Forms.RowStyle([Windows.Forms.SizeType]::Absolute,$height)))
}
$form.Controls.Add($layout)
function Add-Label($text,$size=10) {
    $label=New-Object Windows.Forms.Label
    $label.Text=$text; $label.Dock='Fill'; $label.TextAlign='MiddleLeft'
    $label.Font=New-Object Drawing.Font('Microsoft YaHei UI',$size)
    [void]$layout.Controls.Add($label); return $label
}
$title=Add-Label 'AI 宠物 · 记忆与语音' 20
$note=Add-Label '连接 = 启动服务 · 断开 = 停止服务 · 关闭窗口保持服务运行'
$script:controlButtons=New-Object 'System.Collections.Generic.List[object]'
function Add-StatusBox($name,$service) {
    $box=New-Object Windows.Forms.GroupBox; $box.Text=$name; $box.Dock='Fill'
    $controls=New-Object Windows.Forms.FlowLayoutPanel; $controls.Dock='Right'; $controls.Width=165
    $controls.Padding=New-Object Windows.Forms.Padding(0,10,0,0)
    foreach($item in @(@('连接','connect'),@('断开','disconnect'))) {
        $button=New-Object Windows.Forms.Button; $button.Text=$item[0]; $button.Width=73
        $button.Tag=@{Service=$service;Action=$item[1]}
        $button.Add_Click({param($sender,$eventArgs) Start-Control $sender.Tag.Service $sender.Tag.Action})
        [void]$controls.Controls.Add($button); $script:controlButtons.Add($button)
    }
    $label=New-Object Windows.Forms.Label; $label.Dock='Fill'
    $label.Padding=New-Object Windows.Forms.Padding(12,2,4,3); $label.Text='检测中…'
    $box.Controls.Add($label); $box.Controls.Add($controls); [void]$layout.Controls.Add($box); return $label
}
$memoryLabel=Add-StatusBox '记忆服务' 'memory'
$voiceLabel=Add-StatusBox '语音后端' 'voice'
$profileTitle=Add-Label '当前已确认记忆（仅在本机显示）'
function Add-TextBox {
    $text=New-Object Windows.Forms.TextBox; $text.Multiline=$true; $text.ReadOnly=$true
    $text.ScrollBars='Vertical'; $text.Dock='Fill'; $text.BackColor=[Drawing.Color]::White
    [void]$layout.Controls.Add($text); return $text
}
$profileText=Add-TextBox
$buttons=New-Object Windows.Forms.FlowLayoutPanel; $buttons.Dock='Fill'
[void]$layout.Controls.Add($buttons)
function Add-Button($name,$action,[bool]$control=$false) {
    $button=New-Object Windows.Forms.Button; $button.Text=$name; $button.AutoSize=$true
    $button.Add_Click($action); [void]$buttons.Controls.Add($button)
    if($control){$script:controlButtons.Add($button)}
}
$activity=Add-TextBox
$footer=Add-Label '检测中…'
$script:worker=$null; $script:pending=$null; $script:lastRevision=$null
$script:revisionEvents=New-Object 'System.Collections.Generic.Queue[string]'
$script:controller=$null; $script:controlPending=$null
function Start-Control($service,$action) {
    if($script:controller){return}
    foreach($button in $script:controlButtons){$button.Enabled=$false}
    $note.Text=if($action -eq 'connect'){'正在连接，请稍候…'}else{'正在断开，请稍候…'}
    $script:controller=[PowerShell]::Create()
    [void]$script:controller.AddScript({param($base,$target,$verb)
        . (Join-Path $base 'scripts/service-monitor-data.ps1')
        . (Join-Path $base 'scripts/service-control.ps1')
        try { Invoke-PetServiceControl $base $target $verb }
        catch { Get-PetControlError $_.Exception.Message }
    }).AddArgument($root).AddArgument($service).AddArgument($action)
    $script:controlPending=$script:controller.BeginInvoke()
}
function Start-Probe {
    if ($script:worker) { return }
    $script:worker=[PowerShell]::Create()
    [void]$script:worker.AddScript({param($base)
        . (Join-Path $base 'scripts/service-monitor-data.ps1')
        Get-ServiceMonitorSnapshot $base
    }).AddArgument($root)
    $script:pending=$script:worker.BeginInvoke()
}
Add-Button '全部连接' { Start-Control 'all' 'connect' } $true
Add-Button '全部断开' { Start-Control 'all' 'disconnect' } $true
Add-Button '刷新' { Start-Probe }
Add-Button '打开日志目录' { Start-Process explorer.exe -ArgumentList ('"'+(Join-Path $root '.runtime/voice/logs')+'"') }
Add-Button '使用说明' { Start-Process notepad.exe -ArgumentList ('"'+(Join-Path $root 'docs/服务监控使用说明.md')+'"') }
$timer=New-Object Windows.Forms.Timer; $timer.Interval=200
$script:nextProbe=[DateTime]::MinValue; $script:refreshes=0; $script:smokeClicked=$false; $script:smokeControlPassed=$false
$timer.Add_Tick({
    if($script:controller -and $script:controlPending.IsCompleted){
        try {
            $messages=$script:controller.EndInvoke($script:controlPending)
            $note.Text=if($script:controller.HadErrors -or $messages.Count -ne 1){'操作未完成，请查看日志。'}else{[string]$messages[0]}
            $script:revisionEvents.Enqueue((Get-Date).ToString('HH:mm:ss')+'  '+$note.Text)
            while($script:revisionEvents.Count -gt 5){[void]$script:revisionEvents.Dequeue()}
        } finally {
            $script:controller.Dispose();$script:controller=$null;$script:controlPending=$null
            foreach($button in $script:controlButtons){$button.Enabled=$true}
            $script:nextProbe=[DateTime]::MinValue
        }
    }
    if ($script:worker -and $script:pending.IsCompleted) {
        try {
            $results=$script:worker.EndInvoke($script:pending)
            if ($script:worker.HadErrors -or $results.Count -ne 1) { throw 'PROBE_FAILED' }
            $s=$results[0]
            $memoryLabel.ForeColor=if($s.Memory.Online){[Drawing.Color]::ForestGreen}else{[Drawing.Color]::Firebrick}
            $online=if($s.Memory.Online){'在线'}else{'离线 / 无响应'}
            $model=if($s.Memory.Model){'已配置（未发起付费调用）'}else{'未配置 / 无法确认'}
            $memoryLabel.Text="状态：$online     本机端口：$($s.Port)`r`n模型：$model"
            $voiceLabel.ForeColor=if($s.Voice -and $s.Ota){[Drawing.Color]::ForestGreen}else{[Drawing.Color]::Firebrick}
            $ws=if($s.Voice){'监听中'}else{'未监听'}; $ota=if($s.Ota){'监听中'}else{'未监听'}
            $voiceLabel.Text="语音 8000：$ws     设备接入 8003：$ota     TCP 连接：$($s.Connections)`r`n$($s.VoiceAddress)  ·  端口与连接状态不代表收音和回复已成功"
            $profileText.Text=$s.Memory.ProfileText
            $revision=$s.Memory.Revision
            if ($null -ne $revision) {
                if ($null -ne $script:lastRevision -and $revision -ne $script:lastRevision) {
                    $script:revisionEvents.Enqueue("$($s.CheckedAt)  已确认记忆发生更新：版本 $script:lastRevision → $revision")
                    while ($script:revisionEvents.Count -gt 5) { [void]$script:revisionEvents.Dequeue() }
                }
                $script:lastRevision=$revision
            }
            $events=@($script:revisionEvents.ToArray())+@($s.Events)
            $activity.Text=if($events.Count){$events -join "`r`n"}else{'暂无可显示的活动摘要；等待设备说话或操作。'}
            $footer.Text="最近检测 $($s.CheckedAt) · 日志更新 $($s.LogTime) · 下次自动刷新 2 秒"
            $script:refreshes++
        } catch {
            $memoryLabel.Text='检测失败，正在重试'; $voiceLabel.Text='检测失败，正在重试'
            $profileText.Text='无法读取当前记忆；不展示旧缓存。'
            $footer.Text='本次检测失败，下次刷新重试。'
        } finally {
            $script:worker.Dispose(); $script:worker=$null; $script:pending=$null
            $script:nextProbe=[DateTime]::Now.AddSeconds(2)
        }
    }
    if (-not $script:worker -and [DateTime]::Now -ge $script:nextProbe) { Start-Probe }
    if($SmokeTest -and -not $script:smokeClicked -and $script:refreshes -ge 1){
        $script:smokeClicked=$true
        $script:controlButtons[4].PerformClick()
    }
    if ($SmokeTest -and $script:smokeClicked -and $script:refreshes -ge 2 -and -not $script:controller) {
        $script:smokeControlPassed=$note.Text -match '已连接'
        $bitmap=New-Object Drawing.Bitmap($form.ClientSize.Width,$form.ClientSize.Height)
        $form.DrawToBitmap($bitmap, $form.ClientRectangle)
        $bitmap.Save((Join-Path $root '.runtime/service-monitor-preview.png'))
        $bitmap.Dispose(); $form.Close()
    }
})
$form.Add_FormClosed({
    $timer.Stop()
    if($script:worker){$script:worker.Stop();$script:worker.Dispose()}
    if($script:controller){$script:controller.Stop();$script:controller.Dispose()}
})
$timer.Start()
[void]$form.ShowDialog()
$timer.Dispose(); $form.Dispose()
if($SmokeTest) { if($script:refreshes -lt 2 -or -not $script:smokeControlPassed){throw 'UI refresh or connect button failed'}; 'PASS: window refreshed twice and real connect button completed' }
