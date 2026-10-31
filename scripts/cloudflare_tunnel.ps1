# Expose the local telephony server via a free Cloudflare quick tunnel.
# Requires: winget install Cloudflare.cloudflared

$ErrorActionPreference = "Stop"

$cloudflared = Get-Command cloudflared -ErrorAction SilentlyContinue
if (-not $cloudflared) {
    $defaultPath = "${env:ProgramFiles(x86)}\cloudflared\cloudflared.exe"
    if (Test-Path $defaultPath) {
        $cloudflared = Get-Command $defaultPath
    } else {
        Write-Error "cloudflared not found. Install with: winget install Cloudflare.cloudflared"
    }
}

$port = if ($env:TELEPHONY_PORT) { $env:TELEPHONY_PORT } else { "5000" }
# Use 127.0.0.1 — on Windows, localhost can resolve to IPv6 [::1] and fail to connect.
$target = "http://127.0.0.1:$port"

Write-Host ""
Write-Host "Cloudflare quick tunnel -> $target"
Write-Host "1. Start telephony FIRST and wait for: telephony server ready"
Write-Host "   uv run python -m voice_assistant.apps.telephony"
Write-Host "2. Copy the https://....trycloudflare.com URL below into PUBLIC_BASE_URL in .env"
Write-Host "3. Restart telephony if you changed .env, then point Vobiz Answer URL at https://<host>/answer"
Write-Host "4. Test: https://<host>/health should return {""ok"":true}"
Write-Host ""

& $cloudflared.Source tunnel --url $target
