param(
    [Parameter(Mandatory = $true)][string]$Stage,
    [string]$Tool = "Claude"
)

$file = Join-Path (Split-Path $PSScriptRoot -Parent) "PROMPT_HISTORY.md"
$text = Get-Clipboard -Raw

if ([string]::IsNullOrWhiteSpace($text)) {
    Write-Host "Clipboard is empty. Copy your message first." -ForegroundColor Red
    exit 1
}

$existing = Get-Content $file -Raw
$number = ([regex]::Matches($existing, "(?m)^### Prompt \d+")).Count + 1
$logged = Get-Date -Format "yyyy-MM-dd HH:mm"

$entry = "`r`n### Prompt $number | $Stage | $Tool | logged $logged`r`n`r`n" +
         '``````text' + "`r`n" + $text.TrimEnd() + "`r`n" + '``````' + "`r`n"

Add-Content -Path $file -Value $entry -Encoding utf8
Write-Host "Logged prompt $number under '$Stage'." -ForegroundColor Green
