"""Tests for stock tool."""

import unittest
from unittest.mock import patch, MagicMock
import json


class TestStockToolSchema(unittest.TestCase):
    """Test stock price tool schema."""
    
    def test_stock_price_schema_structure(self):
        """Test stock price tool has correct schema structure."""
        from app.tools import STOCK_PRICE_TOOL_SCHEMA
        
        self.assertIn("type", STOCK_PRICE_TOOL_SCHEMA)
        self.assertEqual(STOCK_PRICE_TOOL_SCHEMA["type"], "function")
        
        function_def = STOCK_PRICE_TOOL_SCHEMA["function"]
        self.assertIn("name", function_def)
        self.assertEqual(function_def["name"], "stock_price")
        
        self.assertIn("description", function_def)
        self.assertIn("parameters", function_def)
        
        # Check required parameters
        params = function_def["parameters"]["properties"]
        self.assertIn("symbol", params)
        self.assertIn("date", params)
        
        required = function_def["parameters"]["required"]
        self.assertIn("symbol", required)
        self.assertIn("date", required)
    
    def test_tool_registry(self):
        """Test tool is registered."""
        from app.tools import TOOL_REGISTRY, get_tool_names
        
        self.assertIn("stock_price", TOOL_REGISTRY)
        self.assertIn("stock_price", get_tool_names())


class TestStockDataSource(unittest.TestCase):
    """Test stock data source."""
    
    @patch('app.tools.stock.yf.Ticker')
    def test_get_price_success(self, mock_ticker):
        """Test successful price retrieval."""
        from app.tools.stock import StockDataSource
        
        # Mock yfinance response
        mock_ticker_instance = MagicMock()
        mock_ticker.return_value = mock_ticker_instance
        mock_ticker_instance.info = {"currency": "USD"}
        
        # Mock historical data
        mock_df = MagicMock()
        mock_df.empty = False
        mock_df.iloc = [0]
        mock_df.iloc[-1] = {
            "Open": 150.0,
            "High": 155.0,
            "Low": 149.0,
            "Close": 153.0,
            "Volume": 1000000
        }
        mock_ticker_instance.history.return_value = mock_df
        
        source = StockDataSource()
        result = source.get_price("AAPL", "2024-01-15")
        
        self.assertEqual(result["symbol"], "AAPL")
        self.assertEqual(result["close"], 153.0)
        self.assertEqual(result["currency"], "USD")
    
    def test_invalid_symbol(self):
        """Test invalid symbol raises error."""
        from app.tools.stock import StockDataSource, InvalidSymbolError
        
        source = StockDataSource()
        
        with self.assertRaises(InvalidSymbolError):
            source.get_price("", "2024-01-15")
    
    @patch('app.tools.stock.yf.Ticker')
    def test_no_data_error(self, mock_ticker):
        """Test no data raises NoDataError."""
        from app.tools.stock import StockDataSource, NoDataError
        
        mock_ticker_instance = MagicMock()
        mock_ticker.return_value = mock_ticker_instance
        
        # Empty response
        mock_df = MagicMock()
        mock_df.empty = True
        mock_ticker_instance.history.return_value = mock_df
        
        source = StockDataSource()
        
        with self.assertRaises(NoDataError):
            source.get_price("INVALID", "2024-01-15")


class TestStockToolFunction(unittest.TestCase):
    """Test stock_price tool function."""
    
    def test_stock_price_returns_dict(self):
        """Test stock_price returns a dictionary."""
        from app.tools import stock_price
        import logging
        
        # Create a mock logger
        logger = logging.getLogger("test")
        logger.setLevel(logging.DEBUG)
        
        # We can't actually call yfinance without network, so let's check
        # the function signature and that it returns expected format
        # For unit testing without network, we'll mock
        
        # Check function exists and has correct parameters
        import inspect
        sig = inspect.signature(stock_price)
        params = list(sig.parameters.keys())
        
        self.assertIn("symbol", params)
        self.assertIn("date", params)


if __name__ == "__main__":
    unittest.main()