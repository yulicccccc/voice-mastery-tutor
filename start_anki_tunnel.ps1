param(
    [string]$Profile = "anki-local",
    [string]$TunnelClientPath = $env:TUNNEL_CLIENT_PATH
)

$ErrorActionPreference = "Stop"

function Resolve-TunnelClient {
    param([string]$ExplicitPath)

    if ($ExplicitPath) {
        $resolved = Resolve-Path -LiteralPath $ExplicitPath -ErrorAction Stop
        return $resolved.Path
    }

    $cmd = Get-Command tunnel-client -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    throw @"
Cannot find tunnel-client.
Either add tunnel-client.exe to PATH or set TUNNEL_CLIENT_PATH for this PowerShell session, for example:
  `$env:TUNNEL_CLIENT_PATH = 'C:\path\to\tunnel-client.exe'
"@
}

function Test-AnkiConnect {
    $payload = @{ action = "version"; version = 6 } | ConvertTo-Json -Compress
    try {
        $response = Invoke-RestMethod \
            -Uri "http://127.0.0.1:8765" \
            -Method Post \
            -ContentType "application/json" \
            -Body $payload \
            -TimeoutSec 5
    }
    catch {
        throw "Cannot reach AnkiConnect at http://127.0.0.1:8765. Open desktop Anki and confirm AnkiConnect is enabled."
    }

    if ($null -ne $response.error -and $response.error -ne "") {
        throw "AnkiConnect returned an error: $($response.error)"
    }

    Write-Host "AnkiConnect OK (API version $($response.result))."
}

function Ensure-RuntimeKey {
    if ($env:CONTROL_PLANE_API_KEY) {
        return
    }

    $secure = Read-Host "Paste CONTROL_PLANE_API_KEY (input is hidden)" -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        $env:CONTROL_PLANE_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
}

$tunnelClient = Resolve-TunnelClient -ExplicitPath $TunnelClientPath
Test-AnkiConnect
Ensure-RuntimeKey

Write-Host "Checking tunnel profile '$Profile'..."
& $tunnelClient doctor --profile $Profile --explain
if ($LASTEXITCODE -ne 0) {
    throw "tunnel-client doctor failed. Fix the reported issue before starting the tunnel."
}

Write-Host "Starting tunnel profile '$Profile'. Keep this window open; press Ctrl+C to stop."
& $tunnelClient run --profile $Profile
exit $LASTEXITCODE
