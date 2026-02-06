from config import exchange

print("Loading markets...")
markets = exchange.load_markets()
print("OK. Markets loaded:", len(markets))
