"""Stock data source module using yfinance."""

import logging
from typing import Any, Dict, Optional

import yfinance as yf


class StockDataError(Exception):
    """Base exception for stock data errors."""
    pass


class InvalidSymbolError(StockDataError):
    """Raised when stock symbol is invalid."""
    pass


class NoDataError(StockDataError):
    """Raised when no data is available for the symbol/date."""
    pass


class NetworkError(StockDataError):
    """Raised when network request fails."""
    pass


class StockDataSource:
    """Abstraction layer for stock data retrieval using yfinance."""
    
    def get_price(self, symbol: str, date: str) -> Dict[str, Any]:
        """
        Get stock price for a given symbol and date.
        
        Args:
            symbol: Stock symbol (e.g., 'AAPL', 'GOOGL')
            date: Date in YYYY-MM-DD format
            
        Returns:
            Dict with price information
            
        Raises:
            InvalidSymbolError: If symbol is invalid
            NoDataError: If no data exists for the symbol/date
            NetworkError: If network request fails
        """
        logger = logging.getLogger("stock_data")
        
        # Validate symbol format (basic validation)
        if not symbol or not isinstance(symbol, str):
            raise InvalidSymbolError(f"Invalid symbol: {symbol}")
        
        symbol = symbol.upper().strip()
        
        # Validate date format
        if not date or not isinstance(date, str):
            raise NoDataError(f"Invalid date format: {date}")
        
        try:
            # Create ticker object
            ticker = yf.Ticker(symbol)
            
            # Get historical data
            # We request a small range to get data for the specific date
            hist = ticker.history(start=date, end=date, auto_adjust=True)
            
            if hist.empty:
                # Try getting data for a few days around the date
                from datetime import datetime, timedelta
                target_date = datetime.strptime(date, "%Y-%m-%d")
                start = (target_date - timedelta(days=7)).strftime("%Y-%m-%d")
                end = (target_date + timedelta(days=7)).strftime("%Y-%m-%d")
                hist = ticker.history(start=start, end=end, auto_adjust=True)
                
                if hist.empty:
                    raise NoDataError(f"No data available for {symbol} around {date}")
            
            # Get the most relevant data point
            latest = hist.iloc[-1]
            
            return {
                "symbol": symbol,
                "date": date,
                "open": float(latest.get("Open", 0)),
                "high": float(latest.get("High", 0)),
                "low": float(latest.get("Low", 0)),
                "close": float(latest.get("Close", 0)),
                "volume": int(latest.get("Volume", 0)),
                "currency": ticker.info.get("currency", "USD")
            }
            
        except InvalidSymbolError:
            raise
        except NoDataError:
            raise
        except Exception as e:
            error_msg = str(e).lower()
            if "no data" in error_msg or "empty" in error_msg:
                raise NoDataError(f"No data available for {symbol} on {date}") from e
            else:
                raise NetworkError(f"Failed to fetch stock data for {symbol}: {str(e)}") from e


# Global instance
_stock_data_source: Optional[StockDataSource] = None


def get_stock_data_source() -> StockDataSource:
    """Get the global stock data source instance."""
    global _stock_data_source
    if _stock_data_source is None:
        _stock_data_source = StockDataSource()
    return _stock_data_source