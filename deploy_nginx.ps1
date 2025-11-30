# ==========================================
# Nginx Config Deployment Script (Windows Client)
# ==========================================

$ErrorActionPreference = "Stop"

# --- Configuration ---
$PemPath = "C:/Users/liuxu/Documents/peiqi.pem"
$ServerUser = "root"
$ServerIP = "124.223.217.73"
$Server = "$ServerUser@$ServerIP"

$LocalConfigPath = "$PSScriptRoot\nginx-config"
$RemoteConfigPath = "/etc/nginx/sites-available"

# --- Checks ---
if (-not (Test-Path $PemPath)) {
    Write-Error "PEM key file not found at: $PemPath"
    exit 1
}

Write-Host "--------------------------------------------------"
Write-Host "Deploying Nginx Config to $ServerIP..."
Write-Host "--------------------------------------------------"

# 1. Upload Config Files
Write-Host "[1/2] Uploading configuration files..."
# Upload contents of nginx-config to sites-available
scp -i $PemPath "$LocalConfigPath/eyewear.conf" "$Server`:$RemoteConfigPath/"

if ($LASTEXITCODE -ne 0) {
    Write-Error "SCP upload failed."
    exit 1
}

# 2. Reload Nginx
Write-Host "[2/2] Testing and Reloading Nginx..."
ssh -i $PemPath $Server "nginx -t && systemctl reload nginx"

if ($LASTEXITCODE -ne 0) {
    Write-Error "Nginx reload failed. Please check the configuration."
    exit 1
}

Write-Host "--------------------------------------------------"
Write-Host "Nginx Config Deployed Successfully!"
Write-Host "--------------------------------------------------"
