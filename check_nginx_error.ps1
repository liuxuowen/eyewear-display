# ==========================================
# Check Nginx Error Log for 400 Causes
# ==========================================

$ErrorActionPreference = "Stop"
$PemPath = "C:/Users/liuxu/Documents/peiqi.pem"
$Server = "root@124.223.217.73"

Write-Host "--------------------------------------------------"
Write-Host "Searching Nginx error logs for recent client errors..."
Write-Host "--------------------------------------------------"

# 查找最近 100 行错误日志中包含 "header" 或 "client" 的条目
# 这些通常对应 400 错误的原因
ssh -i $PemPath $Server "tail -n 200 /var/log/nginx/error.log | grep -E 'too long|header|client'"

Write-Host "--------------------------------------------------"
Write-Host "Done."
