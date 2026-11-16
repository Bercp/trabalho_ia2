$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
Write-Host 'Configuração local da API. A chave não será exibida nem enviada por este script.'
Write-Host '1 - Google Gemini (interface compatível com Chat Completions)'
Write-Host '2 - Outro provedor compatível com Chat Completions'
$choice = Read-Host 'Escolha 1 ou 2'
if ($choice -eq '1') {
    $apiBase = 'https://generativelanguage.googleapis.com/v1beta/openai'
    Write-Host 'Consulte os modelos disponíveis em https://ai.google.dev/gemini-api/docs/models'
} elseif ($choice -eq '2') {
    $apiBase = Read-Host 'Endpoint base HTTPS (inclua /v1 se exigido pelo provedor)'
} else { throw 'Escolha inválida.' }
$apiModel = Read-Host 'Nome exato do modelo com suporte a tools e saída JSON'
if (-not $apiBase.StartsWith('https://') -or $apiBase -match '[\r\n"\x27]' -or $apiModel -match '[\r\n"\x27]' -or [string]::IsNullOrWhiteSpace($apiModel)) {
    throw 'Endpoint ou nome do modelo inválido.'
}
$secureKey = Read-Host 'Chave da API' -AsSecureString
$keyPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
try {
    $apiKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPtr)
    if ([string]::IsNullOrWhiteSpace($apiKey) -or $apiKey -match '[\r\n"\x27]') { throw 'Chave inválida.' }
    $envPath = Join-Path $PSScriptRoot '.env'
    $text = if (Test-Path -LiteralPath $envPath) { [IO.File]::ReadAllText($envPath) } else { [IO.File]::ReadAllText((Join-Path $PSScriptRoot '.env.example')) }
    $updates = @{ LLM_PROVIDER='openai_compatible'; LLM_BASE_URL=$apiBase.TrimEnd('/'); LLM_MODEL=$apiModel; LLM_API_KEY=$apiKey }
    foreach ($name in $updates.Keys) {
        $pattern = '(?m)^' + [regex]::Escape($name) + '=.*$'
        $replacement = $name + "='" + $updates[$name] + "'"
        if ([regex]::IsMatch($text,$pattern)) { $text = [regex]::Replace($text,$pattern,[System.Text.RegularExpressions.MatchEvaluator]{param($m) $replacement}) }
        else { $text += "`n$replacement`n" }
    }
    [IO.File]::WriteAllText($envPath,$text,[Text.UTF8Encoding]::new($false))
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPtr)
    $apiKey = $null
}
Write-Host 'Configuração salva em .env. Recarregue a página do chat para aplicar.'
