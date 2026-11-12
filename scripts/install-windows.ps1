$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
python -m pip install --user -e .
if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar VMForge.' }
Write-Host 'VMForge instalado. Se vmforge nao estiver no PATH, use: python -m vmforge'
