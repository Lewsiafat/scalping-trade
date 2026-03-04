import urllib.request
import json
import ssl
import os

def fetch_symbols(url):
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
            data = json.loads(response.read().decode())
            return set(s['symbol'] for s in data['symbols'] if s['status'] == 'TRADING' and s['quoteAsset'] == 'USDT')
    except Exception as e:
        print(f"Error fetching symbols from {url}: {e}")
        return set()

def update_supported_symbols():
    try:
        spot_url = 'https://api.binance.com/api/v3/exchangeInfo'
        futures_url = 'https://fapi.binance.com/fapi/v1/exchangeInfo'

        spot_symbols = fetch_symbols(spot_url)
        futures_symbols = fetch_symbols(futures_url)
        
        # Combine and sort to get a clean, unique list of supported symbols
        all_symbols = sorted(list(spot_symbols.union(futures_symbols)))
            
        if all_symbols:
            # Save to a local JSON file that the backend can serve
            with open('supported_symbols.json', 'w', encoding='utf-8') as f:
                json.dump(all_symbols, f, ensure_ascii=False)
            print(f"Successfully saved {len(all_symbols)} active USDT pairs (Spot + Futures) to supported_symbols.json")
        else:
            print("No symbols fetched. Please check API connectivity.")

    except Exception as e:
        print(f"Error updating symbols: {e}")

if __name__ == '__main__':
    update_supported_symbols()

