# 生成符合官方命名规则的提交 ZIP
# 命名规则: 组别-参赛编号-队伍名称-队长姓名
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$name = "本科生组-U225-SoloAI Lab-皇甫生昕"
$stage = Join-Path $env:TEMP ("zhiwei-submit-" + [guid]::NewGuid().ToString('N').Substring(0,8))
$zipPath = Join-Path ([Environment]::GetFolderPath('Desktop')) ($name + ".zip")

Write-Host "打包中..." -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $stage | Out-Null
$dst = Join-Path $stage $name
New-Item -ItemType Directory -Force -Path $dst | Out-Null

Get-ChildItem $root -Force | Where-Object {
  $_.Name -notin @("__pycache__", ".git", ".gh") -and $_.Name -notlike "_*"
} | ForEach-Object { Copy-Item $_.FullName -Destination $dst -Recurse -Force }

Get-ChildItem $dst -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
  Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
$uploads = Join-Path $dst "data\uploads"
if (Test-Path $uploads) { Remove-Item $uploads -Recurse -Force }

if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
Compress-Archive -Path $dst -DestinationPath $zipPath -CompressionLevel Optimal
Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue

$size = [math]::Round((Get-Item $zipPath).Length / 1MB, 2)
Write-Host ""
Write-Host ("  [OK] 已生成: " + $zipPath) -ForegroundColor Green
Write-Host ("  大小: " + $size + " MB (官方限制 200MB)") -ForegroundColor Gray
if ($size -gt 200) { Write-Host "  [警告] 超过 200MB，请精简后重新打包" -ForegroundColor Red }