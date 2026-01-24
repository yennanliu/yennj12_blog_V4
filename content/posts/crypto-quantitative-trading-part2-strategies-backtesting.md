---
title: "Crypto Quantitative Trading Part 2: Advanced Strategies and Backtesting Framework"
date: 2026-01-24T21:00:00+08:00
draft: false
authors: ["yen"]
categories: ["all", "engineering", "finance"]
tags: ["Cryptocurrency", "Bitcoin", "Ethereum", "Backtesting", "Trading Strategies", "Risk Management", "Python", "Portfolio Optimization", "Mean Reversion", "Trend Following"]
summary: "Build production-ready cryptocurrency trading strategies with comprehensive backtesting. Learn trend following, mean reversion, pairs trading, and arbitrage strategies. Master risk management, position sizing, and performance evaluation with real Bitcoin and Ethereum examples."
description: "Advanced guide to cryptocurrency trading strategy development and backtesting. Implement multiple strategy types, build robust backtesting frameworks, apply proper risk management, and evaluate performance with industry-standard metrics. Complete with Python implementations."
readTime: "28 min"
---

In Part 1, we established the fundamentals of cryptocurrency quantitative trading and built data collection infrastructure. Now we'll develop actual trading strategies and build a robust backtesting framework to evaluate their performance before risking real capital.

## Why Backtesting is Critical

```
The #1 Rule of Quantitative Trading:

"Never trade a strategy with real money
until you've thoroughly backtested it."

Why?
- Most strategies that sound good fail in practice
- Backtesting reveals hidden risks and edge cases
- Proper testing prevents catastrophic losses
- Statistical validation builds confidence
```

### **The Danger of Overfitting**

```python
# Example: Overfitted vs Robust Strategy

# ❌ Overfitted (curve-fit to historical data)
def overfitted_strategy():
    """
    Buy when:
    - RSI crosses 31.7 (not 30 or 32)
    - MACD histogram > 42.3
    - Hour of day is 14 or 23
    - Day of month is prime number

    This likely worked great on historical data
    but will fail miserably going forward.
    """
    pass

# ✅ Robust (based on sound principles)
def robust_strategy():
    """
    Buy when:
    - Oversold (RSI < 30)
    - Positive momentum (MACD positive)
    - Simple, interpretable rules
    - Works across multiple timeframes

    This strategy has economic rationale
    and is likely to generalize to new data.
    """
    pass
```

## Building a Backtesting Framework

### **Core Architecture**

```python
from dataclasses import dataclass
from typing import List, Dict, Optional
from enum import Enum
import pandas as pd
import numpy as np
from datetime import datetime

class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"

class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"

@dataclass
class Order:
    """Represents a trading order"""
    timestamp: datetime
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: Optional[float] = None  # For limit orders
    filled_price: Optional[float] = None
    filled_quantity: float = 0.0
    status: str = "pending"  # pending, filled, cancelled
    commission: float = 0.0

@dataclass
class Position:
    """Represents a trading position"""
    symbol: str
    quantity: float
    entry_price: float
    entry_time: datetime
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0

@dataclass
class Trade:
    """Represents a completed trade"""
    entry_time: datetime
    exit_time: datetime
    symbol: str
    side: OrderSide
    entry_price: float
    exit_price: float
    quantity: float
    pnl: float
    pnl_percent: float
    commission: float
    duration: float  # hours

class BacktestEngine:
    """
    Core backtesting engine
    """

    def __init__(self, initial_capital: float = 100000,
                 commission_rate: float = 0.001,
                 slippage: float = 0.0005):
        """
        Initialize backtesting engine

        initial_capital: Starting capital in USD
        commission_rate: Commission per trade (0.001 = 0.1%)
        slippage: Estimated slippage (0.0005 = 0.05%)
        """
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.commission_rate = commission_rate
        self.slippage = slippage

        self.positions: Dict[str, Position] = {}
        self.orders: List[Order] = []
        self.trades: List[Trade] = []
        self.equity_curve: List[Dict] = []

        self.current_time = None
        self.current_prices: Dict[str, float] = {}

    def update_time(self, timestamp: datetime, prices: Dict[str, float]):
        """Update current time and prices"""
        self.current_time = timestamp
        self.current_prices = prices

        # Update position values
        for symbol, position in self.positions.items():
            if symbol in prices:
                position.current_price = prices[symbol]
                position.unrealized_pnl = (
                    (position.current_price - position.entry_price) *
                    position.quantity
                )

        # Record equity
        total_equity = self.calculate_total_equity()
        self.equity_curve.append({
            'timestamp': timestamp,
            'capital': self.capital,
            'position_value': total_equity - self.capital,
            'total_equity': total_equity,
        })

    def calculate_total_equity(self) -> float:
        """Calculate total portfolio equity"""
        position_value = sum(
            pos.quantity * pos.current_price
            for pos in self.positions.values()
        )
        return self.capital + position_value

    def place_order(self, symbol: str, side: OrderSide,
                    quantity: float, order_type: OrderType = OrderType.MARKET,
                    limit_price: Optional[float] = None) -> Order:
        """
        Place an order

        Returns: Order object
        """
        order = Order(
            timestamp=self.current_time,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=limit_price,
        )

        # Execute market orders immediately
        if order_type == OrderType.MARKET:
            self._execute_order(order)

        self.orders.append(order)
        return order

    def _execute_order(self, order: Order):
        """Execute an order"""
        if order.symbol not in self.current_prices:
            order.status = "rejected"
            return

        # Calculate execution price with slippage
        current_price = self.current_prices[order.symbol]
        if order.side == OrderSide.BUY:
            execution_price = current_price * (1 + self.slippage)
        else:
            execution_price = current_price * (1 - self.slippage)

        # Calculate costs
        order_value = order.quantity * execution_price
        commission = order_value * self.commission_rate

        # Check if we have enough capital (for buy orders)
        if order.side == OrderSide.BUY:
            total_cost = order_value + commission
            if total_cost > self.capital:
                order.status = "rejected"
                return

        # Execute the order
        order.filled_price = execution_price
        order.filled_quantity = order.quantity
        order.commission = commission
        order.status = "filled"

        # Update positions
        if order.side == OrderSide.BUY:
            self._open_position(order)
        else:
            self._close_position(order)

    def _open_position(self, order: Order):
        """Open or add to a position"""
        if order.symbol in self.positions:
            # Add to existing position (average entry price)
            pos = self.positions[order.symbol]
            total_quantity = pos.quantity + order.filled_quantity
            total_cost = (
                pos.entry_price * pos.quantity +
                order.filled_price * order.filled_quantity
            )
            pos.entry_price = total_cost / total_quantity
            pos.quantity = total_quantity
        else:
            # Create new position
            self.positions[order.symbol] = Position(
                symbol=order.symbol,
                quantity=order.filled_quantity,
                entry_price=order.filled_price,
                entry_time=order.timestamp,
                current_price=order.filled_price,
            )

        # Update capital
        self.capital -= (order.filled_quantity * order.filled_price + order.commission)

    def _close_position(self, order: Order):
        """Close or reduce a position"""
        if order.symbol not in self.positions:
            order.status = "rejected"
            return

        pos = self.positions[order.symbol]

        # Calculate P&L
        pnl = (order.filled_price - pos.entry_price) * order.filled_quantity
        pnl -= order.commission

        # Create trade record
        trade = Trade(
            entry_time=pos.entry_time,
            exit_time=order.timestamp,
            symbol=order.symbol,
            side=OrderSide.BUY,  # Position side
            entry_price=pos.entry_price,
            exit_price=order.filled_price,
            quantity=order.filled_quantity,
            pnl=pnl,
            pnl_percent=(order.filled_price / pos.entry_price - 1) * 100,
            commission=order.commission,
            duration=(order.timestamp - pos.entry_time).total_seconds() / 3600,
        )
        self.trades.append(trade)

        # Update capital
        self.capital += (order.filled_quantity * order.filled_price - order.commission)

        # Update or remove position
        pos.quantity -= order.filled_quantity
        pos.realized_pnl += pnl

        if pos.quantity <= 0:
            del self.positions[order.symbol]

    def get_position(self, symbol: str) -> Optional[Position]:
        """Get current position for a symbol"""
        return self.positions.get(symbol)

    def get_equity_curve(self) -> pd.DataFrame:
        """Get equity curve as DataFrame"""
        return pd.DataFrame(self.equity_curve).set_index('timestamp')

    def get_trades_df(self) -> pd.DataFrame:
        """Get all trades as DataFrame"""
        if not self.trades:
            return pd.DataFrame()

        return pd.DataFrame([vars(t) for t in self.trades])
```

### **Strategy Base Class**

```python
from abc import ABC, abstractmethod

class TradingStrategy(ABC):
    """
    Base class for trading strategies
    """

    def __init__(self, name: str):
        self.name = name
        self.params = {}

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """
        Generate trading signals

        Returns: Series with values -1 (sell), 0 (hold), 1 (buy)
        """
        pass

    @abstractmethod
    def calculate_position_size(self, signal: float, capital: float,
                                current_price: float) -> float:
        """
        Calculate position size for a signal

        Returns: Position size (quantity)
        """
        pass

    def set_params(self, **kwargs):
        """Update strategy parameters"""
        self.params.update(kwargs)

    def get_description(self) -> str:
        """Get strategy description"""
        return f"{self.name} with params: {self.params}"
```

## Trading Strategy #1: Trend Following

### **Moving Average Crossover Strategy**

```python
class MovingAverageCrossover(TradingStrategy):
    """
    Classic trend following strategy using moving average crossovers

    Buy: Fast MA crosses above Slow MA
    Sell: Fast MA crosses below Slow MA
    """

    def __init__(self, fast_period=20, slow_period=50, atr_period=14):
        super().__init__("MA Crossover")
        self.params = {
            'fast_period': fast_period,
            'slow_period': slow_period,
            'atr_period': atr_period,
        }

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """Generate signals based on MA crossover"""
        fast = df['close'].ewm(span=self.params['fast_period']).mean()
        slow = df['close'].ewm(span=self.params['slow_period']).mean()

        # Generate crossover signals
        signals = pd.Series(0, index=df.index)

        # Buy signal: Fast crosses above Slow
        signals[(fast > slow) & (fast.shift() <= slow.shift())] = 1

        # Sell signal: Fast crosses below Slow
        signals[(fast < slow) & (fast.shift() >= slow.shift())] = -1

        return signals

    def calculate_position_size(self, signal: float, capital: float,
                                current_price: float) -> float:
        """
        Calculate position size using fixed fractional method

        Risk 2% of capital per trade
        """
        if signal == 0:
            return 0.0

        risk_per_trade = capital * 0.02
        position_value = capital * 0.95  # Use 95% of capital max

        # Calculate quantity
        quantity = min(
            position_value / current_price,
            risk_per_trade / (current_price * 0.02)  # 2% stop loss
        )

        return quantity

# Example usage
def backtest_ma_crossover(df: pd.DataFrame, initial_capital=100000):
    """
    Backtest MA Crossover strategy
    """
    # Initialize
    engine = BacktestEngine(initial_capital=initial_capital)
    strategy = MovingAverageCrossover(fast_period=20, slow_period=50)

    # Generate signals
    signals = strategy.generate_signals(df)

    # Run backtest
    position = None

    for timestamp, row in df.iterrows():
        # Update engine
        engine.update_time(timestamp, {'BTC/USDT': row['close']})

        signal = signals.loc[timestamp]

        # Get current position
        current_pos = engine.get_position('BTC/USDT')

        # Execute signals
        if signal == 1 and current_pos is None:
            # Buy signal and no position
            quantity = strategy.calculate_position_size(
                signal,
                engine.capital,
                row['close']
            )
            engine.place_order('BTC/USDT', OrderSide.BUY, quantity)

        elif signal == -1 and current_pos is not None:
            # Sell signal and have position
            engine.place_order(
                'BTC/USDT',
                OrderSide.SELL,
                current_pos.quantity
            )

    return engine

# Run backtest
from crypto_quantitative_trading_part1_fundamentals import CryptoDataCollector

collector = CryptoDataCollector('binance')
df = collector.fetch_historical_data('BTC/USDT', '1h', '2023-01-01', '2024-01-01')

# Add indicators
from crypto_quantitative_trading_part1_fundamentals import TrendIndicators
df['sma_20'] = TrendIndicators.sma(df['close'], 20)
df['sma_50'] = TrendIndicators.sma(df['close'], 50)

# Backtest
result = backtest_ma_crossover(df)
equity = result.get_equity_curve()
trades = result.get_trades_df()

print(f"\nBacktest Results:")
print(f"Initial Capital: ${result.initial_capital:,.2f}")
print(f"Final Equity: ${result.calculate_total_equity():,.2f}")
print(f"Total Return: {(result.calculate_total_equity() / result.initial_capital - 1) * 100:.2f}%")
print(f"Number of Trades: {len(trades)}")
```

### **Trend Following with ADX Filter**

```python
class ADXTrendFollowing(TradingStrategy):
    """
    Enhanced trend following with ADX filter

    Only trade when trend is strong (ADX > threshold)
    """

    def __init__(self, fast_period=12, slow_period=26, adx_period=14, adx_threshold=25):
        super().__init__("ADX Trend Following")
        self.params = {
            'fast_period': fast_period,
            'slow_period': slow_period,
            'adx_period': adx_period,
            'adx_threshold': adx_threshold,
        }

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """Generate signals with ADX filter"""
        from crypto_quantitative_trading_part1_fundamentals import TrendIndicators

        # Calculate indicators
        fast = df['close'].ewm(span=self.params['fast_period']).mean()
        slow = df['close'].ewm(span=self.params['slow_period']).mean()
        adx, plus_di, minus_di = TrendIndicators.adx(
            df['high'], df['low'], df['close'], self.params['adx_period']
        )

        # Generate signals
        signals = pd.Series(0, index=df.index)

        # Only trade when ADX indicates strong trend
        strong_trend = adx > self.params['adx_threshold']

        # Buy: Fast > Slow AND ADX > threshold AND +DI > -DI
        buy_condition = (
            (fast > slow) &
            (fast.shift() <= slow.shift()) &
            strong_trend &
            (plus_di > minus_di)
        )
        signals[buy_condition] = 1

        # Sell: Fast < Slow OR ADX weakening
        sell_condition = (
            (fast < slow) &
            (fast.shift() >= slow.shift())
        ) | (adx < self.params['adx_threshold'] * 0.7)

        signals[sell_condition] = -1

        return signals

    def calculate_position_size(self, signal: float, capital: float,
                                current_price: float) -> float:
        """Kelly Criterion based position sizing"""
        if signal == 0:
            return 0.0

        # Simplified Kelly: f = (p * b - q) / b
        # Assuming 55% win rate, 1.5:1 reward:risk
        win_rate = 0.55
        reward_risk = 1.5

        kelly_fraction = (win_rate * reward_risk - (1 - win_rate)) / reward_risk
        kelly_fraction = max(0, min(kelly_fraction, 0.25))  # Cap at 25%

        position_value = capital * kelly_fraction
        quantity = position_value / current_price

        return quantity
```

## Trading Strategy #2: Mean Reversion

### **Bollinger Band Mean Reversion**

```python
class BollingerMeanReversion(TradingStrategy):
    """
    Mean reversion strategy using Bollinger Bands

    Buy: Price touches lower band (oversold)
    Sell: Price reaches middle band or upper band
    """

    def __init__(self, bb_period=20, bb_std=2.0, rsi_period=14):
        super().__init__("Bollinger Mean Reversion")
        self.params = {
            'bb_period': bb_period,
            'bb_std': bb_std,
            'rsi_period': rsi_period,
        }

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """Generate mean reversion signals"""
        from crypto_quantitative_trading_part1_fundamentals import (
            VolatilityIndicators, MomentumIndicators
        )

        # Calculate indicators
        bb_middle, bb_upper, bb_lower = VolatilityIndicators.bollinger_bands(
            df['close'],
            self.params['bb_period'],
            self.params['bb_std']
        )
        rsi = MomentumIndicators.rsi(df['close'], self.params['rsi_period'])

        # Calculate Bollinger Band position
        bb_position = (df['close'] - bb_lower) / (bb_upper - bb_lower)

        signals = pd.Series(0, index=df.index)

        # Buy: Price at lower band AND RSI oversold
        buy_condition = (
            (bb_position < 0.1) &  # Near lower band
            (rsi < 30) &  # Oversold
            (df['close'] > df['close'].shift())  # Starting to bounce
        )
        signals[buy_condition] = 1

        # Sell: Price at middle band or upper band
        sell_condition = (
            (bb_position > 0.5) |  # Above middle
            (rsi > 70)  # Overbought
        )
        signals[sell_condition] = -1

        return signals

    def calculate_position_size(self, signal: float, capital: float,
                                current_price: float) -> float:
        """
        Fixed fractional position sizing
        Risk 1% per trade (mean reversion is riskier)
        """
        if signal == 0:
            return 0.0

        risk_per_trade = capital * 0.01
        position_value = capital * 0.5  # Max 50% of capital

        quantity = min(
            position_value / current_price,
            risk_per_trade / (current_price * 0.03)  # 3% stop loss
        )

        return quantity
```

### **RSI Mean Reversion with Volume Confirmation**

```python
class RSIVolumeMeanReversion(TradingStrategy):
    """
    Mean reversion using RSI with volume confirmation

    Buy: RSI oversold + volume spike (capitulation)
    Sell: RSI overbought + volume spike (exhaustion)
    """

    def __init__(self, rsi_period=14, volume_period=20, volume_threshold=1.5):
        super().__init__("RSI Volume Mean Reversion")
        self.params = {
            'rsi_period': rsi_period,
            'volume_period': volume_period,
            'volume_threshold': volume_threshold,
        }

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """Generate RSI + Volume signals"""
        from crypto_quantitative_trading_part1_fundamentals import MomentumIndicators

        # Calculate RSI
        rsi = MomentumIndicators.rsi(df['close'], self.params['rsi_period'])

        # Calculate volume ratio
        avg_volume = df['volume'].rolling(self.params['volume_period']).mean()
        volume_ratio = df['volume'] / avg_volume

        signals = pd.Series(0, index=df.index)

        # Buy: RSI < 30 + Volume spike (panic selling)
        buy_condition = (
            (rsi < 30) &
            (volume_ratio > self.params['volume_threshold'])
        )
        signals[buy_condition] = 1

        # Sell: RSI > 70 + Volume spike (FOMO buying)
        sell_condition = (
            (rsi > 70) &
            (volume_ratio > self.params['volume_threshold'])
        )
        signals[sell_condition] = -1

        return signals

    def calculate_position_size(self, signal: float, capital: float,
                                current_price: float) -> float:
        """Scale position by signal strength"""
        if signal == 0:
            return 0.0

        base_size = capital * 0.02 / current_price
        return base_size
```

## Trading Strategy #3: Pairs Trading

### **Bitcoin-Ethereum Pairs Strategy**

```python
class BTCETHPairsTrad(TradingStrategy):
    """
    Statistical arbitrage between BTC and ETH

    Trade the spread between BTC/ETH ratio and its mean
    """

    def __init__(self, lookback_period=30, entry_z_score=2.0, exit_z_score=0.5):
        super().__init__("BTC-ETH Pairs Trading")
        self.params = {
            'lookback_period': lookback_period,
            'entry_z_score': entry_z_score,
            'exit_z_score': exit_z_score,
        }

    def generate_signals(self, btc_df: pd.DataFrame, eth_df: pd.DataFrame) -> Dict:
        """
        Generate pairs trading signals

        Returns: Dict with 'btc_signal' and 'eth_signal'
        """
        # Calculate BTC/ETH ratio
        ratio = btc_df['close'] / eth_df['close']

        # Calculate rolling statistics
        period = self.params['lookback_period']
        ratio_mean = ratio.rolling(period).mean()
        ratio_std = ratio.rolling(period).std()

        # Calculate z-score
        z_score = (ratio - ratio_mean) / ratio_std

        # Generate signals
        btc_signals = pd.Series(0, index=btc_df.index)
        eth_signals = pd.Series(0, index=eth_df.index)

        # When z-score is high: BTC overvalued, ETH undervalued
        # Short BTC, Long ETH
        overvalued = z_score > self.params['entry_z_score']
        btc_signals[overvalued] = -1
        eth_signals[overvalued] = 1

        # When z-score is low: BTC undervalued, ETH overvalued
        # Long BTC, Short ETH
        undervalued = z_score < -self.params['entry_z_score']
        btc_signals[undervalued] = 1
        eth_signals[undervalued] = -1

        # Exit when z-score returns to mean
        exit_long = (z_score < self.params['exit_z_score']) & (z_score.shift() >= self.params['exit_z_score'])
        exit_short = (z_score > -self.params['exit_z_score']) & (z_score.shift() <= -self.params['exit_z_score'])

        btc_signals[exit_long | exit_short] = 0
        eth_signals[exit_long | exit_short] = 0

        return {
            'btc_signal': btc_signals,
            'eth_signal': eth_signals,
            'z_score': z_score,
        }

    def calculate_position_size(self, signal: float, capital: float,
                                current_price: float) -> float:
        """Equal dollar weighting for pairs"""
        if signal == 0:
            return 0.0

        # Use 50% of capital for each leg
        position_value = capital * 0.5
        quantity = position_value / current_price

        return quantity
```

## Risk Management

### **Stop Loss and Take Profit**

```python
class RiskManager:
    """
    Comprehensive risk management system
    """

    def __init__(self, max_position_size=0.3, max_daily_loss=0.02,
                 stop_loss=0.05, take_profit=0.15):
        """
        max_position_size: Maximum fraction of capital per position
        max_daily_loss: Maximum daily loss (fraction of capital)
        stop_loss: Stop loss percentage (0.05 = 5%)
        take_profit: Take profit percentage (0.15 = 15%)
        """
        self.max_position_size = max_position_size
        self.max_daily_loss = max_daily_loss
        self.stop_loss = stop_loss
        self.take_profit = take_profit

        self.daily_pnl = 0.0
        self.daily_start_capital = 0.0
        self.last_reset_date = None

    def check_stop_loss(self, position: Position) -> bool:
        """Check if position hit stop loss"""
        if position.quantity == 0:
            return False

        pnl_percent = (position.current_price / position.entry_price - 1)
        return pnl_percent <= -self.stop_loss

    def check_take_profit(self, position: Position) -> bool:
        """Check if position hit take profit"""
        if position.quantity == 0:
            return False

        pnl_percent = (position.current_price / position.entry_price - 1)
        return pnl_percent >= self.take_profit

    def check_daily_loss_limit(self, current_capital: float,
                               current_date: datetime) -> bool:
        """Check if daily loss limit reached"""
        # Reset daily tracking at start of new day
        if self.last_reset_date is None or current_date.date() != self.last_reset_date:
            self.daily_start_capital = current_capital
            self.daily_pnl = 0.0
            self.last_reset_date = current_date.date()

        # Calculate daily loss
        daily_loss = (current_capital - self.daily_start_capital) / self.daily_start_capital

        return daily_loss <= -self.max_daily_loss

    def validate_position_size(self, quantity: float, price: float,
                               total_capital: float) -> float:
        """
        Validate and adjust position size

        Returns: Adjusted quantity
        """
        position_value = quantity * price
        max_value = total_capital * self.max_position_size

        if position_value > max_value:
            quantity = max_value / price

        return quantity

    def calculate_optimal_stop_loss(self, entry_price: float,
                                    atr: float, atr_multiplier: float = 2.0) -> float:
        """
        Calculate optimal stop loss based on ATR

        atr: Average True Range
        atr_multiplier: Number of ATRs for stop
        """
        stop_distance = atr * atr_multiplier
        stop_price = entry_price - stop_distance

        return stop_price

# Enhanced backtesting with risk management
def backtest_with_risk_management(df: pd.DataFrame, strategy: TradingStrategy,
                                  initial_capital: float = 100000):
    """
    Backtest strategy with comprehensive risk management
    """
    engine = BacktestEngine(initial_capital=initial_capital)
    risk_manager = RiskManager(
        max_position_size=0.3,
        max_daily_loss=0.02,
        stop_loss=0.05,
        take_profit=0.15
    )

    # Calculate ATR for stop loss
    from crypto_quantitative_trading_part1_fundamentals import VolatilityIndicators
    df['atr'] = VolatilityIndicators.atr(df['high'], df['low'], df['close'])

    # Generate signals
    signals = strategy.generate_signals(df)

    # Run backtest
    for timestamp, row in df.iterrows():
        # Update engine
        engine.update_time(timestamp, {'BTC/USDT': row['close']})

        # Check daily loss limit
        if risk_manager.check_daily_loss_limit(engine.capital, timestamp):
            # Stop trading for the day
            continue

        current_pos = engine.get_position('BTC/USDT')

        # Check stop loss / take profit
        if current_pos is not None:
            current_pos.current_price = row['close']

            if risk_manager.check_stop_loss(current_pos):
                # Hit stop loss - close position
                engine.place_order('BTC/USDT', OrderSide.SELL, current_pos.quantity)
                continue

            if risk_manager.check_take_profit(current_pos):
                # Hit take profit - close position
                engine.place_order('BTC/USDT', OrderSide.SELL, current_pos.quantity)
                continue

        # Process signals
        signal = signals.loc[timestamp]

        if signal == 1 and current_pos is None:
            # Buy signal
            quantity = strategy.calculate_position_size(
                signal, engine.capital, row['close']
            )

            # Validate position size
            quantity = risk_manager.validate_position_size(
                quantity, row['close'], engine.capital
            )

            if quantity > 0:
                engine.place_order('BTC/USDT', OrderSide.BUY, quantity)

        elif signal == -1 and current_pos is not None:
            # Sell signal
            engine.place_order('BTC/USDT', OrderSide.SELL, current_pos.quantity)

    return engine
```

## Performance Evaluation

### **Key Performance Metrics**

```python
class PerformanceAnalyzer:
    """
    Calculate comprehensive performance metrics
    """

    @staticmethod
    def calculate_metrics(equity_curve: pd.DataFrame,
                         trades_df: pd.DataFrame,
                         initial_capital: float,
                         risk_free_rate: float = 0.04) -> Dict:
        """
        Calculate all performance metrics

        risk_free_rate: Annual risk-free rate (default 4%)
        """
        if equity_curve.empty or trades_df.empty:
            return {}

        # Total return
        final_equity = equity_curve['total_equity'].iloc[-1]
        total_return = (final_equity / initial_capital - 1) * 100

        # Period
        days = (equity_curve.index[-1] - equity_curve.index[0]).days
        years = days / 365.25

        # Annualized return
        annualized_return = ((final_equity / initial_capital) ** (1/years) - 1) * 100

        # Returns series
        returns = equity_curve['total_equity'].pct_change().dropna()

        # Volatility
        daily_vol = returns.std()
        annualized_vol = daily_vol * np.sqrt(365 * 24) * 100  # For hourly data

        # Sharpe Ratio
        excess_return = annualized_return / 100 - risk_free_rate
        sharpe_ratio = excess_return / (annualized_vol / 100) if annualized_vol > 0 else 0

        # Maximum Drawdown
        cumulative = (1 + returns).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max
        max_drawdown = drawdown.min() * 100

        # Win Rate
        winning_trades = len(trades_df[trades_df['pnl'] > 0])
        total_trades = len(trades_df)
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0

        # Average Win/Loss
        avg_win = trades_df[trades_df['pnl'] > 0]['pnl'].mean() if winning_trades > 0 else 0
        avg_loss = trades_df[trades_df['pnl'] < 0]['pnl'].mean() if total_trades - winning_trades > 0 else 0

        # Profit Factor
        total_wins = trades_df[trades_df['pnl'] > 0]['pnl'].sum()
        total_losses = abs(trades_df[trades_df['pnl'] < 0]['pnl'].sum())
        profit_factor = total_wins / total_losses if total_losses > 0 else 0

        # Expectancy
        expectancy = (win_rate / 100 * avg_win) - ((1 - win_rate / 100) * abs(avg_loss))

        # Sortino Ratio (downside deviation)
        downside_returns = returns[returns < 0]
        downside_std = downside_returns.std() * np.sqrt(365 * 24)
        sortino_ratio = excess_return / downside_std if downside_std > 0 else 0

        # Calmar Ratio
        calmar_ratio = (annualized_return / 100) / abs(max_drawdown / 100) if max_drawdown != 0 else 0

        return {
            'initial_capital': initial_capital,
            'final_equity': final_equity,
            'total_return': total_return,
            'annualized_return': annualized_return,
            'annualized_volatility': annualized_vol,
            'sharpe_ratio': sharpe_ratio,
            'sortino_ratio': sortino_ratio,
            'calmar_ratio': calmar_ratio,
            'max_drawdown': max_drawdown,
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': total_trades - winning_trades,
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'expectancy': expectancy,
        }

    @staticmethod
    def print_metrics(metrics: Dict):
        """Print metrics in readable format"""
        print("\n" + "="*60)
        print("PERFORMANCE METRICS")
        print("="*60)

        print(f"\nCapital:")
        print(f"  Initial: ${metrics['initial_capital']:,.2f}")
        print(f"  Final: ${metrics['final_equity']:,.2f}")

        print(f"\nReturns:")
        print(f"  Total Return: {metrics['total_return']:.2f}%")
        print(f"  Annualized Return: {metrics['annualized_return']:.2f}%")
        print(f"  Annualized Volatility: {metrics['annualized_volatility']:.2f}%")

        print(f"\nRisk-Adjusted Returns:")
        print(f"  Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")
        print(f"  Sortino Ratio: {metrics['sortino_ratio']:.2f}")
        print(f"  Calmar Ratio: {metrics['calmar_ratio']:.2f}")
        print(f"  Maximum Drawdown: {metrics['max_drawdown']:.2f}%")

        print(f"\nTrade Statistics:")
        print(f"  Total Trades: {metrics['total_trades']}")
        print(f"  Winning Trades: {metrics['winning_trades']}")
        print(f"  Losing Trades: {metrics['losing_trades']}")
        print(f"  Win Rate: {metrics['win_rate']:.2f}%")

        print(f"\nPer-Trade Metrics:")
        print(f"  Average Win: ${metrics['avg_win']:.2f}")
        print(f"  Average Loss: ${metrics['avg_loss']:.2f}")
        print(f"  Profit Factor: {metrics['profit_factor']:.2f}")
        print(f"  Expectancy: ${metrics['expectancy']:.2f}")

        print("="*60 + "\n")

# Example usage
result = backtest_with_risk_management(df, MovingAverageCrossover())
equity = result.get_equity_curve()
trades = result.get_trades_df()

metrics = PerformanceAnalyzer.calculate_metrics(
    equity, trades, result.initial_capital
)
PerformanceAnalyzer.print_metrics(metrics)
```

## Complete Example: Strategy Comparison

```python
def compare_strategies(df: pd.DataFrame, strategies: List[TradingStrategy],
                      initial_capital: float = 100000):
    """
    Compare multiple strategies side-by-side
    """
    results = {}

    for strategy in strategies:
        print(f"\nBacktesting {strategy.name}...")

        # Run backtest
        engine = backtest_with_risk_management(df, strategy, initial_capital)

        # Get results
        equity = engine.get_equity_curve()
        trades = engine.get_trades_df()

        # Calculate metrics
        metrics = PerformanceAnalyzer.calculate_metrics(
            equity, trades, initial_capital
        )

        results[strategy.name] = {
            'engine': engine,
            'metrics': metrics,
        }

    # Print comparison
    print("\n" + "="*80)
    print("STRATEGY COMPARISON")
    print("="*80)

    # Create comparison DataFrame
    comparison = pd.DataFrame({
        name: result['metrics']
        for name, result in results.items()
    }).T

    print(comparison[[
        'total_return',
        'annualized_return',
        'sharpe_ratio',
        'max_drawdown',
        'win_rate',
        'total_trades'
    ]])

    return results

# Compare strategies
strategies = [
    MovingAverageCrossover(fast_period=20, slow_period=50),
    ADXTrendFollowing(fast_period=12, slow_period=26),
    BollingerMeanReversion(bb_period=20, bb_std=2.0),
    RSIVolumeMeanReversion(rsi_period=14),
]

comparison = compare_strategies(df, strategies)
```

## Conclusion and Next Steps

In Part 2, we've built a complete backtesting framework and implemented multiple trading strategies:

- ✅ Robust backtesting engine with realistic costs
- ✅ Multiple strategy types (trend following, mean reversion, pairs trading)
- ✅ Comprehensive risk management
- ✅ Professional performance metrics
- ✅ Strategy comparison framework

### **Key Takeaways**

1. **Always Backtest**: Never trade without thorough testing
2. **Account for Costs**: Slippage and commissions significantly impact results
3. **Manage Risk**: Stop losses and position sizing are crucial
4. **Compare Strategies**: No single strategy works in all market conditions
5. **Avoid Overfitting**: Simple, robust strategies outperform complex curve-fit ones

### **Coming Up in Part 3**

In the final post, we'll focus on production deployment and optimization:

- Walk-forward analysis and out-of-sample testing
- Parameter optimization without overfitting
- Live trading integration with exchange APIs
- Real-time monitoring and alerting
- Portfolio management across multiple strategies
- Machine learning for strategy enhancement

### **Practice Exercises**

```python
# Exercise 1: Implement your own strategy
# Create a strategy combining multiple indicators

# Exercise 2: Optimize parameters
# Find optimal parameters for MovingAverageCrossover using walk-forward analysis

# Exercise 3: Multi-asset strategy
# Create a strategy that trades both BTC and ETH

# Exercise 4: Advanced risk management
# Implement trailing stop loss and position scaling

# Exercise 5: Strategy ensemble
# Combine multiple strategies with dynamic weighting
```

**Continue to Part 3**: [Crypto Quantitative Trading Part 3: Optimization and Production Deployment](#)

---

*Questions about backtesting or strategies? Drop them in the comments! In Part 3, we'll deploy these strategies to production.*
