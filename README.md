# parser-Kwork

Telegram-бот, который следит за биржей [Kwork](https://kwork.ru/projects) и сразу
присылает новые проекты из раздела **«Скрипты, боты и mini apps»**:

| Подкатегория        | Ссылка на Kwork                                        |
|---------------------|--------------------------------------------------------|
| 📜 Скрипты           | https://kwork.ru/projects?c=41&attr=7352               |
| 🕷 Парсеры           | https://kwork.ru/projects?c=41&attr=211                |
| 💬 Чат-боты          | https://kwork.ru/projects?c=41&attr=3587               |
| 📱 Telegram Mini Apps | https://kwork.ru/projects?c=41&attr=3934090           |
| 🧠 ИИ-агенты         | https://kwork.ru/projects?c=41&attr=5548694            |
| 🤖 ИИ-боты           | https://kwork.ru/projects?c=41&attr=4158112            |

## Что умеет

- **Уведомления о новых проектах**: раз в минуту (настраивается) проверяет
  Kwork и присылает новые проекты: название, бюджет, число предложений,
  время публикации, описание и кнопку «Открыть на Kwork».
- **🗂 Категории**: галочками выбираете, какие подкатегории отслеживать.
- **📋 Последние заказы**: 5 самых свежих проектов по выбранным категориям.
- **🔔 Уведомления**: быстро выключить или включить рассылку.
- **Закрытый доступ**: можно разрешить бота только себе (`ALLOWED_USERS`).

При первом запуске бот не шлёт всю текущую ленту. Он запоминает проекты,
которые уже есть, и дальше присылает только новые. Если бот был выключен
дольше 15 минут, после включения он снова просто запоминает ленту, чтобы
не завалить вас старыми проектами.

## Запуск

1. Создайте бота у [@BotFather](https://t.me/BotFather) (команда `/newbot`)
   и скопируйте токен.
2. Установите Python 3.10+ и зависимости:

   ```bash
   python -m venv .venv
   source .venv/bin/activate        # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Скопируйте `.env.example` в `.env` и впишите токен:

   ```bash
   cp .env.example .env
   ```

   | Переменная       | Что это                                                      |
   |------------------|--------------------------------------------------------------|
   | `BOT_TOKEN`      | токен от @BotFather (обязательно)                            |
   | `CHECK_INTERVAL` | как часто проверять Kwork, в секундах (по умолчанию 60, минимум 30) |
   | `ALLOWED_USERS`  | ваш Telegram ID (можно несколько через запятую); пусто — бот доступен всем |
   | `DB_PATH`        | файл базы SQLite (по умолчанию `kwork_bot.db`)               |
   | `KWORK_PROXY`    | прокси для запросов к kwork.ru, например `http://user:pass@host:port` |

   Свой Telegram ID можно узнать у [@userinfobot](https://t.me/userinfobot), или
   просто напишите боту: если доступ закрыт, он сам покажет ваш ID.

4. Запустите:

   ```bash
   python -m kwork_bot
   ```

   Напишите боту `/start`. Сразу после запуска все шесть подкатегорий
   уже включены.

### Чтобы бот работал постоянно

На сервере с Linux удобно запускать бота через systemd, например
`/etc/systemd/system/kwork-bot.service`:

```ini
[Unit]
Description=Kwork Telegram bot
After=network-online.target

[Service]
WorkingDirectory=/opt/parser-Kwork
ExecStart=/opt/parser-Kwork/.venv/bin/python -m kwork_bot
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now kwork-bot
journalctl -u kwork-bot -f     # логи
```

## Как это устроено

Страница https://kwork.ru/projects подгружает ленту POST-запросом на тот же
адрес. Бот делает такой же запрос с полями `c=41` (раздел), `attr=<id>`
(подкатегория) и `page=1` и получает JSON со списком проектов. Официального
API у Kwork нет, поэтому если Kwork что-то поменяет у себя, бот может
перестать получать проекты. Это будет видно в логах как
`Kwork, «…»: …`.

Kwork иногда блокирует запросы с зарубежных серверов и хостингов. Если в
логах постоянно `HTTP 403` или `ответ не JSON`, укажите российский прокси
в `KWORK_PROXY`.

```
kwork_bot/
  __main__.py    запуск: python -m kwork_bot
  categories.py  подкатегории и их id на Kwork
  kwork.py       запросы к Kwork и разбор ответа
  monitor.py     фоновая проверка и рассылка новых проектов
  handlers.py    команды и кнопки бота
  keyboards.py   клавиатуры
  formatting.py  текст сообщения о проекте
  storage.py     SQLite: пользователи, подписки, уже виденные проекты
```

## Тесты

```bash
pip install -r requirements-dev.txt
pytest
```
