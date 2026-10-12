# 启动智维交互式演示（在线诊断演示）
# 用法：右键"使用 PowerShell 运行"，或在本目录执行 .\start_demo.ps1
$ErrorActionPreference = 'Stop'
$py = "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe"
if (-not (Test-Path $py)) { $py = 'python' }
Set-Location $PSScriptRoot
Write-Host ''
Write-Host '  智维 ZHIWEI · 在线诊断演示' -ForegroundColor Cyan
Write-Host '  启动后请在浏览器打开： http://127.0.0.1:8801/' -ForegroundColor Yellow
Write-Host '  前提：Agnes Harness (AGH) 服务已在运行（另一个窗口）' -ForegroundColor DarkGray
Write-Host '  按 Ctrl+C 停止本服务' -ForegroundColor DarkGray
Write-Host ''
& $py demo_server.py --port 8801