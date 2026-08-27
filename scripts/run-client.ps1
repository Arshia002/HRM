param([string]$Server = "https://127.0.0.1:8765")
$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$env:PYTHONPATH = Join-Path $ProjectRoot "src"
python -m sazmanhr.client --server $Server
