# 一键推送到 GitHub
# 用法：在本目录执行  .\push_to_github.ps1 -RepoUrl https://github.com/你的用户名/仓库名.git
param(
  [Parameter(Mandatory = $true)][string]$RepoUrl,
  [string]$Email = ""
)
$ErrorActionPreference = 'Stop'
$git = "C:\Users\28385\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\cmd\git.exe"
$proj = $PSScriptRoot
Set-Location $proj

if ($Email) {
  & $git config user.email $Email
  & $git commit --amend --reset-author --no-edit | Out-Null
  Write-Host "已更新提交作者邮箱：$Email" -ForegroundColor Green
}

$hasRemote = (& $git remote) -contains 'origin'
if ($hasRemote) { & $git remote set-url origin $RepoUrl } else { & $git remote add origin $RepoUrl }
Write-Host "远程仓库：$RepoUrl" -ForegroundColor Cyan
Write-Host ""
Write-Host "即将推送（首次会弹出浏览器要求登录 GitHub，请授权）..." -ForegroundColor Yellow
& $git push -u origin main
if ($LASTEXITCODE -eq 0) {
  $web = $RepoUrl -replace '\.git$',''
  Write-Host ""
  Write-Host "  [成功] 已推送到 $web" -ForegroundColor Green
  Write-Host "  下一步：仓库 Settings → Pages → Source 选 main /(root) → Save，即可获得在线展示页" -ForegroundColor Gray
} else {
  Write-Host "  [失败] 请把上面的英文错误信息发给 Codex" -ForegroundColor Red
}