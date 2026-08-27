$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$env:PYTHONPATH = Join-Path $ProjectRoot "src"
python -m compileall -q (Join-Path $ProjectRoot "src")
python -m unittest discover -s (Join-Path $ProjectRoot "tests") -v
