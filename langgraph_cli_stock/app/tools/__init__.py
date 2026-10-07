"""Tools package with stock price tool."""

import logging
from typing import Any, Dict, List

from .stock import (
    StockDataSource,
    get_stock_data_source,
    InvalidSymbolError,
    NoDataError,
    NetworkError
)


# Tool schema for stock_price - clear schema for LLM to call
STOCK_PRICE_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "stock_price",
        "description": "Get the stock price for a given US stock symbol on a specific date.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "The stock symbol (e.g., 'AAPL' for Apple, 'GOOGL' for Google, 'MSFT' for Microsoft)"
                },
                "date": {
                    "type": "string",
                    "description": "The date in YYYY-MM-DD format (e.g., '2024-01-15')"
                }
            },
            "required": ["symbol", "date"]
        }
    }
}


def stock_price(symbol: str, date: str, logger: logging.Logger = None) -> Dict[str, Any]:
    """
    Stock price tool - queries stock price for a given symbol and date.
    
    Args:
        symbol: Stock symbol (e.g., 'AAPL')
        date: Date in YYYY-MM-DD format
        logger: Optional logger for recording tool execution
        
    Returns:
        Dict with stock price information or error details
    """
    # Use the provided logger or get a default one
    if logger is None:
        logger = logging.getLogger("stock_price_tool")
    
    # Log tool call
    extra = {
        "trace_id": getattr(logger, "trace_id", ""),
        "event_type": "tool_call",
        "component": "stock_price",
        "payload": {
            "tool_name": "stock_price",
            "input": {
                "symbol": symbol,
                "date": date
            }
        }
    }
    logger.info(f"Tool call: stock_price(symbol={symbol}, date={date})", extra=extra)
    
    try:
        # Get stock data source
        source = get_stock_data_source()
        
        # Fetch price data
        result = source.get_price(symbol, date)
        
        # Log success
        extra["payload"]["success"] = True
        extra["payload"]["result"] = result
        logger.info(f"Tool result: stock_price success", extra=extra)
        
        return result
        
    except InvalidSymbolError as e:
        error_result = {
            "error": "invalid_symbol",
            "message": str(e)
        }
        extra["payload"]["success"] = False
        extra["payload"]["error"] = error_result
        logger.error(f"Tool error: invalid_symbol - {e}", extra=extra)
        return error_result
        
    except NoDataError as e:
        error_result = {
            "error": "no_data",
            "message": str(e)
        }
        extra["payload"]["success"] = False
        extra["payload"]["error"] = error_result
        logger.error(f"Tool error: no_data - {e}", extra=extra)
        return error_result
        
    except NetworkError as e:
        error_result = {
            "error": "network_error",
            "message": str(e)
        }
        extra["payload"]["success"] = False
        extra["payload"]["error"] = error_result
        logger.error(f"Tool error: network_error - {e}", extra=extra)
        return error_result
        
    except Exception as e:
        error_result = {
            "error": "unknown_error",
            "message": str(e)
        }
        extra["payload"]["success"] = False
        extra["payload"]["error"] = error_result
        logger.error(f"Tool error: unknown - {e}", extra=extra)
        return error_result


# Tool registry - easy to extend with more tools
TOOL_REGISTRY = {
    "stock_price": stock_price
}

# Tool schemas for LLM
AVAILABLE_TOOLS = [STOCK_PRICE_TOOL_SCHEMA]


def get_tool_names() -> List[str]:
    """Get list of registered tool names."""
    return list(TOOL_REGISTRY.keys())


def execute_tool(name: str, arguments: Dict[str, Any], logger: logging.Logger = None) -> Any:
    """Execute a tool by name with given arguments."""
    if name not in TOOL_REGISTRY:
        raise ValueError(f"Unknown tool: {name}")
    
    return TOOL_REGISTRY[name](logger=logger, **arguments)