import asyncio
import websockets
import json
import time
import redis
import logging
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone
from collections import defaultdict
import config
import hmac
import base64
from pybit.unified_trading import WebSocket


#basic log info files
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s:%(message)s',
    handlers=[
        logging.FileHandler("websocketByHyper.log"),
        logging.StreamHandler()
    ]
)
redis_client = redis.Redis(host='localhost', port=6379, db=0)
# bybit_ws_url = "wss://stream.bybit.com/realtime" # maybe do not need it
hyperliquid_ws_url = "wss://api.hyperliquid.xyz/ws"
hyperliquid_stream_types = ['l2Book']
bybit_stream_types = [1, 50, 200, 500] # need to find the stream for this one the depth, use the websocket for this
symbol = ['BTC', 'SOL', 'ETH'] # for hyperliquid
hyper_message = {
    "method": "subscribe",
    "subscription":{ "type": "l2Book", "coin": "BTC" }
}
orderbook_data = list()
def handle_message(message):
    logging.info(f"Received message: {message}")
    # orderbook_data.append(message["data"])
async def hyperliquid_stream(): # return  [level1, level2] such that levels = [px(price), sz(size), n(number of trades)] , levels1 = bid, levels2 = ask
    try:
        # Connect to the WebSocket server
        async with websockets.connect(hyperliquid_ws_url) as websocket:
            logging.info("Connected to Hyperliquid WebSocket")

            # Send subscription message
            await websocket.send(json.dumps(hyper_message))
            logging.info("Sent subscription message: %s", json.dumps(hyper_message))

            # Receive data from WebSocket
            while True:
                data = await websocket.recv()
                # logging.info("Received data: %s", data)
                handle_message(data)


    except Exception as e:
        logging.error("Error: %s", str(e))
async def bybit_stream(): #returns dict('b':[bid price, bid size], 'a':[ask_price, ask_size])
    ws = WebSocket(
        testnet=False,
        channel_type="linear",
    )
    ws.orderbook_stream(
        depth=50,
        symbol="SOLUSDT",
        callback=handle_message)
# Run the asyncio event loop
asyncio.run(hyperliquid_stream())
# asyncio.run(bybit_stream())