# ByBit&HyperLiquid WebSocket Integration

## Introduction

This project, `byBitHyperLiquid.py`, establishes WebSocket connections to both the Bybit and HyperLiquid trading platforms

## Compilation
* Compiled by writing in terminal `python byBitHyperLiquid.py`.

## Documentation 
* For Bybit documentation, refer to  https://bybit-exchange.github.io/docs/v5/websocket/public/orderbook  for the websocket API
* For Hyperliquid Documentation, refer to  https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/websocket for the websocket API.

## Variables
The symbols in Hyperliquid is showing the pattern such as ETH, BTC, DOGE and etc whilst the symbols in Bybit shows the pattern of 
BTCUSDT, ETHUSDT, DOGEUSDT which is given in Hyperliquid`symbols = ['ETH', 'BTC', 'DOGE', 'SOL']` and  for bybit `[f'{symbol}USDT' for symbol in sybmols]`.
