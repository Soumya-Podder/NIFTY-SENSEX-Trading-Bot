param([string]$Tailscale = 'E:\trading_bot_full\.tools\tailscale\installed\tailscale.exe')
$ErrorActionPreference = 'Stop'
# Run after the administrator installs Tailscale and the user signs in.
# This config contains an identity/hostname only, never the Dhan token.
$env:TEMP = 'E:\trading_bot_full\.tmp'
$env:TMP = $env:TEMP
if (-not (Test-Path -LiteralPath $Tailscale)) {
    throw 'Tailscale is not installed at the selected path. Install it and pass -Tailscale with its executable path.'
}
$status = (& $Tailscale status --json | ConvertFrom-Json)
if ($LASTEXITCODE -ne 0 -or $status.BackendState -ne 'Running') {
    throw 'Sign in to Tailscale on the desktop and phone with the same account first.'
}
$hostname = $status.Self.DNSName.TrimEnd('.')
$owner = $status.User.PSObject.Properties[[string]$status.Self.UserID].Value.LoginName
if (-not $hostname.EndsWith('.ts.net') -or -not $owner) {
    throw 'A user-owned Tailscale device and MagicDNS hostname are required.'
}
@{hostname=$hostname;login=$owner} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'token_access.json') -Encoding utf8
# Private Serve only. Never run Funnel or expose the dashboard ports publicly.
& $Tailscale serve --bg --https=443 http://127.0.0.1:8080
if ($LASTEXITCODE -ne 0) { throw 'Serve is not enabled yet. Follow the Tailscale HTTPS setup link and run again.' }
Write-Output "Phone token form: https://$hostname/api/credentials/form"
