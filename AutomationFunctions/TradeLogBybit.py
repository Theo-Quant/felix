import ccxt
import pandas as pd
import pyodbc
import schedule
import time
from datetime import datetime, timedelta
# import config
import dummy_config as config
import sys
import traceback

logger = config.setup_logger('BybitTradeLog')

# Initialize the Bybit exchange using credentials from configGB.py
bybit = ccxt.bybit({
    'apiKey': config.BYBIT_API_KEY,
    'secret': config.BYBIT_SECRET_KEY,
    'enableRateLimit': True,
    'options': {'defaultType': 'swap'}
})

# Azure SQL Database connection details
driver = '{ODBC Driver 17 for SQL Server}'
server = 'theosql.database.windows.net'
database = 'arbitrage_db_2024-03-22T23-30Z'
username = 'THEOsql'
password = 'THEOBullRun2024!'

def fetch_usdt_perp_trades(exchange, since):
    all_trades = []
    exchange.load_markets()
    usdt_perp_symbols = [symbol for symbol in exchange.markets if 'USDT' in symbol and exchange.markets[symbol]['type'] == 'swap']
    for symbol in usdt_perp_symbols:
        print(f"Fetching trades for {symbol} on Bybit...")
        try:
            trades = exchange.fetch_my_trades(symbol=symbol, params={'since': since})
            if trades:
                all_trades.extend(trades)
        except Exception as e:
            print(f"Error fetching trades for {symbol} on Bybit: {e}")
    return all_trades

def clean_bybit_trades_df(df):
    if not df.empty:
        df['symbol'] = df['symbol']
        df['orderId'] = df['order']
        df['side'] = df['side']
        df['price'] = df['price']
        df['qty'] = df['amount']
        df['notional'] = df['cost']
        df['takerOrMaker'] = df['takerOrMaker']
        df['realizedPnl'] = df['info'].apply(lambda x: 0)
        df['commission'] = df['info'].apply(lambda x: float(x['execFee']))
        df['commissionAsset'] = df['fee'].apply(lambda x: x['currency'])
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
        df['instanceId'] = df['id']
        df['CliOrdId'] = df['info'].apply(lambda x: x['orderLinkId'])
        df.drop(columns=['fees', 'fee'], inplace=True)
        new_order = ['datetime', 'symbol', 'orderId', 'takerOrMaker', 'side', 'price', 'qty', 'notional', 'commission',
                     'commissionAsset', 'realizedPnl', 'info', 'instanceId', 'CliOrdId']
        df = df[new_order]
    return df


def upload_to_azure(df, table_name):
    if df.empty:
        print(f"No new trades to upload for {table_name}")
        return

    conn = pyodbc.connect(
        f'DRIVER={driver};SERVER={server};PORT=1433;DATABASE={database};UID={username};PWD={password}')
    cursor = conn.cursor()

    # Calculate the date 1 day ago
    one_day_ago = datetime.now(df['datetime'].dt.tz) - timedelta(days=1)

    # Filter the DataFrame to include only trades from the last day
    df_filtered = df[df['datetime'] >= one_day_ago]

    if df_filtered.empty:
        print(f"No new trades within the last day for {table_name}")
        return

    # Get all instanceIds from the filtered DataFrame
    instance_ids = df_filtered['instanceId'].tolist()

    # Check which instanceIds already exist in the database from the last day
    existing_ids = set()
    batch_size = 1000  # Adjust this value based on your database limitations

    for i in range(0, len(instance_ids), batch_size):
        batch = instance_ids[i:i+batch_size]
        placeholders = ','.join(['?' for _ in batch])
        check_query = f"""
            SELECT instanceId 
            FROM {table_name} 
            WHERE instanceId IN ({placeholders})
            AND datetime >= ?
        """
        try:
            cursor.execute(check_query, batch + [one_day_ago])
            existing_ids.update(row.instanceId for row in cursor.fetchall())
        except pyodbc.Error as e:
            print(f"Error checking existing IDs (batch {i//batch_size + 1}): {e}")
            print(f"SQL State: {e.args[1]}")
            conn.close()
            return

    # Insert only the new records
    insert_query = f"""
        INSERT INTO {table_name} (datetime, symbol, orderId, takerOrMaker, side, price, qty, notional, commission, commissionAsset, realizedPnl, info, instanceId, CliOrdId)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    new_records_count = 0
    for index, row in df_filtered.iterrows():
        if row['instanceId'] not in existing_ids:
            try:
                cursor.execute(insert_query,
                    row['datetime'], row['symbol'], row['orderId'], row['takerOrMaker'],
                    row['side'], row['price'], row['qty'], row['notional'], row['commission'],
                    row['commissionAsset'], row['realizedPnl'], str(row['info']), row['instanceId'], row['CliOrdId']
                )
                new_records_count += 1
            except pyodbc.Error as e:
                print(f"Error inserting row: {e}")
                print(f"Problematic row: {row}")
                conn.rollback()
                conn.close()
                return

    try:
        conn.commit()
    except pyodbc.Error as e:
        print(f"Error committing transaction: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

    print(f"Data uploaded to {table_name}. {new_records_count} new records inserted.")

def run_trading_bot():
    now = datetime.now()
    since = now - timedelta(hours=1, minutes=30)
    since_timestamp = int(since.timestamp() * 1000)

    print("Fetching Bybit USDT perpetual futures trades...")
    bybit_trades = fetch_usdt_perp_trades(bybit, since_timestamp)
    bybit_trades = [trade for trade in bybit_trades if trade['timestamp'] >= since_timestamp]

    bybit_df = pd.DataFrame(bybit_trades)
    bybit_df = clean_bybit_trades_df(bybit_df)
    print(bybit_df.columns)
    print(bybit_df.dtypes)
    print(bybit_df.head())
    print(bybit_df.isnull().sum())
    upload_to_azure(bybit_df, 'BybitTrades')

def main():
    while True:
        try:
            logger.info(f"Bybit Trading Log restarted")
            schedule.every(1).minutes.do(run_trading_bot)
            run_trading_bot()

            while True:
                schedule.run_pending()
                time.sleep(1)
        except Exception as e:
            logger.error(f"An error occurred: {e} Restarting in 60 seconds...")
            traceback.print_exc()
            time.sleep(60)
            continue

if __name__ == "__main__":
    main()