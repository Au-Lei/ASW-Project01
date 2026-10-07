#!/usr/bin/env bash
# Run as root after placing the allowlisted release at /tmp/asw-release.zip.
set -euo pipefail

release_id="$(date -u +%Y%m%dT%H%M%SZ)"
release_dir="/opt/asw/releases/$release_id"
if ! id asw >/dev/null 2>&1; then
    useradd --system --home /var/lib/asw --shell /usr/sbin/nologin asw
fi
install -d -m 0755 /opt/asw/releases
install -d -m 0750 -o asw -g asw /var/lib/asw
install -d -m 0700 /etc/asw
install -d -m 0755 "$release_dir"
python3 -m zipfile -e /tmp/asw-release.zip "$release_dir"
python3 -m venv "$release_dir/.venv"
"$release_dir/.venv/bin/pip" install --disable-pip-version-check -r "$release_dir/requirements.txt"
if [ ! -f /etc/asw/asw.env ]; then
    key="$("$release_dir/.venv/bin/python" -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
    printf 'ASW_STATE_DIR=/var/lib/asw\nASW_REQUIRE_EXTERNAL_KEY=1\nASW_MASTER_KEY=%s\n' "$key" > /etc/asw/asw.env
    chmod 0600 /etc/asw/asw.env
fi
if [ -L /opt/asw/current ]; then
    readlink -f /opt/asw/current > /etc/asw/previous-release
fi
ln -sfn "$release_dir" /opt/asw/current
cat > /etc/systemd/system/asw.service <<'EOF'
[Unit]
Description=ASW contact sheet application
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=asw
Group=asw
WorkingDirectory=/opt/asw/current
EnvironmentFile=/etc/asw/asw.env
ExecStart=/opt/asw/current/.venv/bin/python /opt/asw/current/app.py
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/var/lib/asw
PrivateTmp=true
UMask=0077

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
echo "RELEASE=$release_dir"
echo "STATE=/var/lib/asw"
echo "Previous release, if any: $(cat /etc/asw/previous-release 2>/dev/null || echo none)"
