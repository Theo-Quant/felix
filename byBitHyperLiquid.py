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
symbols = ['BTC', 'SOL', 'ETH'] # for hyperliquid
# hyperliquid_message = {
#     "method": "subscribe",
#     "subscription":{ "type": "l2Book", "coin": "BTC" }
# }
orderbook_data = list()
latest_data = {symbol: {
    'hyperliquid': {'bids': defaultdict(float), 'asks': defaultdict(float), 'time': 0},
    'bybit': {
        stream_type: {'bids': [], 'asks': [], 'time': None}
        for stream_type in bybit_stream_types
    },
    'local_orderbook': {'bids': [], 'asks': [], 'time': None}
} for symbol in symbols}
last_process_time = {symbol: 0 for symbol in symbols}
#done
def update_local_orderbook(symbol, stream_type, new_data): #confirmed
    local_ob = latest_data[symbol]['local_orderbook']

    def update_side(side, new_levels):
        current_levels = {price: size for price, size in local_ob[side]}
        for price, size in new_levels:
            if size == 0:
                current_levels.pop(price, None)
            else:
                current_levels[price] = size

        sorted_levels = sorted(current_levels.items(), key=lambda x: -x[0] if side == 'bids' else x[0])
        return sorted_levels[:5]

    if stream_type == 'books5':
        # Replace the entire local orderbook with books5 data
        local_ob['bids'] = new_data['bids']
        local_ob['asks'] = new_data['asks']
    else:
        # Update the local orderbook with new data
        local_ob['bids'] = update_side('bids', new_data['bids'])
        local_ob['asks'] = update_side('asks', new_data['asks'])

    # Ensure we always have 5 levels for both bids and asks
    while len(local_ob['bids']) < 5:
        local_ob['bids'].append((0, 0))
    while len(local_ob['asks']) < 5:
        local_ob['asks'].append((float('inf'), 0))

    local_ob['time'] = new_data['time']
def get_timestamp(): #confirmed
    return int(time.time())
def sign(message, secret_key): #confirmed
    mac = hmac.new(bytes(secret_key, encoding='utf8'), bytes(message, encoding='utf-8'), digestmod='sha256')
    d = mac.digest()
    return base64.b64encode(d)

class RateLimiter: #confirmed
    def __init__(self, interval):
        self.interval = interval
        self.last_check = {}

    def should_process(self, symbol):
        current_time = time.time()
        if symbol not in self.last_check or current_time - self.last_check[symbol] >= self.interval:
            self.last_check[symbol] = current_time
            return True
        return False
def handle_message(message):
    logging.info(f"Received message: {message}")
def get_current_utc_time_with_ms(): #confirmed
    now = datetime.now(timezone.utc)
    return now.isoformat(timespec='milliseconds')
def round_significant_digits(value, significant_digits): #confirmed
    if value == 0:
        return 0
    d = Decimal(value)
    rounded_value = d.scaleb(-d.adjusted()).quantize(Decimal(10) ** -significant_digits, rounding=ROUND_HALF_UP).scaleb(d.adjusted())
    return float(rounded_value)
def get_current_time_ms(): #confirmed
    return int(time.time() * 1000)

rate_limiter = RateLimiter(interval=0.025)
def calculate_impact_price(order_book, imn): #confirmed
    accumulated_notional = 0.0
    accumulated_quantity = 0.0

    for price, quantity in order_book:
        notional = price * quantity
        accumulated_notional += notional
        accumulated_quantity += quantity

        if accumulated_notional >= imn:
            remaining_notional = imn - (accumulated_notional - notional)
            remaining_quantity = remaining_notional / price
            impact_price = imn / (accumulated_quantity - quantity + remaining_quantity)
            return impact_price

    # orderbook_data.append(message["data"])
    #TODO1
async def hyperliquid_websocket_handler(ws_url, symbol, stream_type): # return  [level1, level2] such that levels = [px(price), sz(size), n(number of trades)] , levels1 = bid, levels2 = ask
    hyperliquid_message = {
        "method": "subscribe",
        "subscription": {"type": "l2Book", "coin": symbol}
    }
    try:
        # Connect to the WebSocket server
        async with websockets.connect(ws_url) as websocket:
            logging.info("Connected to Hyperliquid WebSocket")

            # Send subscription message
            await websocket.send(json.dumps(hyperliquid_message))
            logging.info("Sent subscription message: %s", json.dumps(hyperliquid_message))

            # Receive data from WebSocket
            while True:
                data = await websocket.recv()
                # logging.info("Received data: %s", data)
                handle_message(data)


    except Exception as e:
        logging.error("Error: %s", str(e))
#TODO2
def process_hyperliquid_message(symbol, stream_type, message):
    pass
def get_top_n(order_dict, n=5, reverse=False): #confirmed
    sorted_orders = sorted(order_dict.items(), key=lambda x: float(x[0]), reverse=reverse)
    return [(float(price), float(quantity)) for price, quantity in sorted_orders[:n]]
def cleanup_orderbook(symbol): #confirmed
    current_time = time.time()
    cutoff_time = current_time - 300  # Remove entries older than 5 minutes

    for book_type in ['bids', 'asks']:
        latest_data[symbol]['bybit'][book_type] = {
            price: qty for price, qty in latest_data[symbol]['bybit'][book_type].items()
                if latest_data[symbol]['binance']['time'] > cutoff_time
        }
#TODO3
def process_bybit_message(symbol, message):
    pass
#TODO4
async def bybit_websocket_handler(symbol) : #returns dict('b':[bid price, bid size], 'a':[ask_price, ask_size])
    ws = WebSocket(
        testnet=False,
        channel_type="linear",
    )
    ws.orderbook_stream(
        depth=50,
        symbol="SOLUSDT",
        callback=handle_message)
# Run the asyncio event loop
# asyncio.run(hyperliquid_stream())
# asyncio.run(bybit_stream())
#TODO5
def process_data(symbol):
    pass
async def main():
    tasks = []
    for symbol in symbols:
        for stream_type in hyperliquid_stream_types:
            tasks.append(hyperliquid_websocket_handler(hyperliquid_ws_url , symbol, stream_type))

        tasks.append(bybit_websocket_handler(symbol))

    await asyncio.gather(*tasks)

async def run():
    while True:
        try:
            await main()
        except Exception as e:
            logging.error(f"Error occurred: {e}")
            logging.info("Restarting the script...")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(run())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Script terminated by user")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {str(e)}")
        logging.info("Restarting the script...")