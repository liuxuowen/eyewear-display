# ==========================================
# One-Click Deployment Script (Windows Client)
# ==========================================

$ErrorActionPreference = "Stop"

# --- Configuration ---
$PemPath = "C:/Users/liuxu/Documents/peiqi.pem"
$ServerUser = "root"
$ServerIP = "124.223.217.73"
$Server = "$ServerUser@$ServerIP"

$LocalBackendPath = "$PSScriptRoot\backend"
$RemoteBasePath = "/opt/projects"
$RemoteBackendPath = "/opt/projects/backend"

# --- Checks ---
if (-not (Test-Path $PemPath)) {
    Write-Error "PEM key file not found at: $PemPath"
    exit 1
}

if (-not (Test-Path $LocalBackendPath)) {
    Write-Error "Backend directory not found at: $LocalBackendPath"
    exit 1
}

Write-Host "--------------------------------------------------"
Write-Host "Deploying to $ServerIP..."
Write-Host "--------------------------------------------------"

# 1. Upload Backend Files
Write-Host "[1/3] Packaging and uploading backend files..."

# Check if tar is available (Windows 10+ includes tar)
if (Get-Command "tar" -ErrorAction SilentlyContinue) {
    $TarName = "backend_deploy.tar.gz"
    $LocalTarPath = "$PSScriptRoot\$TarName"

    # Create tarball excluding .pyc and __pycache__
    # -C changes to the parent directory so the archive contains 'backend/...'
    Write-Host "Creating archive (excluding .pyc/__pycache__)..."
    tar --exclude "__pycache__" --exclude "*.pyc" -czf "$LocalTarPath" -C "$PSScriptRoot" backend

    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to create tar archive."
        exit 1
    }

    # Upload tarball
    Write-Host "Uploading archive..."
    scp -i $PemPath "$LocalTarPath" "$Server`:$RemoteBasePath/$TarName"
    
    if ($LASTEXITCODE -ne 0) {
        Write-Error "SCP upload failed."
        Remove-Item "$LocalTarPath" -ErrorAction SilentlyContinue
        exit 1
    }

    # Extract and remove remote tarball
    Write-Host "Extracting on server..."
    ssh -i $PemPath $Server "tar -xzf $RemoteBasePath/$TarName -C $RemoteBasePath && rm $RemoteBasePath/$TarName"

    if ($LASTEXITCODE -ne 0) {
        Write-Error "Remote extraction failed."
        Remove-Item "$LocalTarPath" -ErrorAction SilentlyContinue
        exit 1
    }

    # Cleanup local tarball
    Remove-Item "$LocalTarPath" -ErrorAction SilentlyContinue

} else {
    # Fallback for systems without tar: Clean local cache then scp -r
    Write-Warning "'tar' command not found. Falling back to direct SCP (cleaning local cache first)."
    
    # Remove local __pycache__ and .pyc files
    Get-ChildItem -Path $LocalBackendPath -Recurse -Include "__pycache__", "*.pyc" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

    # Upload folder
    scp -i $PemPath -r "$LocalBackendPath" "$Server`:$RemoteBasePath/"

    if ($LASTEXITCODE -ne 0) {
        Write-Error "SCP upload failed."
        exit 1
    }
}

# 2. Set Permissions
Write-Host "[2/4] Setting permissions..."
ssh -i $PemPath $Server "chmod +x $RemoteBackendPath/restart.sh $RemoteBackendPath/setup.sh"

if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to set permissions."
    exit 1
}

# 3. Setup Environment (Venv & Dependencies)
Write-Host "[3/4] Setting up environment and dependencies..."
ssh -i $PemPath $Server "bash $RemoteBackendPath/setup.sh"

if ($LASTEXITCODE -ne 0) {
    Write-Error "Setup script failed."
    exit 1
}

# 4. Execute Restart Script
Write-Host "[4/4] Restarting backend service..."
ssh -i $PemPath $Server "bash $RemoteBackendPath/restart.sh"

if ($LASTEXITCODE -ne 0) {
    Write-Error "Remote restart script failed."
    exit 1
}

Write-Host "--------------------------------------------------"
Write-Host "Deployment Successfully Completed!"
Write-Host "--------------------------------------------------"
