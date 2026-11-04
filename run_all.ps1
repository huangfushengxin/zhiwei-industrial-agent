# Cross-platform validation is implemented in scripts/validate.py.
$ErrorActionPreference = 'Stop'
$runner = Join-Path $PSScriptRoot 'scripts/validate.py'
& python $runner @args
exit $LASTEXITCODE
