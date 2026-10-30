#!/usr/bin/env bash
# Installs a systemd --user service + timer that runs `f1paper run` daily.
#
# Usage: install_timer_linux.sh [HH:MM]
set -euo pipefail

RUN_TIME="${1:-09:00}"

PYTHON_BIN="$(command -v python3 || command -v python)"
if [ -z "${PYTHON_BIN}" ]; then
    echo "Could not find python3/python on PATH. Install Python and 'pip install -e .' this project first." >&2
    exit 1
fi

SERVICE_DIR="$HOME/.config/systemd/user"
mkdir -p "$SERVICE_DIR"

cat > "$SERVICE_DIR/f1paper.service" <<EOF
[Unit]
Description=Refresh F1 race-weekend desktop wallpaper (f1paper)

[Service]
Type=oneshot
ExecStart=${PYTHON_BIN} -m f1paper.cli run
EOF

cat > "$SERVICE_DIR/f1paper.timer" <<EOF
[Unit]
Description=Daily timer for f1paper

[Timer]
OnCalendar=*-*-* ${RUN_TIME}:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now f1paper.timer

echo "Installed and enabled f1paper systemd --user timer (daily at ${RUN_TIME})."
echo "Run it manually any time with: systemctl --user start f1paper.service"
echo "Note: for this to run when you're not logged in, enable lingering: loginctl enable-linger \$USER"
