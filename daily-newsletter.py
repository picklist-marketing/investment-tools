#!/usr/bin/env python3
"""
デイリーニュースレター
- 朝7:00: 米国市場の結果 + 保有株 + ニュース
- 夜21:00: 日本市場まとめ + 保有株 + ニュース
- LINE Messaging APIで配信
"""

import yfinance as yf
import json
import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import sys

# ===== 設定 =====
CONFIG_FILE = "market-alert-config.json"
POSITIONS_FILE = "market-positions.json"


def load_config():
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)


def load_positions():
    if os.path.exists(POSITIONS_FILE):
        with open(POSITIONS_FILE, 'r') as f:
            return json.load(f)
    return []


def send_line_message(config, message):
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN") or config["line"]["channel_access_token"]
    user_id = os.environ.get("LINE_USER_ID") or config["line"]["user_id"]
    if not token or not user_id:
        return False
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    # LINE は1メッセージ5000文字まで
    payload = {
        "to": user_id,
        "messages": [{"type": "text", "text": message[:5000]}],
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        print(f"  LINE送信失敗: {e}")
        return False


# ===== マーケットデータ =====
def get_index_data():
    indices = {
        "S&P 500": "^GSPC",
        "NASDAQ": "^IXIC",
        "ダウ": "^DJI",
        "日経225": "^N225",
        "VIX": "^VIX",
    }
    results = {}
    for name, ticker in indices.items():
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="5d")
            if len(hist) >= 2:
                prev = float(hist['Close'].iloc[-2])
                curr = float(hist['Close'].iloc[-1])
                chg = (curr - prev) / prev * 100
                results[name] = {"price": curr, "change": chg}
            elif len(hist) >= 1:
                curr = float(hist['Close'].iloc[-1])
                results[name] = {"price": curr, "change": 0}
        except:
            pass
    return results


def get_forex():
    try:
        t = yf.Ticker("JPY=X")
        hist = t.history(period="5d")
        if len(hist) >= 2:
            prev = float(hist['Close'].iloc[-2])
            curr = float(hist['Close'].iloc[-1])
            chg = (curr - prev) / prev * 100
            return {"price": curr, "change": chg}
        elif len(hist) >= 1:
            return {"price": float(hist['Close'].iloc[-1]), "change": 0}
    except:
        pass
    return None


def get_portfolio_status():
    positions = load_positions()
    results = []
    for pos in positions:
        try:
            t = yf.Ticker(pos["ticker"])
            hist = t.history(period="5d")
            if len(hist) >= 1:
                curr = float(hist['Close'].iloc[-1])
                entry = pos["entry_price"]
                pnl_pct = (curr - entry) / entry * 100
                pnl_amount = (curr - entry) * pos["shares"]
                results.append({
                    "name": pos["name"],
                    "ticker": pos["ticker"],
                    "current": curr,
                    "entry": entry,
                    "shares": pos["shares"],
                    "pnl_pct": pnl_pct,
                    "pnl_amount": pnl_amount,
                })
        except:
            pass
    return results


# ===== ニュース取得（Google News RSS）=====
def fetch_news(query, max_items=4):
    url = f"https://news.google.com/rss/search?q={requests.utils.quote(query)}&hl=ja&gl=JP&ceid=JP:ja"
    try:
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        root = ET.fromstring(resp.content)
        items = []
        for item in root.findall('.//item')[:max_items]:
            title = item.find('title').text or ""
            # ソース名を分離（"記事タイトル - ロイター" → タイトル部分だけ）
            if ' - ' in title:
                title, source = title.rsplit(' - ', 1)
                title = f"{title}（{source}）"
            items.append(title)
        return items
    except:
        return []


# ===== ニュースレター組み立て =====
def format_index(name, data):
    if name == "VIX":
        level = "穏やか" if data["price"] < 15 else "やや不安" if data["price"] < 25 else "警戒"
        return f"  VIX（恐怖指数）: {data['price']:.1f}（{level}）"
    sign = "+" if data["change"] >= 0 else ""
    arrow = "↑" if data["change"] > 0 else "↓" if data["change"] < 0 else "→"
    return f"  {arrow} {name}: {data['price']:,.0f}（{sign}{data['change']:.1f}%）"


def format_portfolio(portfolio):
    lines = []
    total_pnl_jpy = 0
    fx = get_forex()
    rate = fx["price"] if fx else 150

    for p in portfolio:
        sign = "+" if p["pnl_pct"] >= 0 else ""
        icon = "🟢" if p["pnl_pct"] >= 0 else "🔴"
        is_jp = p["ticker"].endswith(".T")
        name = p["name"]

        if is_jp:
            pnl_jpy = p["pnl_amount"]
            lines.append(
                f"  {icon} {name}  ¥{p['current']:,.0f}\n"
                f"     {sign}{p['pnl_pct']:.1f}% / {sign}¥{pnl_jpy:,.0f}"
            )
        else:
            pnl_jpy = p["pnl_amount"] * rate
            lines.append(
                f"  {icon} {p['ticker']}  ${p['current']:.2f}\n"
                f"     {sign}{p['pnl_pct']:.1f}% / {sign}${p['pnl_amount']:.2f}（{sign}¥{pnl_jpy:,.0f}）"
            )
        total_pnl_jpy += pnl_jpy

    sign = "+" if total_pnl_jpy >= 0 else ""
    lines.append(f"  ─────────")
    lines.append(f"  合計損益: {sign}¥{total_pnl_jpy:,.0f}")
    return lines


def build_morning():
    today = datetime.now().strftime("%m/%d(%a)")
    lines = [f"☀️ おはようございます！ {today}", ""]

    # 米国市場
    indices = get_index_data()
    lines.append("━━ 📊 昨夜の米国市場 ━━")
    for name in ["S&P 500", "NASDAQ", "ダウ", "VIX"]:
        if name in indices:
            lines.append(format_index(name, indices[name]))
    lines.append("")

    # 為替
    fx = get_forex()
    if fx:
        sign = "+" if fx["change"] >= 0 else ""
        direction = "円安↗" if fx["change"] > 0.05 else "円高↘" if fx["change"] < -0.05 else "横ばい→"
        lines.append(f"━━ 💱 為替 ━━")
        lines.append(f"  USD/JPY: {fx['price']:.2f}（{sign}{fx['change']:.1f}% {direction}）")
        lines.append("")

    # 保有株
    portfolio = get_portfolio_status()
    if portfolio:
        lines.append("━━ 📈 あなたの保有株 ━━")
        lines.extend(format_portfolio(portfolio))
        lines.append("")

    # ニュース
    biz = fetch_news("経済 マーケット 株式", 4)
    if biz:
        lines.append("━━ 📰 ビジネス/経済 ━━")
        for i, n in enumerate(biz, 1):
            lines.append(f"  {i}. {n}")
        lines.append("")

    tech = fetch_news("AI 半導体 テクノロジー", 3)
    if tech:
        lines.append("━━ 💡 テック/AI ━━")
        for i, n in enumerate(tech, 1):
            lines.append(f"  {i}. {n}")
        lines.append("")

    lines.append("良い1日を！")
    return "\n".join(lines)


def build_evening():
    today = datetime.now().strftime("%m/%d(%a)")
    lines = [f"🌙 お疲れ様です！ {today}", ""]

    indices = get_index_data()

    # 日本市場
    lines.append("━━ 📊 日本市場 ━━")
    if "日経225" in indices:
        lines.append(format_index("日経225", indices["日経225"]))
    lines.append("")

    # 米国市場
    lines.append("━━ 📊 米国市場 ━━")
    for name in ["S&P 500", "NASDAQ", "ダウ", "VIX"]:
        if name in indices:
            lines.append(format_index(name, indices[name]))
    lines.append("")

    # 為替
    fx = get_forex()
    if fx:
        sign = "+" if fx["change"] >= 0 else ""
        direction = "円安↗" if fx["change"] > 0.05 else "円高↘" if fx["change"] < -0.05 else "横ばい→"
        lines.append(f"━━ 💱 為替 ━━")
        lines.append(f"  USD/JPY: {fx['price']:.2f}（{sign}{fx['change']:.1f}% {direction}）")
        lines.append("")

    # 保有株
    portfolio = get_portfolio_status()
    if portfolio:
        lines.append("━━ 📈 あなたの保有株 ━━")
        lines.extend(format_portfolio(portfolio))
        lines.append("")

    # ニュース
    biz = fetch_news("経済 ビジネス", 4)
    if biz:
        lines.append("━━ 📰 ビジネス/経済 ━━")
        for i, n in enumerate(biz, 1):
            lines.append(f"  {i}. {n}")
        lines.append("")

    tech = fetch_news("AI 半導体 テクノロジー", 3)
    if tech:
        lines.append("━━ 💡 テック/AI ━━")
        for i, n in enumerate(tech, 1):
            lines.append(f"  {i}. {n}")
        lines.append("")

    lines.append("おやすみなさい 🌙")
    return "\n".join(lines)


# ===== メイン =====
def main():
    if len(sys.argv) < 2:
        print("""
📬 デイリーニュースレター

使い方:
  python3 ~/daily-newsletter.py morning   # 朝のニュースレター送信
  python3 ~/daily-newsletter.py evening   # 夜のニュースレター送信
  python3 ~/daily-newsletter.py test      # テスト（LINEに送信）
  python3 ~/daily-newsletter.py preview   # プレビュー（送信しない）
""")
        return

    cmd = sys.argv[1]

    if cmd == "preview":
        print(build_morning())
        print("\n" + "=" * 50 + "\n")
        print(build_evening())
        return

    config = load_config()

    if cmd in ("morning", "test"):
        msg = build_morning()
    elif cmd == "evening":
        msg = build_evening()
    else:
        print("Unknown command. Use: morning, evening, test, preview")
        return

    print(msg)
    print("\n" + "=" * 50)

    if config["notify"]["line_enabled"]:
        success = send_line_message(config, msg)
        print("✅ LINE送信完了" if success else "❌ LINE送信失敗")
    else:
        print("⚠️ LINE通知が無効です。setup-lineで設定してください")


if __name__ == "__main__":
    main()
