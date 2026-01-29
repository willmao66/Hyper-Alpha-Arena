"""
Exchange adapters for multi-exchange support.

This module provides a unified interface for interacting with different
cryptocurrency exchanges. Each exchange has its own adapter that handles
data fetching, format conversion, and order execution.

Supported exchanges:
- Hyperliquid (existing, native implementation)
- Binance (new, via adapter)
"""

from .base_adapter import BaseExchangeAdapter
from .symbol_mapper import SymbolMapper

__all__ = ["BaseExchangeAdapter", "SymbolMapper"]
