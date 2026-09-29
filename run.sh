#!/usr/bin/env bash
# Запуск бота в терминале (Linux/macOS):
#   ./run.sh          — запустить бота (при первом запуске спросит токен)
#   ./run.sh setup    — поменять токен или доступ
#   ./run.sh check    — проверить связь с Telegram и Kwork
# Остановить бота — Ctrl+C.
set -euo pipefail
cd "$(dirname "$0")"

PYTHON=${PYTHON:-python3}
if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "Не найден $PYTHON. Установите Python 3.10+ (Ubuntu/Debian: sudo apt install python3 python3-venv)" >&2
    exit 1
fi
if ! "$PYTHON" -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
    echo "Нужен Python 3.10 или новее, а у вас $("$PYTHON" -V 2>&1)" >&2
    exit 1
fi

if [ ! -x .venv/bin/python ]; then
    echo "Создаю виртуальное окружение .venv…"
    if ! "$PYTHON" -m venv .venv; then
        rm -rf .venv
        echo "Не удалось создать .venv. На Ubuntu/Debian: sudo apt install python3-venv" >&2
        exit 1
    fi
fi

if [ ! -f .venv/.installed ] || [ requirements.txt -nt .venv/.installed ]; then
    echo "Устанавливаю зависимости…"
    .venv/bin/python -m pip install -q --disable-pip-version-check -r requirements.txt
    touch .venv/.installed
fi

exec .venv/bin/python -m kwork_bot "$@"
