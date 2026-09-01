#!/bin/sh
# Generates a self-signed TLS certificate on first run if one doesn't
# already exist at the bind-mounted ./nginx/certs, then starts nginx.
#
# This is a PLACEHOLDER certificate for local/no-domain use. Once a real
# domain is assigned on the deployment server, replace server.crt/server.key
# in ./nginx/certs with a real certificate (Let's Encrypt via certbot, or an
# org-issued cert + key) - see DEPLOYMENT.md.
set -eu

CERT_DIR=/etc/nginx/certs
CERT_FILE="$CERT_DIR/server.crt"
KEY_FILE="$CERT_DIR/server.key"

if [ ! -f "$CERT_FILE" ] || [ ! -f "$KEY_FILE" ]; then
    echo "No TLS certificate found at $CERT_DIR - generating a self-signed placeholder."
    echo "Replace it with a real certificate once a domain is assigned - see DEPLOYMENT.md."
    apk add --no-cache openssl >/dev/null
    mkdir -p "$CERT_DIR"
    openssl req -x509 -nodes -days 825 \
        -newkey rsa:2048 \
        -keyout "$KEY_FILE" \
        -out "$CERT_FILE" \
        -subj "/CN=etop.local" \
        -addext "subjectAltName=DNS:etop.local,DNS:localhost,IP:127.0.0.1"
fi

exec nginx -g "daemon off;"
