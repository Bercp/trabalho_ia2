param([int]$Port = 8000)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonExe = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Não foi possível criar o ambiente Python.' }
    & $pythonExe -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar as dependências.' }
}
if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot '.env'))) {
    Copy-Item -LiteralPath '.env.example' -Destination '.env'
}
if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'data\processed\index.json'))) {
    Write-Host 'Preparando o acervo e baixando o embedder local (apenas na primeira execução)...'
    & $pythonExe -m penal.ingest
    if ($LASTEXITCODE -ne 0) { throw 'Falha na indexação. Verifique o erro acima.' }
}
Write-Host "Abra http://127.0.0.1:$Port no navegador. Ctrl+C encerra o servidor."
& $pythonExe -m uvicorn penal.web:app --host 127.0.0.1 --port $Port
