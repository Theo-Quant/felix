import ccxt
import pandas as pd
from datetime import datetime, timedelta
import pytz
import redis
import schedule
import time
import json
import config
from sqlalchemy import create_engine
from sqlalchemy.types import DateTime, Float, String

# Shortened coin list for simplicity
coins_list = config.IN_TRADE
redis_client = redis.Redis(host='localhost', port=6379, db=0)


# Azure SQL Database connection details
driver = 'ODBC Driver 17 for SQL Server'
server = 'theosql.database.windows.net'
database = 'arbitrage_db_2024-03-22T23-30Z'
username = 'THEOsql'
password = 'THEOBullRun2024!'


# Initialize exchanges
binance = ccxt.binance({'enableRateLimit': True, 'options': {'defaultType': 'future'}})
okx = ccxt.okx({'enableRateLimit': True, 'options': {'defaultType': 'swap'}})

def convert_to_okx_symbol(symbol):
    base, quote = symbol.split('/')
    return f"{base}-{quote}-SWAP"

def fetch_current_funding_rate(exchange, symbol):
    try:
        if exchange.id == 'okx':
            symbol = convert_to_okx_symbol(symbol)

        funding_rate_data = exchange.fetch_funding_rate(symbol)
        # print(f"Fetched funding rate for {symbol} on {exchange.id}: {funding_rate_data}")

        funding_rate = funding_rate_data.get('fundingRate', None)
        timestamp = funding_rate_data.get('timestamp', None)

        if exchange.id == 'binance':
            next_funding_time = funding_rate_data['info'].get('nextFundingTime', None)
        else:
            next_funding_time = funding_rate_data['info'].get('fundingTime', None)

        return {
            'funding_rate': funding_rate*100,
            'next_funding_time': next_funding_time,
            'timestamp': timestamp
        }
    except Exception as e:
        print(f"Error fetching current rate for {symbol} on {exchange.id}: {str(e)}")
        return None


def calculate_time_weighted_adjustment(binance_fr, okx_fr, current_time, next_funding_time):
    # Calculate the number of minutes left until the next funding time
    minutes_left = (next_funding_time - current_time).total_seconds() / 60
    if minutes_left > 240:
        return 0
    elif minutes_left < 240:
        weight = (240 - minutes_left)/240
        divergence = okx_fr - binance_fr
        return weight * divergence


def process_and_collect_data(coins_list):
    all_data = []
    utc = pytz.UTC

    for coin in coins_list:
        # print(f"\nProcessing data for {coin}")

        # Fetch current data for both exchanges
        binance_data = fetch_current_funding_rate(binance, f'{coin}/USDT')
        okx_data = fetch_current_funding_rate(okx, f'{coin}/USDT')

        if not binance_data or not okx_data:
            print(f"No data available for {coin} on one or both exchanges")
            continue

        # Handle None values for timestamps and convert to UTC
        binance_timestamp = pd.to_datetime(binance_data['timestamp'], unit='ms').tz_localize(utc) if binance_data['timestamp'] else None
        okx_timestamp = pd.to_datetime(okx_data['timestamp'], unit='ms').tz_localize(utc) if okx_data['timestamp'] else None
        current_time = max(filter(None, [binance_timestamp, okx_timestamp]))

        # Determine next funding time and convert to UTC
        binance_next_funding_time = pd.to_datetime(pd.to_numeric(binance_data['next_funding_time'], errors='coerce'), unit='ms').tz_localize(utc) if binance_data['next_funding_time'] else None
        okx_next_funding_time = pd.to_datetime(pd.to_numeric(okx_data['next_funding_time'], errors='coerce'), unit='ms').tz_localize(utc) if okx_data['next_funding_time'] else None

        # Determine if we are in a 4/8 funding period by comparing the difference between the two time to fundings
        binance_time_diff = (binance_next_funding_time - current_time).total_seconds()
        okx_time_diff = (okx_next_funding_time - current_time).total_seconds()

        # If the time to funding is different then that means we should only be looking at the fr for the exchange that is next to payout.
        if binance_time_diff < okx_time_diff:
            okx_fr_adjusted = 0
            binance_fr_adjusted = binance_data['funding_rate']
        elif okx_time_diff > binance_time_diff:
            okx_fr_adjusted = okx_data['funding_rate']
            binance_fr_adjusted = 0
        else:
            okx_fr_adjusted = okx_data['funding_rate']
            binance_fr_adjusted = binance_data['funding_rate']


        # Calculate the time-weighted funding rate adjustment factor
        next_funding_time = binance_next_funding_time if binance_next_funding_time else okx_next_funding_time
        fr_adjustment_factor = - calculate_time_weighted_adjustment(binance_fr_adjusted, okx_fr_adjusted, current_time, next_funding_time)
        fr_divergence = okx_fr_adjusted - binance_fr_adjusted

        # Create a DataFrame for this coin
        df = pd.DataFrame({
            'timestamp': [current_time],
            'coin': [coin],
            'binance_fr': [binance_data['funding_rate']],
            'okx_fr': [okx_data['funding_rate']],
            'binance_next_funding': [binance_next_funding_time],
            'okx_next_funding': [okx_next_funding_time],
            'funding_divergence': fr_divergence,
            'fr_adjustment_factor': [fr_adjustment_factor],
            'okx_adjustment_factor': [okx_fr_adjusted],
            'binance_adjustment_factor': [binance_fr_adjusted],

        })

        # Append to all_data list
        all_data.append(df)

    # Concatenate all DataFrames
    df_all = pd.concat(all_data, ignore_index=True)
    df_all = df_all.sort_values(by=['funding_divergence'])

    return df_all


def export_to_redis(df):
    for index, row in df.iterrows():
        coin = row['coin']
        # Convert the row to a JSON string
        json_data = row.to_json()
        # Store the JSON string in Redis under the key for the specific coin
        redis_client.set(f'funding_rates:{coin}', json_data)
    print(f"Data exported to Redis successfully at {datetime.now()}")


def scheduled_task():
    df_all = process_and_collect_data(coins_list)
    print("\nFunding Rates for All Coins:")
    print(df_all.to_string(index=False))

    # Export the data to Redis
    export_to_redis(df_all)


def main():
    while True:
        try:
            # Run the task immediately
            scheduled_task()
            # Schedule the task to run every 5 minutes
            schedule.every(5).minutes.do(scheduled_task)
            # Keep the script running
            while True:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            print("FRAdjustmentFactor shutting down...")
            break  # Exit the outer loop on keyboard interrupt
        except Exception as e:
            # Log the error
            logger.exception("An error occurred: %s", str(e))
            print(f"An error occurred: {str(e)}. Restarting in 5 seconds...")
            time.sleep(5)  # Wait for 5 seconds before restarting
            # The outer loop will restart the process


if __name__ == "__main__":
    logger = config.setup_logger('FRAdjustmentFactor')
    main()