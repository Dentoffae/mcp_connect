#!/usr/bin/env python3
"""
Telegram bot — natural language interface to the product-mcp server.

Flow:
  User message → OpenAI GPT (function calling) → MCP tool(s) → final answer

Run:
    python bot.py
"""

import asyncio
import json
import logging
from typing import Dict, List, Any, Optional, Tuple

from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

from openai import AsyncOpenAI

from config import TELEGRAM_TOKEN, OPENAI_API_KEY, MCP_SERVER_URL, OPENAI_MODEL
from mcp_client import get_mcp_tools, call_mcp_tool, tools_to_openai_format, format_tool_result, format_products_direct

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# OpenAI client
# ---------------------------------------------------------------------------
openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """Ты — умный помощник для работы с базой данных товаров.

═══════════════════════════════════════════
ПРАВИЛО ВЫБОРА ИНСТРУМЕНТА (строго следуй):
═══════════════════════════════════════════

1. Пользователь называет слово/название товара → ВСЕГДА используй find_product(name="<слово>")
   Примеры:
   "найди чай"        → find_product(name="чай")
   "найди шоколад"    → find_product(name="шоколад")
   "есть кофе?"       → find_product(name="кофе")
   "покажи Nike"      → find_product(name="Nike")
   find_product ищет по ЧАСТИЧНОМУ совпадению в названии и вернёт ВСЕ подходящие товары.
   ЗАПРЕЩЕНО заменять поиск по слову на поиск по категории!

2. Пользователь называет КАТЕГОРИЮ → используй find_products_by_category(category="<категория>")
   Примеры:
   "покажи электронику"              → find_products_by_category(category="Электроника")
   "товары категории Спорт"          → find_products_by_category(category="Спорт")
   "что есть из продуктов питания?"  → find_products_by_category(category="Продукты")

3. Пользователь называет ID → используй find_product_by_id(id=<число>)
   Пример: "найди товар с ID 5" → find_product_by_id(id=5)

4. Пользователь просит похожие → используй find_similar_products(product_id=<id>)
   Если пользователь указал название, а не ID — сначала вызови find_product, возьми id первого результата,
   потом вызови find_similar_products.

5. Пользователь спрашивает стоимость количества товара → ВСЕГДА используй calculate_product_price
   Примеры (ключевые фразы: "сколько стоит", "стоимость N", "цена за N", "N штук/кг/л/упаковок"):
   "сколько стоит 10 кг чая"         → calculate_product_price(query="чай", quantity=10, unit="кг")
   "цена 5 шт шоколада"              → calculate_product_price(query="шоколад", quantity=5, unit="шт")
   "сколько стоит 3 бутылки кофе"    → calculate_product_price(query="кофе", quantity=3, unit="бутылки")
   "стоимость товара ID 16 в 7 штук" → calculate_product_price(query="16", quantity=7, unit="шт")
   "хочу купить 2 пальто"            → calculate_product_price(query="пальто", quantity=2, unit="шт")
   ЗАПРЕЩЕНО для таких запросов использовать find_product + calculate отдельно!

6. Показать весь каталог → list_products()

7. Добавить товар → add_product(name=..., category=..., price=...)

8. Посчитать произвольное выражение → calculate(expression=...)
   Используй только когда пользователь задаёт математический вопрос без товаров, например "2+2" или "15% от 3000".

═══════════════════════════════
ПРАВИЛА ОТВЕТА:
═══════════════════════════════
- Отвечай на русском языке, будь дружелюбным.
- Когда инструмент вернул список товаров — напиши ТОЛЬКО короткое вступление
  (например: "Нашёл 2 товара по запросу «чай»:"), товары будут выведены автоматически.
- При добавлении товара — подтверди с указанием ID.
- Цены указывай в рублях (₽).
- Не выдумывай данные — только из инструментов.
"""

# ---------------------------------------------------------------------------
# Conversation storage
# ---------------------------------------------------------------------------

# OpenAI message sequences per user (role/content/tool_calls/tool_call_id)
_histories: Dict[int, List[Dict[str, Any]]] = {}

# Human-readable log per user: list of (role, short_text)
_readable_log: Dict[int, List[tuple]] = {}

MAX_HISTORY_MSGS  = 30   # OpenAI messages kept (each turn = several messages)
MAX_READABLE_LOG  = 20   # readable entries shown in /history


def _log(user_id: int, role: str, text: str) -> None:
    """Append a line to the human-readable log for /history."""
    log = _readable_log.setdefault(user_id, [])
    log.append((role, text))
    _readable_log[user_id] = log[-MAX_READABLE_LOG:]


# ---------------------------------------------------------------------------
# Core LLM + tool-calling loop
# ---------------------------------------------------------------------------

# Tools that return a product list — their results are sent directly to the user
_LIST_TOOLS = {"list_products", "find_product", "find_products_by_category", "find_similar_products"}


async def run_agent(
    user_id: int, user_message: str
) -> Tuple[str, Optional[List[Dict]], str]:
    """
    Run the OpenAI agentic loop with context-aware history.

    History stores only (user / assistant-text) pairs — never tool_call objects.
    Context from previous tool calls is embedded as an annotation in the
    assistant message so the LLM can reference prior results in follow-up turns.

    Returns:
        (llm_text, products_or_None, product_label)
    """
    # ── History: only clean user/assistant text messages ─────────────────────
    history = _histories.setdefault(user_id, [])

    mcp_tools    = await get_mcp_tools()
    openai_tools = tools_to_openai_format(mcp_tools)

    # "Live" messages for this request — includes tool_calls, but NEVER saved to history
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *history[-MAX_HISTORY_MSGS:],          # safe: contains only user/assistant text
        {"role": "user", "content": user_message},
    ]

    collected_products: Optional[List[Dict]] = None
    product_label: str = ""
    tool_context_notes: List[str] = []         # compact summaries for history annotation

    MAX_ITERATIONS = 6
    for _ in range(MAX_ITERATIONS):
        response = await openai_client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            tools=openai_tools,
            tool_choice="auto",
            temperature=0.5,
            max_tokens=1024,
        )

        msg = response.choices[0].message

        # Build the assistant entry for the LIVE messages list (may have tool_calls)
        assistant_live: Dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            assistant_live["tool_calls"] = [
                {
                    "id":   tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in msg.tool_calls
            ]
        messages.append(assistant_live)

        # ── No tool calls → final answer ─────────────────────────────────────
        if not msg.tool_calls:
            final_text = msg.content or "Не могу ответить на этот вопрос."

            # Persist to history as plain text only (no tool_calls → no OpenAI errors)
            history_assistant = final_text
            if tool_context_notes:
                history_assistant += (
                    "\n\n[Контекст: " + "; ".join(tool_context_notes) + "]"
                )
            history.append({"role": "user",      "content": user_message})
            history.append({"role": "assistant", "content": history_assistant})
            _histories[user_id] = history[-MAX_HISTORY_MSGS:]

            _log(user_id, "user",      user_message)
            _log(user_id, "assistant", final_text)

            return final_text, collected_products, product_label

        # ── Execute tool calls (all in this iteration) ────────────────────────
        tool_msgs: List[Dict[str, Any]] = []
        for tc in msg.tool_calls:
            tool_name = tc.function.name
            try:
                tool_args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                tool_args = {}

            logger.info("Tool call → %s(%s)", tool_name, tool_args)

            try:
                tool_result = await call_mcp_tool(tool_name, tool_args)

                if tool_name in _LIST_TOOLS:
                    raw_products = tool_result.get("products", [])
                    count        = tool_result.get("count", len(raw_products))
                    if raw_products:
                        collected_products = raw_products
                        if tool_name == "find_product":
                            query = tool_result.get("query", "")
                            product_label = f"🔍 По запросу «{query}» найдено {count} товаров:"
                            preview = ", ".join(
                                f"«{p['name']}» ID={p['id']} {p['price']}₽"
                                for p in raw_products[:5]
                            )
                            tool_context_notes.append(
                                f"find_product('{query}'): {count} шт. — {preview}"
                                + (" и др." if count > 5 else "")
                            )
                        elif tool_name == "find_products_by_category":
                            cat = tool_result.get("category", "")
                            product_label = f"📂 Категория «{cat}» — {count} товаров:"
                            preview = ", ".join(
                                f"«{p['name']}» ID={p['id']}"
                                for p in raw_products[:5]
                            )
                            tool_context_notes.append(
                                f"категория '{cat}': {count} шт. — {preview}"
                                + (" и др." if count > 5 else "")
                            )
                        elif tool_name == "find_similar_products":
                            src = tool_result.get("source") or {}
                            product_label = (
                                f"🔗 Похожие на «{src.get('name', '')}» "
                                f"({src.get('category', '')}) — {count} шт.:"
                            )
                            tool_context_notes.append(
                                f"похожие на ID={src.get('id')} «{src.get('name','')}»: {count} шт."
                            )
                        else:
                            product_label = f"📋 Список товаров ({count} шт.):"
                            tool_context_notes.append(f"list_products: {count} шт.")

                        result_text = (
                            f"Найдено {count} товаров. "
                            "Список отправлен пользователю автоматически — "
                            "напиши только короткое дружелюбное вступление."
                        )
                    else:
                        result_text = format_tool_result(tool_name, tool_result)
                        tool_context_notes.append(f"{tool_name}: ничего не найдено")
                else:
                    result_text = format_tool_result(tool_name, tool_result)
                    if tool_name == "find_product_by_id":
                        p = tool_result.get("product") or {}
                        if p:
                            tool_context_notes.append(
                                f"ID={p.get('id')} → «{p.get('name')}» {p.get('price')}₽ [{p.get('category')}]"
                            )
                    elif tool_name == "calculate_product_price":
                        if tool_result.get("found"):
                            tool_context_notes.append(
                                f"расчёт цены: {tool_result.get('expression', '')}"
                            )
                    elif tool_name == "calculate":
                        tool_context_notes.append(
                            f"calc: {tool_result.get('expression','')} = {tool_result.get('result','')}"
                        )

            except Exception as exc:
                result_text = f"[Ошибка инструмента '{tool_name}']: {exc}"
                logger.error("Tool error: %s", exc)

            tool_msgs.append({
                "role":         "tool",
                "tool_call_id": tc.id,
                "content":      result_text,
            })

        # Add ALL tool results after the assistant entry (required by OpenAI)
        messages.extend(tool_msgs)

    return (
        "Превышен лимит итераций. Пожалуйста, переформулируйте запрос.",
        collected_products,
        product_label,
    )



# ---------------------------------------------------------------------------
# Safe senders — handle Telegram's 4096-char limit and Markdown errors
# ---------------------------------------------------------------------------

TG_LIMIT = 4000   # leave 96 chars buffer below the 4096 hard limit


async def send_text(update: Update, text: str) -> None:
    """Send plain text, splitting into chunks if longer than TG_LIMIT."""
    text = text.strip()
    if not text:
        return
    for i in range(0, len(text), TG_LIMIT):
        await update.message.reply_text(text[i : i + TG_LIMIT])


async def send_markdown(update: Update, text: str) -> None:
    """Send Markdown text, splitting if needed; falls back to plain on parse error."""
    text = text.strip()
    if not text:
        return
    chunks = [text[i : i + TG_LIMIT] for i in range(0, len(text), TG_LIMIT)]
    for chunk in chunks:
        try:
            await update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            await update.message.reply_text(chunk)


async def send_product_list(update: Update, products: List[Dict], header: str = "") -> None:
    """
    Send a product list directly (not through LLM).
    Products are formatted in chunks so nothing gets cut off.
    """
    lines = format_products_direct(products)   # one formatted string per product
    if header:
        await send_text(update, header)

    chunk_lines: List[str] = []
    chunk_len = 0
    for line in lines:
        if chunk_len + len(line) + 1 > TG_LIMIT and chunk_lines:
            await update.message.reply_text("\n".join(chunk_lines))
            chunk_lines = []
            chunk_len   = 0
        chunk_lines.append(line)
        chunk_len += len(line) + 1

    if chunk_lines:
        await update.message.reply_text("\n".join(chunk_lines))


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    name = update.effective_user.first_name or "друг"
    text = (
        f"👋 Привет, *{name}*!\n\n"
        "Я умный помощник магазина. Умею:\n"
        "📋 Показывать список товаров\n"
        "🔍 Искать товары по названию\n"
        "➕ Добавлять новые товары\n"
        "🧮 Считать математические выражения\n\n"
        "Просто пиши обычным языком!\n\n"
        "*Примеры:*\n"
        "— _покажи все товары_\n"
        "— _найди чай_\n"
        "— _добавь яблоки, категория фрукты, цена 120_\n"
        "— _сколько будет 15 \\* 89.99_\n\n"
        "/help — справка   /history — история   /clear — очистить"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "📖 *Справка*\n\n"
        "Пиши запросы обычным языком — я пойму!\n\n"
        "*Что я умею:*\n"
        "• `покажи все товары` — весь ассортимент\n"
        "• `найди чай` — все товары со словом «чай» в названии\n"
        "• `покажи товары категории электроника` — поиск по категории\n"
        "• `найди товар с ID 5` — поиск по ID\n"
        "• `покажи похожие на товар 16` — товары той же категории\n"
        "• `что похоже на чай зелёный?` — тоже поиск похожих\n"
        "• `сколько стоит 10 кг чая` — стоимость N единиц товара\n"
        "• `цена 5 шт шоколада` — тоже расчёт по цене из каталога\n"
        "• `стоимость товара ID 26 в 3 штуках` — расчёт по ID\n"
        "• `добавь товар «Манго» категория Фрукты цена 250` — добавление\n"
        "• `посчитай 1200 * 0.87` — обычный калькулятор\n\n"
        "*Доступные категории:*\n"
        "Электроника, Продукты, Одежда, Дом и интерьер, Спорт, Книги, Красота\n\n"
        "*Команды:*\n"
        "/start — приветствие\n"
        "/help — эта справка\n"
        "/history — посмотреть историю диалога\n"
        "/clear — очистить историю диалога"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    _histories.pop(user_id, None)
    _readable_log.pop(user_id, None)
    await update.message.reply_text("🧹 История диалога очищена!")


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the last N exchanges from the readable log."""
    user_id = update.effective_user.id
    log = _readable_log.get(user_id, [])

    if not log:
        await update.message.reply_text(
            "📭 История пуста. Начни диалог — и я всё запомню!"
        )
        return

    lines = ["📜 *История диалога:*\n"]
    for role, text in log:
        if role == "user":
            # Truncate long messages for display
            preview = text[:120] + "…" if len(text) > 120 else text
            lines.append(f"👤 *Вы:* {preview}")
        else:
            preview = text[:120] + "…" if len(text) > 120 else text
            lines.append(f"🤖 *Бот:* {preview}")

    lines.append(f"\n_Показано {len(log)} сообщений. /clear — очистить историю._")

    await send_markdown(update, "\n".join(lines))


# ---------------------------------------------------------------------------
# Main message handler
# ---------------------------------------------------------------------------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_text = (update.message.text or "").strip()
    if not user_text:
        return

    # Show typing indicator
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING,
    )

    try:
        llm_text, products, label = await run_agent(user_id, user_text)

        # Always send LLM intro/answer
        if llm_text:
            await send_markdown(update, llm_text)

        # If a product list was collected — send it directly, fully, split into chunks
        if products:
            await send_product_list(update, products, header=label)

    except Exception as exc:
        logger.error("Unhandled error in handle_message: %s", exc, exc_info=True)
        await update.message.reply_text(
            "❌ Произошла внутренняя ошибка.\n"
            "Убедитесь, что MCP-сервер запущен (`python mcp_server/server.py`)."
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    print(f"[Bot] Model      : {OPENAI_MODEL}")
    print(f"[Bot] MCP server : {MCP_SERVER_URL}")
    print("[Bot] Starting polling…")

    app = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .build()
    )

    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("help",    cmd_help))
    app.add_handler(CommandHandler("clear",   cmd_clear))
    app.add_handler(CommandHandler("history", cmd_history))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
