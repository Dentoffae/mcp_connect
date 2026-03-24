# MCP Connect — Product Manager Bot

Проект состоит из двух компонентов:

| Компонент | Технологии | Порт |
|-----------|-----------|------|
| **MCP Server** (`mcp_server/`) | FastAPI + SQLite3 | 8000 |
| **Telegram Bot** (`telegram_bot/`) | python-telegram-bot + OpenAI | — |

---

## Структура проекта

```
MCP_CONNECT/
├── mcp_server/
│   ├── server.py          ← FastAPI MCP-сервер (точка входа)
│   ├── db.py              ← SQLite3: создание БД, 100 тестовых товаров
│   ├── tools.py           ← Безопасный калькулятор (AST, без eval)
│   ├── requirements.txt
│   └── products.db        ← создаётся автоматически при первом запуске
│
├── telegram_bot/
│   ├── bot.py             ← Telegram-бот (точка входа)
│   ├── config.py          ← Загрузка .env конфига
│   ├── mcp_client.py      ← HTTP-клиент для вызова MCP-инструментов
│   └── requirements.txt
│
├── .env                   ← Ваши API-ключи (заполнить!)
└── README.md
```

---

## Быстрый старт

### 1. Заполните `.env`

Откройте файл `.env` и вставьте свои ключи:

```dotenv
TELEGRAM_TOKEN=123456789:AAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
MCP_SERVER_URL=http://localhost:8000
OPENAI_MODEL=gpt-4o-mini
```

- **TELEGRAM_TOKEN** — получите у [@BotFather](https://t.me/BotFather) (`/newbot`)
- **OPENAI_API_KEY** — получите на [platform.openai.com/api-keys](https://platform.openai.com/api-keys)

---

### 2. Установите зависимости

Откройте **два терминала**.

**Терминал 1 — MCP Server:**
```bash
cd mcp_server
pip install -r requirements.txt
```

**Терминал 2 — Telegram Bot:**
```bash
cd telegram_bot
pip install -r requirements.txt
```

---

### 3. Запустите MCP Server

В терминале 1:
```bash
cd mcp_server
python server.py
```

Ожидаемый вывод:
```
[DB] Seeded 100 test products into products.db
[MCP] product-mcp server started on http://0.0.0.0:8000
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

Проверить работу: http://localhost:8000/tools

---

### 4. Запустите Telegram Bot

В терминале 2:
```bash
cd telegram_bot
python bot.py
```

Ожидаемый вывод:
```
[Bot] Model      : gpt-4o-mini
[Bot] MCP server : http://localhost:8000
[Bot] Starting polling…
```

---

## MCP Server API

| Метод | Эндпоинт | Описание |
|-------|----------|----------|
| GET   | `/`            | Информация о сервере |
| GET   | `/tools`       | Список всех MCP-инструментов (JSON Schema) |
| POST  | `/tools/call`  | Вызов инструмента |
| POST  | `/mcp/rpc`     | JSON-RPC 2.0 эндпоинт (MCP-протокол) |

### Пример вызова инструмента

```bash
curl -X POST http://localhost:8000/tools/call \
  -H "Content-Type: application/json" \
  -d '{"name": "find_product", "arguments": {"name": "чай"}}'
```

---

## Доступные MCP-инструменты

| Инструмент | Параметры | Описание |
|-----------|-----------|----------|
| `list_products` | `limit`, `offset` | Список товаров с пагинацией |
| `find_product` | `name` | Поиск товаров по названию |
| `add_product` | `name`, `category`, `price` | Добавление товара |
| `calculate` | `expression` | Безопасный калькулятор (AST) |

---

## Примеры запросов боту

```
покажи все товары
покажи 10 товаров
найди кофе
есть ли шоколад?
добавь товар Манго, категория Фрукты, цена 250
сколько будет 1500 * 12 / 100
посчитай 2^10
```

---

## Категории тестовых товаров

- 🖥 Электроника (15 товаров)
- 🛒 Продукты (15 товаров)
- 👗 Одежда (15 товаров)
- 🏠 Дом и интерьер (15 товаров)
- ⚽ Спорт (15 товаров)
- 📚 Книги (10 товаров)
- 💄 Красота (15 товаров)

**Итого: 100 товаров**

---

## Требования к системе

- Python 3.10+
- Интернет-подключение (для OpenAI API и Telegram API)
- Токен Telegram-бота
- Ключ OpenAI API (платный аккаунт или credits)
