#!/usr/bin/env bash
set -Eeuo pipefail

# Automated Nginx + HTTPS (Certbot) setup for Debian 12
# This script:
# 1) Installs nginx and certbot
# 2) Creates an HTTP-only server block for your domain
# 3) Reloads nginx
# 4) Obtains and installs a Let’s Encrypt cert with certbot --nginx and enables HTTPS redirect
# 5) Reloads nginx
#
# Requirements:
# - Run as root (sudo)
# - Your DOMAIN must already resolve (A/AAAA) to this server’s public IP
# - Your backend is running on 127.0.0.1:PORT (default 5000)
#
# Usage examples:
#   DOMAIN=example.com EMAIL=admin@example.com ./scripts/setup-nginx-https.sh
#   DOMAIN=api.example.com EMAIL=admin@example.com BACKEND_PORT=5000 STATIC_IMAGES_DIR=/var/www/resource/products_img ./scripts/setup-nginx-https.sh

DOMAIN=${DOMAIN:-yimuliaoran.top}
EMAIL=${EMAIL:-admin@yimuliaoran.top}
BACKEND_PORT=${BACKEND_PORT:-5000}
STATIC_IMAGES_DIR=${STATIC_IMAGES_DIR:-/var/www/resource/products_img}
SITE_NAME=${SITE_NAME:-eyewear}

if [[ $EUID -ne 0 ]]; then
  echo "[ERR ] Please run as root (sudo)." >&2
  exit 1
fi

if [[ -z "$DOMAIN" || -z "$EMAIL" ]]; then
  echo "[ERR ] DOMAIN and EMAIL env vars are required." >&2
  echo "       Example: DOMAIN=example.com EMAIL=admin@example.com ./scripts/setup-nginx-https.sh" >&2
  exit 1
fi

echo "[INFO] Installing nginx and certbot..."
apt-get update -y
DEBIAN_FRONTEND=noninteractive apt-get install -y nginx certbot python3-certbot-nginx

HTTP_CONF_PATH="/etc/nginx/sites-available/${SITE_NAME}.conf"
ENABLED_LINK="/etc/nginx/sites-enabled/${SITE_NAME}.conf"

echo "[INFO] Writing HTTP server block to ${HTTP_CONF_PATH}"
cat >"$HTTP_CONF_PATH" <<EOF
server {
  listen 80;
  listen [::]:80;
  server_name ${DOMAIN};

  server_tokens off;
  client_max_body_size 10m;

  # Static images
  location /static/images/ {
    alias ${STATIC_IMAGES_DIR}/;
    autoindex off;
    access_log off;
    gzip off;      # avoid compression-related length issues for binaries
    aio off;       # stability for some filesystems/clients
    add_header Cache-Control "public, max-age=31536000, immutable";
    # If files lack extensions and are JPEGs, you may force content type:
    # types {}
    # default_type image/jpeg;
  }

  # Health check
  location = /healthz {
    proxy_pass http://127.0.0.1:${BACKEND_PORT}/healthz;
    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto http;
  }

  # API proxy
  location /api/ {
    proxy_pass http://127.0.0.1:${BACKEND_PORT};
    proxy_http_version 1.1;
    proxy_set_header Upgrade \$http_upgrade;
    proxy_set_header Connection \$connection_upgrade;
    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto http;
    proxy_read_timeout 60s;
  }

  location / {
    return 404;
  }
}
EOF

echo "[INFO] Enabling site and reloading nginx..."
ln -sf "$HTTP_CONF_PATH" "$ENABLED_LINK"
nginx -t
systemctl reload nginx

echo "[INFO] Requesting Let’s Encrypt certificate for ${DOMAIN} via certbot --nginx"
certbot --nginx -d "$DOMAIN" --email "$EMAIL" --agree-tos --no-eff-email --redirect -n

echo "[INFO] Final nginx config test and reload"
nginx -t
systemctl reload nginx

echo "[OK  ] HTTPS is set up. Test: https://${DOMAIN}/healthz and https://${DOMAIN}/api/products"
echo "[NOTE] If your backend listens on a different port, rerun with BACKEND_PORT set accordingly."
echo "[NOTE] To customize further, see scripts/nginx-https.conf.example"
