"""
MCP HTTP client — thin async wrapper over the product-mcp REST API.

All functions are async; use them inside asyncio context (bot handlers).
"""

import json
from typing import Any, Dict, List

import httpx

from config import MCP_SERVER_URL

_TIMEOUT = httpx.Timeout(30.0)


# ---------------------------------------------------------------------------
# Raw API calls
# ---------------------------------------------------------------------------

async def get_mcp_tools() -> List[Dict]:
    """Fetch the list of available tools from the MCP server."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(f"{MCP_SERVER_URL}/tools")
        resp.raise_for_status()
        return resp.json().get("tools", [])


async def call_mcp_tool(tool_name: str, arguments: Dict[str, Any]) -> Any:
    """
    Execute a named tool on the MCP server.
    Returns the 'result' field on success, raises on error.
    """
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        payload = {"name": tool_name, "arguments": arguments}
        resp = await client.post(f"{MCP_SERVER_URL}/tools/call", json=payload)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            raise RuntimeError(data.get("error", "Unknown MCP error"))
        return data["result"]


# ---------------------------------------------------------------------------
# Converters for OpenAI function-calling
# ---------------------------------------------------------------------------

def tools_to_openai_format(tools: List[Dict]) -> List[Dict]:
    """
    Convert MCP tool definitions to the OpenAI tools array format.

    MCP schema:   { name, description, inputSchema }
    OpenAI format: { type: "function", function: { name, description, parameters } }
    """
    return [
        {
            "type": "function",
            "function": {
                "name":        t["name"],
                "description": t["description"],
                "parameters":  t["inputSchema"],
            },
        }
        for t in tools
    ]


# ---------------------------------------------------------------------------
# Result formatters (used as tool-result text passed back to the LLM)
# ---------------------------------------------------------------------------

def _fmt_products(products: List[Dict]) -> str:
    if not products:
        return "Товары не найдены."
    lines = []
    for p in products:
        lines.append(
            f"  ID {p['id']}: {p['name']} | Категория: {p['category']} | Цена: {p['price']:.2f} ₽"
        )
    return "\n".join(lines)


def format_products_direct(products: List[Dict]) -> List[str]:
    """
    Return a list of formatted strings — one per product.
    Used by the bot to send the full list directly (with chunking),
    bypassing any LLM summarisation.
    """
    if not products:
        return ["Товары не найдены."]
    return [
        f"🏷 {p['name']}\n"
        f"   📂 {p['category']}  |  💰 {p['price']:.2f} ₽  |  ID: {p['id']}"
        for p in products
    ]


def format_tool_result(tool_name: str, result: Any) -> str:
    """
    Produce a plain-text summary of a tool result for the LLM context.
    The LLM will then rephrase this into a user-friendly Telegram message.
    """
    if tool_name == "list_products":
        count    = result.get("count", 0)
        products = result.get("products", [])
        return f"Список товаров ({count} шт.):\n" + _fmt_products(products)

    if tool_name == "find_product":
        query    = result.get("query", "")
        count    = result.get("count", 0)
        products = result.get("products", [])
        if count == 0:
            return f"По запросу «{query}» ничего не найдено."
        return f"Результаты поиска «{query}» — найдено {count} шт.:\n" + _fmt_products(products)

    if tool_name == "find_products_by_category":
        category = result.get("category", "")
        count    = result.get("count", 0)
        products = result.get("products", [])
        if count == 0:
            return f"В категории «{category}» товары не найдены."
        return f"Товары в категории «{category}» — найдено {count} шт.:\n" + _fmt_products(products)

    if tool_name == "find_product_by_id":
        if not result.get("found"):
            return result.get("message", "Товар не найден.")
        p = result["product"]
        return (
            f"Товар найден:\n"
            f"  ID {p['id']}: {p['name']} | Категория: {p['category']} | Цена: {p['price']:.2f} ₽"
        )

    if tool_name == "find_similar_products":
        source   = result.get("source")
        count    = result.get("count", 0)
        products = result.get("products", [])
        if not source:
            return "Исходный товар не найден."
        header = (
            f"Похожие товары на «{source['name']}» "
            f"(категория «{source['category']}») — {count} шт."
        )
        if count == 0:
            return header + "\nПохожих товаров нет."
        return header + ":\n" + _fmt_products(products)

    if tool_name == "calculate_product_price":
        if not result.get("found"):
            return result.get("message", "Товар не найден.")
        p        = result["product"]
        qty      = result["quantity"]
        unit     = result.get("unit", "шт")
        u_price  = result["unit_price"]
        total    = result["total"]
        note     = result.get("note", "")
        others   = result.get("other_matches", [])

        lines = [
            f"Товар: {p['name']} (ID {p['id']}, категория: {p['category']})",
            f"Цена за единицу: {u_price:.2f} ₽",
            f"Количество: {qty} {unit}",
            f"Итого: {u_price:.2f} × {qty} = {total:.2f} ₽",
        ]
        if note:
            lines.append(f"\nПримечание: {note}")
            if others:
                lines.append("Другие совпадения:")
                for o in others:
                    lines.append(f"  ID {o['id']}: {o['name']} — {o['price']:.2f} ₽")
        return "\n".join(lines)

    if tool_name == "add_product":
        return result.get("message", "Товар добавлен.")

    if tool_name == "calculate":
        expr = result.get("expression", "")
        res  = result.get("result", "")
        return f"Результат вычисления: {expr} = {res}"

    # Fallback — dump raw JSON
    return json.dumps(result, ensure_ascii=False, indent=2)
