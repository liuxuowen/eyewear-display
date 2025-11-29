# ==========================================
# Remote Log Monitor Script (Windows Client)
# ==========================================

$ErrorActionPreference = "Stop"

# --- Configuration ---
$PemPath = "C:/Users/liuxu/Documents/peiqi.pem"
$ServerUser = "root"
$ServerIP = "124.223.217.73"
$Server = "$ServerUser@$ServerIP"
$RemoteLogFile = "/opt/projects/backend/server.log"

# --- Checks ---
if (-not (Test-Path $PemPath)) {
    Write-Error "PEM key file not found at: $PemPath"
    exit 1
}

Write-Host "--------------------------------------------------"
Write-Host "Connecting to $ServerIP to tail logs..."
Write-Host "Target File: $RemoteLogFile"
Write-Host "Press Ctrl+C to stop."
Write-Host "--------------------------------------------------"

# Execute ssh with tail -f
# -t forces pseudo-terminal allocation (optional but good for interactive)
ssh -i $PemPath $Server "tail -f -n 50 $RemoteLogFile"
