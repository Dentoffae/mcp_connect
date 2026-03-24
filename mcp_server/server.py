#!/usr/bin/env python3
"""
product-mcp  — MCP-compatible HTTP server (FastAPI).

Endpoints
---------
GET  /            — server info
GET  /tools       — list all tools in MCP JSON-schema format
POST /tools/call  — execute a tool   { "name": "...", "arguments": {...} }
POST /mcp/rpc     — JSON-RPC 2.0 endpoint (MCP protocol)

Run:
    python server.py
"""

import json
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from db import (
    init_db, get_all_products,
    search_products_by_name, search_products_by_category,
    get_product_by_id, find_similar_products,
    add_product_to_db,
)
from tools import safe_calculate

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="product-mcp",
    description="MCP Server — product management + calculator",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# MCP Tool definitions (JSON Schema)
# ---------------------------------------------------------------------------

MCP_TOOLS: List[Dict] = [
    {
        "name": "list_products",
        "description": (
            "Returns a paginated list of all products from the database. "
            "Use limit and offset for pagination."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit":  {"type": "integer", "description": "Max products to return (default 50)", "default": 50},
                "offset": {"type": "integer", "description": "Products to skip (default 0)",        "default": 0},
            },
        },
    },
    {
        "name": "find_product",
        "description": (
            "Full-text search across ALL product names. "
            "Returns EVERY product whose name contains the given keyword. "
            "Example: keyword='чай' returns 'Чай зелёный', 'Чай чёрный Ахмад', etc. "
            "Use this whenever the user asks to find/search a product by word or phrase. "
            "Do NOT use find_products_by_category for name-based searches."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Keyword to search in product names, e.g. 'чай', 'шоколад', 'Nike'",
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "find_products_by_category",
        "description": (
            "Find products by CATEGORY name only. "
            "Use ONLY when the user explicitly asks for a category, e.g. 'покажи электронику' or 'товары категории Спорт'. "
            "Do NOT use this for searches by product name or keyword."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Category name, e.g. 'Электроника', 'Продукты', 'Спорт'",
                },
            },
            "required": ["category"],
        },
    },
    {
        "name": "find_product_by_id",
        "description": "Find a single product by its exact numeric ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "integer", "description": "Product ID"},
            },
            "required": ["id"],
        },
    },
    {
        "name": "find_similar_products",
        "description": (
            "Find products similar to a given product (same category). "
            "Requires the product ID. Use find_product_by_id first if you only have a name."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "integer", "description": "ID of the reference product"},
            },
            "required": ["product_id"],
        },
    },
    {
        "name": "calculate_product_price",
        "description": (
            "Look up a product by name or ID and calculate the total price for a given quantity. "
            "Use this when the user asks things like: "
            "'сколько стоит 10 кг чая', '5 штук шоколада', 'цена 3 единицы товара ID 26'. "
            "The tool finds the product, takes its unit price from the database, "
            "and returns unit_price × quantity = total."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Product name (partial match) OR numeric product ID as a string, e.g. 'чай зелёный' or '16'",
                },
                "quantity": {
                    "type": "number",
                    "description": "Quantity to multiply the price by, e.g. 10",
                },
                "unit": {
                    "type": "string",
                    "description": "Optional unit label for display, e.g. 'кг', 'шт', 'л'",
                    "default": "шт",
                },
            },
            "required": ["query", "quantity"],
        },
    },
    {
        "name": "add_product",
        "description": "Add a new product to the database.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name":     {"type": "string", "description": "Product name"},
                "category": {"type": "string", "description": "Product category"},
                "price":    {"type": "number", "description": "Price in rubles"},
            },
            "required": ["name", "category", "price"],
        },
    },
    {
        "name": "calculate",
        "description": (
            "Safely evaluate a mathematical expression. "
            "Supports +  -  *  /  //  %  ** (power). "
            "eval() is never used — parsing is done via Python AST."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Math expression, e.g. '(1500 * 12) / 100'",
                },
            },
            "required": ["expression"],
        },
    },
]

# ---------------------------------------------------------------------------
# Tool executor
# ---------------------------------------------------------------------------

def _execute_tool(name: str, arguments: Dict[str, Any]) -> Any:
    if name == "list_products":
        limit  = int(arguments.get("limit",  50))
        offset = int(arguments.get("offset",  0))
        products = get_all_products(limit=limit, offset=offset)
        return {"count": len(products), "products": products}

    if name == "find_product":
        query = arguments.get("name", "").strip()
        if not query:
            raise ValueError("Parameter 'name' is required and must not be empty")
        products = search_products_by_name(query)
        return {"query": query, "count": len(products), "products": products}

    if name == "find_products_by_category":
        category = arguments.get("category", "").strip()
        if not category:
            raise ValueError("Parameter 'category' is required and must not be empty")
        products = search_products_by_category(category)
        return {"category": category, "count": len(products), "products": products}

    if name == "find_product_by_id":
        try:
            product_id = int(arguments.get("id", 0))
        except (TypeError, ValueError):
            raise ValueError("Parameter 'id' must be an integer")
        product = get_product_by_id(product_id)
        if not product:
            return {"found": False, "product": None, "message": f"Product with ID={product_id} not found"}
        return {"found": True, "product": product}

    if name == "find_similar_products":
        try:
            product_id = int(arguments.get("product_id", 0))
        except (TypeError, ValueError):
            raise ValueError("Parameter 'product_id' must be an integer")
        result = find_similar_products(product_id)
        return result

    if name == "calculate_product_price":
        query    = str(arguments.get("query", "")).strip()
        quantity = arguments.get("quantity")
        unit     = str(arguments.get("unit", "шт")).strip() or "шт"

        if not query:
            raise ValueError("Parameter 'query' is required")
        if quantity is None:
            raise ValueError("Parameter 'quantity' is required")
        quantity = float(quantity)
        if quantity <= 0:
            raise ValueError("Quantity must be greater than zero")

        # Try to resolve as numeric ID first
        product = None
        if query.isdigit():
            product = get_product_by_id(int(query))

        # Fall back to name search — take the closest (first) match
        if not product:
            matches = search_products_by_name(query)
            if matches:
                product = matches[0]
                ambiguous = len(matches) > 1
            else:
                ambiguous = False

        if not product:
            return {
                "found": False,
                "query": query,
                "message": f"Товар по запросу «{query}» не найден в базе данных.",
            }

        unit_price = product["price"]
        total      = round(unit_price * quantity, 2)

        result = {
            "found":       True,
            "product":     product,
            "quantity":    quantity,
            "unit":        unit,
            "unit_price":  unit_price,
            "total":       total,
            "expression":  f"{unit_price} ₽ × {quantity} {unit} = {total} ₽",
        }
        # Warn if multiple products matched the name query
        if not query.isdigit() and "ambiguous" in dir() and ambiguous:
            matches_preview = search_products_by_name(query)
            result["note"] = (
                f"По запросу «{query}» найдено несколько товаров. "
                f"Использован первый: «{product['name']}» (ID {product['id']}). "
                f"Уточните запрос или используйте ID для точного выбора."
            )
            result["other_matches"] = [
                {"id": p["id"], "name": p["name"], "price": p["price"]}
                for p in matches_preview[1:5]
            ]
        return result

    if name == "add_product":
        prod_name = (arguments.get("name") or "").strip()
        category  = (arguments.get("category") or "").strip()
        price     = arguments.get("price")
        if not prod_name:
            raise ValueError("Parameter 'name' is required")
        if not category:
            raise ValueError("Parameter 'category' is required")
        if price is None:
            raise ValueError("Parameter 'price' is required")
        new_id = add_product_to_db(prod_name, category, float(price))
        return {
            "success": True,
            "id": new_id,
            "message": f"Product '{prod_name}' successfully added (ID={new_id})",
        }

    if name == "calculate":
        expression = arguments.get("expression", "").strip()
        if not expression:
            raise ValueError("Parameter 'expression' is required")
        result = safe_calculate(expression)
        return {"expression": expression, "result": result}

    raise ValueError(f"Unknown tool: '{name}'")


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ToolCallRequest(BaseModel):
    name: str
    arguments: Dict[str, Any] = {}

# ---------------------------------------------------------------------------
# HTTP endpoints
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def on_startup() -> None:
    init_db()
    print("[MCP] product-mcp server started on http://0.0.0.0:8000")


@app.get("/")
async def root():
    return {
        "name": "product-mcp",
        "version": "1.0.0",
        "protocol": "MCP/HTTP",
        "tools": [t["name"] for t in MCP_TOOLS],
    }


@app.get("/tools")
async def list_tools():
    """Return all MCP tools with JSON-schema definitions."""
    return {"tools": MCP_TOOLS}


@app.post("/tools/call")
async def call_tool(req: ToolCallRequest):
    """Execute a single MCP tool and return the result."""
    try:
        result = _execute_tool(req.name, req.arguments)
        return {"success": True, "result": result}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Internal error: {exc}")


@app.post("/mcp/rpc")
async def mcp_jsonrpc(body: Dict[str, Any]):
    """
    Minimal JSON-RPC 2.0 endpoint for MCP protocol compatibility.
    Supports: initialize, ping, tools/list, tools/call
    """
    rpc_id  = body.get("id", 1)
    method  = body.get("method", "")
    params  = body.get("params", {})

    def ok(result):
        return {"jsonrpc": "2.0", "id": rpc_id, "result": result}

    def err(code, message):
        return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": code, "message": message}}

    try:
        if method == "initialize":
            return ok({
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "product-mcp", "version": "1.0.0"},
            })

        if method == "ping":
            return ok({})

        if method == "tools/list":
            return ok({"tools": MCP_TOOLS})

        if method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            result    = _execute_tool(tool_name, arguments)
            return ok({
                "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]
            })

        return err(-32601, f"Method not found: {method}")

    except ValueError as exc:
        return err(-32602, str(exc))
    except Exception as exc:
        return err(-32603, f"Internal error: {exc}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
