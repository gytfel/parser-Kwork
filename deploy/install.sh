#!/usr/bin/env bash
# Установка бота на VPS (Ubuntu 22.04+ / Debian 12+) как системной службы.
#
#   git clone -b claude/kwork-parser-telegram-bot-vx02ke https://github.com/gytfel/parser-Kwork.git
#   cd parser-Kwork
#   bash deploy/install.sh        (не под root — через sudo)
#
# Скрипт ставит Python, копирует бота в /opt/kwork-bot, спрашивает токен,
# создаёт службу systemd (бот сам стартует после перезагрузки сервера и
# перезапускается при сбоях) и команду kwork-bot для управления.
# Повторный запуск обновляет код и перезапускает бота; .env и база сохраняются.
#
# Без вопросов: sudo BOT_TOKEN=... ALLOWED_USERS=... bash deploy/install.sh
set -euo pipefail

APP_DIR=/opt/kwork-bot
APP_USER=kworkbot
SERVICE=kwork-bot
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

step() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
fail() { printf '\n\033[1;31mОшибка: %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || fail "нужны права root: sudo bash deploy/install.sh"
[ -f "$SRC_DIR/kwork_bot/__main__.py" ] || fail "не найден код бота в $SRC_DIR"
[ "$SRC_DIR" != "$APP_DIR" ] || fail "склонируйте проект в другую папку (например, ~/parser-Kwork), а не в $APP_DIR"
command -v systemctl >/dev/null || fail "на сервере нет systemd — нужен Ubuntu 22.04+ или Debian 12+"

step "Проверяю Python"
if ! python3 -c 'import ensurepip, venv' >/dev/null 2>&1; then
    if command -v apt-get >/dev/null; then
        export DEBIAN_FRONTEND=noninteractive
        apt-get update -qq
        apt-get install -y -qq python3 python3-venv python3-pip >/dev/null
    elif command -v dnf >/dev/null; then
        dnf install -y -q python3 python3-pip
    else
        fail "установите python3 (3.10+) с модулем venv и запустите скрипт снова"
    fi
fi
python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' \
    || fail "нужен Python 3.10+, а на сервере $(python3 -V 2>&1). Возьмите Ubuntu 22.04+ или Debian 12+"
echo "$(python3 -V) — подходит"

step "Копирую бота в $APP_DIR"
id -u "$APP_USER" >/dev/null 2>&1 \
    || useradd --system --home-dir "$APP_DIR" --no-create-home --shell /usr/sbin/nologin "$APP_USER"
mkdir -p "$APP_DIR"
rm -rf "$APP_DIR/kwork_bot"
cp -r "$SRC_DIR/kwork_bot" "$SRC_DIR/requirements.txt" "$SRC_DIR/.env.example" "$APP_DIR/"
echo "$SRC_DIR" > "$APP_DIR/.source"

step "Ставлю зависимости"
[ -x "$APP_DIR/.venv/bin/python" ] || python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/python" -m pip install -q --disable-pip-version-check --upgrade pip
"$APP_DIR/.venv/bin/python" -m pip install -q --disable-pip-version-check -r "$APP_DIR/requirements.txt"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

run_as_app() {
    (cd "$APP_DIR" && runuser -u "$APP_USER" -- "$APP_DIR/.venv/bin/python" -m kwork_bot "$@")
}

if ! grep -qE '^BOT_TOKEN=.+' "$APP_DIR/.env" 2>/dev/null; then
    step "Настройка"
    if [ -n "${BOT_TOKEN:-}" ]; then
        run_as_app setup --token "$BOT_TOKEN" --allowed-users "${ALLOWED_USERS:-}"
    else
        run_as_app setup </dev/tty
    fi
fi

step "Проверяю связь с Telegram и Kwork"
if ! run_as_app check; then
    printf '\n\033[1;33mПроверка нашла проблемы (см. выше). Бот всё равно будет запущен —\n'
    printf 'когда поправите настройки, выполните: kwork-bot restart\033[0m\n'
fi

step "Создаю службу $SERVICE"
cat > "/etc/systemd/system/$SERVICE.service" <<EOF
[Unit]
Description=Kwork Telegram bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/.venv/bin/python -m kwork_bot
Environment=PYTHONUNBUFFERED=1
Restart=always
RestartSec=10
NoNewPrivileges=true
ProtectSystem=full
ProtectHome=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF
install -m 755 "$SRC_DIR/deploy/kwork-bot" /usr/local/bin/kwork-bot
systemctl daemon-reload
systemctl enable --quiet "$SERVICE"
systemctl restart "$SERVICE"

sleep 5
if ! systemctl is-active --quiet "$SERVICE"; then
    journalctl -u "$SERVICE" -n 30 --no-pager || true
    fail "бот не запустился — причина в логе выше"
fi

step "Готово! Бот работает и сам запустится после перезагрузки сервера."
cat <<'EOF'

Напишите боту /start в Telegram.

Управление ботом на сервере:
  kwork-bot status    — работает ли бот
  kwork-bot logs      — логи в реальном времени (выход — Ctrl+C)
  kwork-bot restart   — перезапустить
  kwork-bot stop      — остановить (kwork-bot start — запустить)
  kwork-bot setup     — поменять токен или доступ
  kwork-bot check     — проверить связь с Telegram и Kwork
  kwork-bot config    — открыть .env (прокси, интервал проверки)
  kwork-bot update    — скачать новую версию из git и перезапустить
EOF
