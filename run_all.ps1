# 智维 ZHIWEI · 一键复现全部验收
# 用法：在项目根目录执行  .\run_all.ps1
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot

function Find-Python {
  $cands = @(
    "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe"
  )
  foreach ($c in $cands) { if (Test-Path $c) { return $c } }
  $cmd = Get-Command python -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  throw "未找到 Python，请先安装 Python 3.11+"
}

$py = Find-Python
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'

Write-Host ""
Write-Host "  智维 ZHIWEI · 一键复现验收" -ForegroundColor Cyan
Write-Host "  赛事编号 U225 / 本科生组 / SoloAI Lab" -ForegroundColor DarkGray
Write-Host ""

$steps = @(
  @{ name = "Day2 故障诊断准确率"; script = "validate_pipeline.py";    dir = "tools" },
  @{ name = "Day3 完整闭环";       script = "validate_closed_loop.py"; dir = "tools" },
  @{ name = "Day4 异常恢复";       script = "validate_day4.py";        dir = "tools" },
  @{ name = "Day5 三测试案例";     script = "run_demo_cases.py";       dir = "tools" }
)

$failed = 0
foreach ($s in $steps) {
  Write-Host (">> " + $s.name) -ForegroundColor Yellow
  Push-Location (Join-Path $root $s.dir)
  & $py $s.script 2>&1 | Select-Object -Last 3 | ForEach-Object { Write-Host ("    " + $_) }
  if ($LASTEXITCODE -ne 0) { $failed++; Write-Host "    [未通过]" -ForegroundColor Red }
  Pop-Location
}

Write-Host ""
Write-Host ">> 生成展示页 app/zhiwei-demo.html" -ForegroundColor Yellow
Push-Location (Join-Path $root "tools")
& $py build_demo_page.py 2>&1 | ForEach-Object { Write-Host ("    " + $_) }
Pop-Location

Write-Host ""
Write-Host ">> MCP 工具自检（需已配置 Agnes Key，可选）" -ForegroundColor Yellow
Write-Host "   在 agent\mcp 目录执行: python verify_mcp_client.py" -ForegroundColor DarkGray

Write-Host ""
if ($failed -eq 0) {
  Write-Host "  [OK] 全部验收通过" -ForegroundColor Green
  Write-Host "  离线展示页: app\zhiwei-demo.html （双击打开）" -ForegroundColor Green
  Write-Host "  交互式演示: cd app; .\start_demo.ps1  然后打开 http://127.0.0.1:8801/" -ForegroundColor Green
} else {
  Write-Host ("  [FAIL] 有 " + $failed + " 项未通过，请查看上面的输出") -ForegroundColor Red
  exit 1
}