"""Market data tool for fetching real stock/crypto prices."""

from datetime import datetime
from typing import Any

import httpx

from app.tools.base import Tool, ToolParameter, ToolResult, registry


class MarketDataTool(Tool):
    """Tool for fetching real market data via Yahoo Finance."""

    def __init__(self) -> None:
        super().__init__(
            id="market_data",
            name="Market Data",
            description="Fetch real market data (stocks, ETFs, crypto) from Yahoo Finance",
            parameters=[
                ToolParameter(
                    name="symbol",
                    type="string",
                    description="Ticker symbol (e.g., AAPL, BTC-USD, SPY)",
                ),
                ToolParameter(
                    name="period",
                    type="string",
                    description="Data period: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, max",
                    required=False,
                    default="1mo",
                ),
                ToolParameter(
                    name="interval",
                    type="string",
                    description="Data interval: 1m, 5m, 15m, 1h, 1d, 1wk, 1mo",
                    required=False,
                    default="1d",
                ),
            ],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Fetch market data from Yahoo Finance."""
        symbol = kwargs.get("symbol", "").upper()
        period = kwargs.get("period", "1mo")
        interval = kwargs.get("interval", "1d")

        if not symbol:
            return ToolResult(success=False, output="", error="No symbol provided")

        valid_periods = ["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "max"]
        valid_intervals = ["1m", "5m", "15m", "1h", "1d", "1wk", "1mo"]

        if period not in valid_periods:
            return ToolResult(success=False, output="", error=f"Invalid period. Use: {valid_periods}")
        if interval not in valid_intervals:
            return ToolResult(success=False, output="", error=f"Invalid interval. Use: {valid_intervals}")

        try:
            url = "https://query1.finance.yahoo.com/v8/finance/chart/" + symbol
            params = {"range": period, "interval": interval, "includePrePost": "false"}

            async with httpx.AsyncClient(timeout=30, verify=False) as client:
                resp = await client.get(url, params=params, headers={"User-Agent": "MaratOS/1.0"})
                resp.raise_for_status()
                data = resp.json()

            result = data.get("chart", {}).get("result", [])
            if not result:
                return ToolResult(success=False, output="", error=f"No data for symbol: {symbol}")

            chart = result[0]
            meta = chart.get("meta", {})
            timestamps = chart.get("timestamp", [])
            quote = chart.get("indicators", {}).get("quote", [{}])[0]

            opens = quote.get("open", [])
            highs = quote.get("high", [])
            lows = quote.get("low", [])
            closes = quote.get("close", [])
            volumes = quote.get("volume", [])

            # Build OHLCV data
            ohlcv = []
            for i, ts in enumerate(timestamps):
                if i < len(closes) and closes[i] is not None:
                    ohlcv.append({
                        "date": datetime.fromtimestamp(ts).isoformat(),
                        "open": opens[i] if i < len(opens) else None,
                        "high": highs[i] if i < len(highs) else None,
                        "low": lows[i] if i < len(lows) else None,
                        "close": closes[i],
                        "volume": volumes[i] if i < len(volumes) else None,
                    })

            current_price = meta.get("regularMarketPrice", closes[-1] if closes else None)
            prev_close = meta.get("previousClose", meta.get("chartPreviousClose"))

            output = f"**{symbol}** - {meta.get('longName', meta.get('shortName', symbol))}\n"
            if current_price:
                output += f"Current: ${current_price:.2f}"
                if prev_close:
                    change = current_price - prev_close
                    pct = (change / prev_close) * 100
                    output += f" ({'+' if change >= 0 else ''}{change:.2f}, {'+' if pct >= 0 else ''}{pct:.2f}%)"
            output += f"\nPeriod: {period}, Interval: {interval}, Data points: {len(ohlcv)}"

            return ToolResult(
                success=True,
                output=output,
                data={
                    "symbol": symbol,
                    "name": meta.get("longName", meta.get("shortName")),
                    "currency": meta.get("currency", "USD"),
                    "current_price": current_price,
                    "previous_close": prev_close,
                    "ohlcv": ohlcv,
                },
            )

        except httpx.HTTPStatusError as e:
            return ToolResult(success=False, output="", error=f"HTTP error: {e.response.status_code}")
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class QuoteTool(Tool):
    """Tool for fetching real-time quotes."""

    def __init__(self) -> None:
        super().__init__(
            id="quote",
            name="Quote",
            description="Get real-time quote for a symbol",
            parameters=[
                ToolParameter(
                    name="symbols",
                    type="string",
                    description="Comma-separated ticker symbols (e.g., AAPL,MSFT,GOOGL)",
                ),
            ],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Fetch real-time quotes."""
        symbols_str = kwargs.get("symbols", "")
        if not symbols_str:
            return ToolResult(success=False, output="", error="No symbols provided")

        symbols = [s.strip().upper() for s in symbols_str.split(",") if s.strip()]
        if not symbols:
            return ToolResult(success=False, output="", error="No valid symbols")

        try:
            # Use chart endpoint for each symbol (more reliable than quote endpoint)
            output_lines = []
            quote_data = []

            async with httpx.AsyncClient(timeout=30, verify=False) as client:
                for sym in symbols[:10]:  # Limit to 10 symbols
                    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
                    params = {"range": "1d", "interval": "1d"}
                    
                    resp = await client.get(url, params=params, headers={"User-Agent": "MaratOS/1.0"})
                    if resp.status_code != 200:
                        output_lines.append(f"**{sym}**: Error fetching data")
                        continue
                    
                    data = resp.json()
                    result = data.get("chart", {}).get("result", [])
                    if not result:
                        output_lines.append(f"**{sym}**: No data")
                        continue
                    
                    meta = result[0].get("meta", {})
                    price = meta.get("regularMarketPrice")
                    prev = meta.get("previousClose", meta.get("chartPreviousClose"))
                    name = meta.get("shortName", sym)
                    
                    line = f"**{sym}** ({name}): "
                    if price:
                        line += f"${price:.2f}"
                        if prev:
                            change = price - prev
                            pct = (change / prev) * 100
                            line += f" ({'+' if change >= 0 else ''}{change:.2f}, {'+' if pct >= 0 else ''}{pct:.2f}%)"
                    else:
                        line += "N/A"
                    
                    output_lines.append(line)
                    quote_data.append({
                        "symbol": sym,
                        "name": name,
                        "price": price,
                        "change": (price - prev) if price and prev else None,
                        "change_percent": ((price - prev) / prev * 100) if price and prev else None,
                        "volume": meta.get("regularMarketVolume"),
                    })

            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                data={"quotes": quote_data},
            )

        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


# Register tools
registry.register(MarketDataTool())
registry.register(QuoteTool())
