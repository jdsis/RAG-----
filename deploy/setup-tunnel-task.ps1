$ErrorActionPreference = "Stop"
$log = "F:\Python\fastApiProject\cf-tunnel.log"
$exe = "C:\Program Files (x86)\cloudflared\cloudflared.exe"

# 清理旧进程
Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force
Remove-Item $log -ErrorAction SilentlyContinue

# 创建常驻计划任务（用户登录时启动，失败自动重启由 bat 循环保证）
$action = New-ScheduledTaskAction -Execute $exe `
    -Argument "tunnel --url http://127.0.0.1:11434 --protocol http2 --no-autoupdate" `
    -WorkingDirectory "F:\Python\fastApiProject"

$trigger = New-ScheduledTaskTrigger -AtLogOn

$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask -TaskName "RAG-Ollama-Tunnel" -Action $action `
    -Trigger $trigger -Settings $settings -Force | Out-Null

Start-ScheduledTask -TaskName "RAG-Ollama-Tunnel"
Write-Output "计划任务已创建并启动"
