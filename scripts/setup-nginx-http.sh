#!/usr/bin/env bash
set -Eeuo pipefail

# Automated Nginx HTTP-only reverse proxy setup for Debian 12
# - Installs nginx if missing
# - Writes a site config that listens on FRONT_PORT and proxies /api and /healthz to 127.0.0.1:PORT
# - Serves images from STATIC_IMAGES_DIR at /static/images/
# - Disables default site to avoid conflicts
# - Reloads nginx
#
# Usage examples:
#   ./scripts/setup-nginx-http.sh
#   BACKEND_PORT=8000 ./scripts/setup-nginx-http.sh
#   STATIC_IMAGES_DIR=/data/images ./scripts/setup-nginx-http.sh
#
# Env vars:
#   FRONT_PORT          default 8080 (public HTTP listen port)
#   BACKEND_PORT        default 5000 (internal backend port)
#   STATIC_IMAGES_DIR   default /var/www/resource/products_img
#   SITE_NAME           default eyewear-http

FRONT_PORT=${FRONT_PORT:-8080}
BACKEND_PORT=${BACKEND_PORT:-5000}
STATIC_IMAGES_DIR=${STATIC_IMAGES_DIR:-/var/www/resource/products_img}
SITE_NAME=${SITE_NAME:-eyewear-http}

if [[ $EUID -ne 0 ]]; then
  echo "[ERR ] Please run as root (sudo)." >&2
  exit 1
fi

echo "[INFO] Installing nginx (if not present) ..."
apt-get update -y
DEBIAN_FRONTEND=noninteractive apt-get install -y nginx

HTTP_CONF_PATH="/etc/nginx/sites-available/${SITE_NAME}.conf"
ENABLED_LINK="/etc/nginx/sites-enabled/${SITE_NAME}.conf"

echo "[INFO] Writing HTTP server block to ${HTTP_CONF_PATH} (listen ${FRONT_PORT} -> proxy 127.0.0.1:${BACKEND_PORT})"
cat >"$HTTP_CONF_PATH" <<EOF
map \$http_upgrade \$connection_upgrade {
  default upgrade;
  ''      close;
}

server {
  listen ${FRONT_PORT};
  listen [::]:${FRONT_PORT};
  server_name _;

  server_tokens off;
  client_max_body_size 10m;
  keepalive_timeout 65;
  sendfile on;
  tcp_nopush on;
  tcp_nodelay on;
  gzip on;
  gzip_types text/plain text/css application/json application/javascript application/x-javascript text/xml application/xml application/xml+rss text/javascript image/svg+xml;

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

echo "[INFO] Disabling default site if enabled"
if [[ -e /etc/nginx/sites-enabled/default ]]; then
  rm -f /etc/nginx/sites-enabled/default
fi

echo "[INFO] Enabling site and reloading nginx"
ln -sf "$HTTP_CONF_PATH" "$ENABLED_LINK"
nginx -t
systemctl reload nginx

echo "[OK  ] HTTP reverse proxy is live on port ${FRONT_PORT}. Test endpoints:"
echo "      curl -i http://127.0.0.1:${FRONT_PORT}/healthz"
echo "      curl -i http://127.0.0.1:${FRONT_PORT}/api/products"
echo "[NOTE] Real WeChat Mini Program on device requires HTTPS:443; use this only for interim testing."
