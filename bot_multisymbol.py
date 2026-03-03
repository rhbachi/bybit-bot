if signal and not s["in_position"]:
    price = df.iloc[-1].close

    qty = calculate_position_size(
        CAPITAL,
        RISK_PER_TRADE,
        STOP_LOSS_PCT,
        price,
        LEVERAGE,
    )

    qty = adjust_qty_to_min_notional(symbol, qty, price)

    if qty <= 0:
        continue

    # ===== CALCUL SL / TP =====
    if signal == "long":
        stop_loss = price * (1 - STOP_LOSS_PCT)
        sl_distance = price - stop_loss
        take_profit = price + sl_distance * RR_MULTIPLIER
    else:
        stop_loss = price * (1 + STOP_LOSS_PCT)
        sl_distance = stop_loss - price
        take_profit = price - sl_distance * RR_MULTIPLIER

    # ===== Precision SAFE =====
    stop_loss = float(exchange.price_to_precision(symbol, stop_loss))
    take_profit = float(exchange.price_to_precision(symbol, take_profit))
    qty = float(exchange.amount_to_precision(symbol, qty))

    exchange.create_market_order(
        symbol,
        "buy" if signal == "long" else "sell",
        qty,
        params={
            "stopLoss": stop_loss,
            "takeProfit": take_profit,
            "slTriggerBy": "LastPrice",
            "tpTriggerBy": "LastPrice",
        },
    )

    s["in_position"] = True
    s["trades_today"] += 1
    s["last_trade_time"] = time.time()

    print(
        f"📈 TRADE OUVERT | {symbol} | {signal.upper()} | "
        f"Entry={round(price,2)} | SL={stop_loss} | TP={take_profit} | Qty={qty}",
        flush=True,
    )

    send_telegram(
        f"📈 TRADE OUVERT\n"
        f"Pair: {symbol}\n"
        f"Direction: {signal.upper()}\n"
        f"Entry: {round(price,2)}\n"
        f"SL: {stop_loss}\n"
        f"TP: {take_profit}\n"
        f"Qty: {qty}"
    )