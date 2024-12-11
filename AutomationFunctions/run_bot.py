from HighFrequencyBotV3 import TradingBot, asyncio

bot_configs = [
    # {'symbol': 'CTC', 'notional_per_trade': 50, 'bot_id': 'CTC', 'max_notional': 250},
    # {'symbol': 'FTM', 'notional_per_trade': 50, 'bot_id': 'FTM', 'max_notional': 250},
    # {'symbol': 'DOGE', 'notional_per_trade': 50, 'bot_id': 'DOGE', 'max_notional': 250}
    {'symbol': 'DOGS', 'notional_per_trade': 50, 'bot_id': 'DOGS', 'max_notional': 250},
    {'symbol': 'XRP', 'notional_per_trade': 50, 'bot_id': 'XRP', 'max_notional': 250},
]


async def run_bots():
    bots = [TradingBot(**config) for config in bot_configs]
    try:
        await asyncio.gather(*(bot.main() for bot in bots))
    finally:
        for bot in bots:
            bot.csv_logger.close()


def main():
    try:
        asyncio.run(run_bots())
    except KeyboardInterrupt:
        print("run_bot shutting down...")


if __name__ == "__main__":
    main()