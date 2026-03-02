#!/usr/bin/env python3
"""
ポジション監視 & 売買アラートシステム
- 保有ポジションの損切り/利確ラインを監視
- テクニカル売りシグナルを検出
- LINE Messaging APIで即時通知
- cronで定期実行（平日9:00-15:00 日本株、23:30-6:00 米国株）
"""

import yfinance as yf
import pandas as pd
import json
import os
import sys
import requests
from datetime import datetime, timedelta

# ===== 設定ファイルパス =====
CONFIG_FILE = "market-alert-config.json"
POSITIONS_FILE = "market-positions.json"
ALERT_LOG_FILE = "market-alert-log.json"

# ===== デフォルト設定 =====
DEFAULT_CONFIG = {
    "line": {
        "channel_access_token": "",
        "user_id": "",
    },
    "rules": {
        "stop_loss_pct": -8,        # 損切りライン（%）
        "target_profit_pct": 15,     # 利確ライン（%）
        "trailing_stop_pct": -5,     # トレーリングストップ（高値から%）
        "rsi_sell_threshold": 75,    # RSIがこれ以上で売り警告
        "macd_death_cross": True,    # MACDデッドクロスで警告
        "bb_upper_warn": True,       # BB上限で警告
    },
    "notify": {
        "line_enabled": False,
        "mac_notify": True,          # macOS通知（フォールバック）
    }
}


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    save_config(DEFAULT_CONFIG)
    return DEFAULT_CONFIG


def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def load_positions():
    if os.path.exists(POSITIONS_FILE):
        with open(POSITIONS_FILE, 'r') as f:
            return json.load(f)
    return []


def save_positions(positions):
    with open(POSITIONS_FILE, 'w') as f:
        json.dump(positions, f, ensure_ascii=False, indent=2)


# ===== 通知 =====
def send_line_message(config, message):
    """LINE Messaging APIでプッシュ通知（環境変数優先）"""
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN") or config["line"]["channel_access_token"]
    user_id = os.environ.get("LINE_USER_ID") or config["line"]["user_id"]

    if not token or not user_id:
        return False

    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    payload = {
        "to": user_id,
        "messages": [{"type": "text", "text": message}],
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        if resp.status_code == 200:
            return True
        else:
            print(f"  LINE送信エラー: {resp.status_code} {resp.text}")
            return False
    except Exception as e:
        print(f"  LINE送信失敗: {e}")
        return False


def send_mac_notification(title, message):
    """macOS通知"""
    try:
        os.system(f'''osascript -e 'display notification "{message}" with title "{title}" sound name "Glass"' ''')
        return True
    except:
        return False


def notify(config, title, message):
    """統合通知（LINE + macOS）"""
    full_message = f"📊 {title}\n\n{message}"
    sent = False

    if config["notify"]["line_enabled"]:
        sent = send_line_message(config, full_message)
        if sent:
            print(f"  ✅ LINE通知送信済み")

    if config["notify"]["mac_notify"]:
        send_mac_notification(title, message[:200])
        if not sent:
            print(f"  ✅ macOS通知送信済み")
            sent = True

    if not sent:
        print(f"  ⚠️  通知送信失敗（LINE/macOS両方）")

    return sent


# ===== テクニカル分析 =====
def calc_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calc_macd(series, fast=12, slow=26, signal=9):
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def calc_bollinger(series, period=20, std_dev=2):
    sma = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    upper = sma + std_dev * std
    lower = sma - std_dev * std
    return upper, sma, lower


def calc_atr(high, low, close, period=14):
    """ATR (Average True Range) 計算"""
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def analyze_for_sell(ticker):
    """売りシグナル用のテクニカル分析"""
    try:
        t = yf.Ticker(ticker)
        data = t.history(period="3mo", interval="1d")
        if data.empty or len(data) < 30:
            return None

        close = data['Close']
        high_s = data['High']
        low_s = data['Low']
        current = float(close.iloc[-1])
        high_price = float(close.max())  # 期間中の最高値

        rsi = calc_rsi(close)
        macd_line, signal_line, macd_hist = calc_macd(close)
        bb_upper, bb_mid, bb_lower = calc_bollinger(close)
        atr_series = calc_atr(high_s, low_s, close)

        def safe_float(s, idx=-1, default=0):
            try:
                v = float(s.iloc[idx])
                return v if not pd.isna(v) else default
            except:
                return default

        cur_atr = safe_float(atr_series, -1, 0)
        atr_pct = cur_atr / current * 100 if current > 0 else 0

        return {
            "price": current,
            "high_3mo": high_price,
            "rsi": safe_float(rsi, -1, 50),
            "macd_hist": safe_float(macd_hist, -1, 0),
            "prev_macd_hist": safe_float(macd_hist, -2, 0),
            "bb_upper": safe_float(bb_upper, -1, current * 1.05),
            "bb_lower": safe_float(bb_lower, -1, current * 0.95),
            "atr": cur_atr,
            "atr_pct": atr_pct,
        }
    except Exception as e:
        print(f"  分析エラー ({ticker}): {e}")
        return None


# ===== ポジション監視 =====
def check_positions(config):
    """全ポジションをチェックして売りシグナルを検出"""
    positions = load_positions()
    if not positions:
        print("  ポジションが登録されていません。")
        print("  追加: python3 ~/market-alert.py add [ティッカー] [買値] [株数]")
        return

    rules = config["rules"]
    alerts = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    print(f"\n  🔍 ポジション監視中... ({now})")
    print(f"  監視銘柄数: {len(positions)}")
    print("-" * 70)

    for pos in positions:
        ticker = pos["ticker"]
        name = pos["name"]
        entry_price = pos["entry_price"]
        shares = pos["shares"]
        market = pos.get("market", "US")

        analysis = analyze_for_sell(ticker)
        if not analysis:
            print(f"  ⚠️  {name} ({ticker}): データ取得失敗")
            continue

        current = analysis["price"]
        pnl_pct = (current - entry_price) / entry_price * 100
        pnl_amount = (current - entry_price) * shares

        if market == "JP":
            price_str = f"¥{current:,.0f}"
            entry_str = f"¥{entry_price:,.0f}"
            pnl_str = f"¥{pnl_amount:,.0f}"
        else:
            price_str = f"${current:,.2f}"
            entry_str = f"${entry_price:,.2f}"
            pnl_str = f"${pnl_amount:,.2f}"

        sell_signals = []
        urgency = 0  # 0=情報, 1=注意（様子見）, 2=即行動

        stop_price = entry_price * (1 + rules["stop_loss_pct"] / 100)
        target_price = entry_price * (1 + rules["target_profit_pct"] / 100)
        if market == "JP":
            sp_str = f"¥{stop_price:,.0f}"
            tp_str = f"¥{target_price:,.0f}"
        else:
            sp_str = f"${stop_price:,.2f}"
            tp_str = f"${target_price:,.2f}"
        dist_to_stop = abs(pnl_pct - rules["stop_loss_pct"])

        # 1. 損切りライン到達 → 即売却
        if pnl_pct <= rules["stop_loss_pct"]:
            sell_signals.append(
                f"🚨 損切りライン({rules['stop_loss_pct']}%)に到達！\n"
                f"  → すぐに売却してください\n"
                f"  → これ以上持つと損失が拡大します"
            )
            urgency = max(urgency, 2)

        # 2. 利確ライン到達 → 売却検討
        if pnl_pct >= rules["target_profit_pct"]:
            sell_signals.append(
                f"🎯 利確目標（+{rules['target_profit_pct']}%）に到達！\n"
                f"  → 利益確定の売却を検討してください\n"
                f"  → 含み益: {pnl_str}（{pnl_pct:+.1f}%）"
            )
            urgency = max(urgency, 2)

        # 3. トレーリングストップ（ATR動的） → 注意（様子見でOK）
        high = analysis["high_3mo"]
        atr_pct_val = analysis.get("atr_pct", 0)
        # ATR×2%を基準に、最低3%〜最大10%の範囲でクランプ
        dynamic_trail_pct = max(3.0, min(10.0, atr_pct_val * 2))
        if high > entry_price:
            drop_from_high = (current - high) / high * 100
            if drop_from_high <= -dynamic_trail_pct:
                sell_signals.append(
                    f"📉 直近3ヶ月の高値から{drop_from_high:.1f}%下落中（ATR動的ストップ: -{dynamic_trail_pct:.1f}%）\n"
                    f"  → 下落トレンドの可能性あり\n"
                    f"  → あなたの損益: {pnl_pct:+.1f}%  損切りライン({sp_str})まで あと{dist_to_stop:.1f}%\n"
                    f"  → 今すぐ売る必要はなし。{sp_str}を割ったら損切り"
                )
                urgency = max(urgency, 1)

        # 4. RSI過熱 → 利確の好機
        if analysis["rsi"] >= rules["rsi_sell_threshold"] and pnl_pct > 0:
            sell_signals.append(
                f"⚠️ 株価が過熱気味（RSI {analysis['rsi']:.0f}）\n"
                f"  → 利益が出ている今、一部利確も選択肢"
            )
            urgency = max(urgency, 1)

        # 5. MACDデッドクロス → 勢い低下
        if rules["macd_death_cross"]:
            if analysis["macd_hist"] < 0 and analysis["prev_macd_hist"] >= 0:
                sell_signals.append(
                    f"⚠️ 上昇の勢いが弱まっています\n"
                    f"  → トレンド転換のサイン。下がり続けるなら注意"
                )
                urgency = max(urgency, 1)

        # 6. BB上限突破 → 反落しやすい
        if rules["bb_upper_warn"] and current >= analysis["bb_upper"]:
            sell_signals.append(
                f"⚠️ 株価が通常の変動幅の上限に到達\n"
                f"  → 一時的に下がりやすい位置。利確も検討"
            )
            urgency = max(urgency, 1)

        # 7. 含み損拡大中 → 損切りライン接近
        if -5 > pnl_pct > rules["stop_loss_pct"]:
            sell_signals.append(
                f"⚡ 含み損が{pnl_pct:+.1f}%に拡大中\n"
                f"  → 損切りライン({sp_str})まで あと{dist_to_stop:.1f}%\n"
                f"  → {sp_str}を割ったら売却を考えましょう"
            )

        # 表示
        status_icon = "🔴" if pnl_pct < 0 else "🟢"
        print(f"\n  {status_icon} {name} ({ticker})")
        print(f"    現在値: {price_str}  取得価格: {entry_str}  損益: {pnl_str} ({pnl_pct:+.1f}%)")
        print(f"    RSI: {analysis['rsi']:.0f}  MACD: {'↑' if analysis['macd_hist'] > 0 else '↓'}")

        if sell_signals:
            for sig in sell_signals:
                print(f"    {sig}")

            # アラート登録
            alerts.append({
                "ticker": ticker,
                "name": name,
                "price": current,
                "entry_price": entry_price,
                "pnl_pct": pnl_pct,
                "pnl_amount": pnl_amount,
                "signals": sell_signals,
                "urgency": urgency,
                "market": market,
            })
        else:
            print(f"    ✅ 異常なし - ホールド継続")

        # ポジション情報を更新（最新価格）
        pos["current_price"] = current
        pos["pnl_pct"] = pnl_pct
        pos["last_check"] = now

    save_positions(positions)

    # === アラート通知 ===
    if alerts:
        urgent = [a for a in alerts if a["urgency"] >= 2]
        warnings = [a for a in alerts if a["urgency"] == 1]

        print(f"\n{'=' * 70}")
        if urgent:
            print(f"  🚨 即時対応が必要: {len(urgent)}銘柄")
            msg_lines = ["🚨 今すぐ確認してください 🚨", ""]
            for a in urgent:
                p = f"¥{a['price']:,.0f}" if a["market"] == "JP" else f"${a['price']:,.2f}"
                ep = f"¥{a['entry_price']:,.0f}" if a["market"] == "JP" else f"${a['entry_price']:,.2f}"
                pnl_str = f"¥{a['pnl_amount']:,.0f}" if a["market"] == "JP" else f"${a['pnl_amount']:,.2f}"
                msg_lines.append(f"━━━━━━━━━━━━━━━")
                msg_lines.append(f"■ {a['name']}（{a['ticker']}）")
                msg_lines.append(f"  現在値: {p}（取得: {ep}）")
                msg_lines.append(f"  損益: {pnl_str}（{a['pnl_pct']:+.1f}%）")
                msg_lines.append("")
                for sig in a["signals"]:
                    msg_lines.append(sig)
                msg_lines.append("")

            notify(config, "売買アラート", "\n".join(msg_lines))

        if warnings:
            print(f"  ⚠️  注意銘柄: {len(warnings)}銘柄")
            msg_lines = ["⚠️ 注意情報（様子見でOK）", ""]
            for a in warnings:
                p = f"¥{a['price']:,.0f}" if a["market"] == "JP" else f"${a['price']:,.2f}"
                ep = f"¥{a['entry_price']:,.0f}" if a["market"] == "JP" else f"${a['entry_price']:,.2f}"
                pnl_str = f"¥{a['pnl_amount']:,.0f}" if a["market"] == "JP" else f"${a['pnl_amount']:,.2f}"
                msg_lines.append(f"━━━━━━━━━━━━━━━")
                msg_lines.append(f"■ {a['name']}（{a['ticker']}）")
                msg_lines.append(f"  現在値: {p}（取得: {ep}）")
                msg_lines.append(f"  損益: {pnl_str}（{a['pnl_pct']:+.1f}%）")
                msg_lines.append("")
                for sig in a["signals"]:
                    msg_lines.append(sig)
                msg_lines.append("")

            notify(config, "注意アラート", "\n".join(msg_lines))

        # ログ保存
        save_alert_log(alerts)
    else:
        print(f"\n  ✅ 全ポジション正常。アラートなし。")

    print(f"\n{'=' * 70}")
    return alerts


def save_alert_log(alerts):
    """アラート履歴を保存"""
    log = []
    if os.path.exists(ALERT_LOG_FILE):
        try:
            with open(ALERT_LOG_FILE, 'r') as f:
                log = json.load(f)
        except:
            log = []

    log.append({
        "timestamp": datetime.now().isoformat(),
        "alerts": [{
            "ticker": a["ticker"],
            "name": a["name"],
            "price": a["price"],
            "pnl_pct": a["pnl_pct"],
            "signals": a["signals"],
            "urgency": a["urgency"],
        } for a in alerts]
    })

    log = log[-200:]
    with open(ALERT_LOG_FILE, 'w') as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


# ===== ポジション管理 =====
def add_position(ticker, entry_price, shares, name=None):
    """ポジション追加"""
    positions = load_positions()

    # 銘柄名を自動取得
    if not name:
        try:
            t = yf.Ticker(ticker)
            info = t.info
            name = info.get("shortName", info.get("longName", ticker))
        except:
            name = ticker

    market = "JP" if ticker.endswith(".T") else "US"

    # 既存ポジションがあれば更新（平均取得単価）
    existing = next((p for p in positions if p["ticker"] == ticker), None)
    if existing:
        total_cost = existing["entry_price"] * existing["shares"] + entry_price * shares
        total_shares = existing["shares"] + shares
        existing["entry_price"] = total_cost / total_shares
        existing["shares"] = total_shares
        existing["updated"] = datetime.now().isoformat()
        print(f"  ✅ {name} を更新（平均取得価格: {existing['entry_price']:.2f}, 合計{total_shares}株）")
    else:
        positions.append({
            "ticker": ticker,
            "name": name,
            "market": market,
            "entry_price": entry_price,
            "shares": shares,
            "added": datetime.now().isoformat(),
        })
        price_str = f"¥{entry_price:,.0f}" if market == "JP" else f"${entry_price:,.2f}"
        print(f"  ✅ {name} ({ticker}) を追加: {price_str} x {shares}株")

    save_positions(positions)


def remove_position(ticker):
    """ポジション削除（売却済み）"""
    positions = load_positions()
    before = len(positions)
    positions = [p for p in positions if p["ticker"] != ticker]
    if len(positions) < before:
        save_positions(positions)
        print(f"  ✅ {ticker} を削除しました")
    else:
        print(f"  ❌ {ticker} はポジションに存在しません")


def list_positions():
    """ポジション一覧表示"""
    positions = load_positions()
    if not positions:
        print("  ポジションなし")
        return

    print(f"\n  📋 保有ポジション一覧 ({len(positions)}銘柄)")
    print("-" * 60)
    for p in positions:
        market = p.get("market", "US")
        if market == "JP":
            price_str = f"¥{p['entry_price']:,.0f}"
        else:
            price_str = f"${p['entry_price']:,.2f}"
        flag = "🇯🇵" if market == "JP" else "🇺🇸"
        print(f"  {flag} {p['name'][:15]:<15} {p['ticker']:<10} {price_str:>12} x {p['shares']}株")
    print()


# ===== LINE設定 =====
def setup_line():
    """LINE Messaging API設定ガイド"""
    config = load_config()

    print("""
╔══════════════════════════════════════════════════════╗
║          LINE通知セットアップガイド                    ║
╚══════════════════════════════════════════════════════╝

【手順】

1. LINE Developersにログイン
   → https://developers.line.biz/

2.「プロバイダー」を作成（名前は何でもOK）

3.「Messaging API」チャネルを作成
   - チャネル名: 「株アラート」など

4.「Messaging API設定」タブで:
   - チャネルアクセストークンを発行（長期）
   - このトークンをコピー

5.「チャネル基本設定」タブで:
   - あなたのユーザーIDを確認

6. 作成したLINE公式アカウントを友だち追加
   （QRコードから）

7. 以下のコマンドで設定:
""")

    token = input("  チャネルアクセストークン: ").strip()
    user_id = input("  ユーザーID: ").strip()

    if token and user_id:
        config["line"]["channel_access_token"] = token
        config["line"]["user_id"] = user_id
        config["notify"]["line_enabled"] = True
        save_config(config)

        # テスト送信
        print("\n  テスト通知を送信中...")
        success = send_line_message(config, "🎉 株アラートシステム接続テスト成功！\n\nこのアカウントから売買シグナルが届きます。")
        if success:
            print("  ✅ LINE通知設定完了！テストメッセージを確認してください。")
        else:
            print("  ❌ 送信失敗。トークンとユーザーIDを確認してください。")
    else:
        print("  スキップしました。後で再設定できます。")


def setup_cron():
    """cron設定ガイド"""
    print("""
╔══════════════════════════════════════════════════════╗
║            自動監視 cron設定ガイド                     ║
╚══════════════════════════════════════════════════════╝

以下をターミナルで実行して crontab を編集:

  crontab -e

以下を追加:

# --- 株アラート ---
# 日本株: 平日9:00-15:00、30分おきに監視
*/30 9-15 * * 1-5 /usr/bin/python3 /Users/muraseatsuki/market-alert.py check >> /Users/muraseatsuki/market-alert-cron.log 2>&1

# 米国株: 平日23:30-翌6:00、30分おきに監視（日本時間）
*/30 23 * * 1-5 /usr/bin/python3 /Users/muraseatsuki/market-alert.py check >> /Users/muraseatsuki/market-alert-cron.log 2>&1
0-30/30 0-6 * * 2-6 /usr/bin/python3 /Users/muraseatsuki/market-alert.py check >> /Users/muraseatsuki/market-alert-cron.log 2>&1

# 市場スキャン: 朝8:30と夜22:00に全銘柄スキャン
30 8 * * 1-5 /usr/bin/python3 /Users/muraseatsuki/market-scanner.py jp >> /Users/muraseatsuki/market-scanner-cron.log 2>&1
0 22 * * 1-5 /usr/bin/python3 /Users/muraseatsuki/market-scanner.py us >> /Users/muraseatsuki/market-scanner-cron.log 2>&1

保存して完了！Macがスリープ中は実行されないので注意。
""")


# ===== メイン =====
def show_help():
    print("""
╔══════════════════════════════════════════════════════╗
║           📊 株アラートシステム                        ║
╚══════════════════════════════════════════════════════╝

【使い方】

  ポジション管理:
    python3 ~/market-alert.py add NVDA 140.50 10       # 買いポジション追加
    python3 ~/market-alert.py add 8306.T 2950 100      # 日本株追加
    python3 ~/market-alert.py remove NVDA              # ポジション削除
    python3 ~/market-alert.py list                     # 一覧表示

  監視:
    python3 ~/market-alert.py check                    # 全ポジション監視
    python3 ~/market-alert.py check --quiet            # アラートのみ表示

  設定:
    python3 ~/market-alert.py setup-line               # LINE通知設定
    python3 ~/market-alert.py setup-cron               # 自動実行設定
    python3 ~/market-alert.py test-notify              # テスト通知送信

  分析:
    python3 ~/market-alert.py log                      # アラート履歴

【売りシグナル】
  🚨 即時対応:
    - 損切りライン到達（-8%）
    - 利確ライン到達（+15%）
    - トレーリングストップ（高値から-5%）

  ⚠️ 注意:
    - RSI買われすぎ（75以上）
    - MACDデッドクロス
    - ボリンジャーバンド上限
    - 含み損拡大中（-5%以下）
""")


def show_log():
    """アラートログ表示"""
    if not os.path.exists(ALERT_LOG_FILE):
        print("  アラート履歴なし")
        return

    with open(ALERT_LOG_FILE, 'r') as f:
        log = json.load(f)

    print(f"\n  📜 アラート履歴（直近10件）")
    print("-" * 70)
    for entry in log[-10:]:
        ts = entry["timestamp"][:16]
        for a in entry["alerts"]:
            urgency = "🚨" if a["urgency"] >= 2 else "⚠️"
            print(f"  {ts}  {urgency} {a['name']} ({a['ticker']}) {a['pnl_pct']:+.1f}%")
            for sig in a["signals"][:2]:
                print(f"           {sig}")
    print()


def main():
    if len(sys.argv) < 2:
        show_help()
        return

    cmd = sys.argv[1]
    config = load_config()

    if cmd == "add":
        if len(sys.argv) < 5:
            print("  使い方: python3 ~/market-alert.py add [ティッカー] [買値] [株数]")
            print("  例: python3 ~/market-alert.py add NVDA 140.50 10")
            print("  例: python3 ~/market-alert.py add 8306.T 2950 100")
            return
        ticker = sys.argv[2].upper()
        entry_price = float(sys.argv[3])
        shares = int(sys.argv[4])
        name = sys.argv[5] if len(sys.argv) > 5 else None
        add_position(ticker, entry_price, shares, name)

    elif cmd == "remove":
        if len(sys.argv) < 3:
            print("  使い方: python3 ~/market-alert.py remove [ティッカー]")
            return
        remove_position(sys.argv[2].upper())

    elif cmd == "list":
        list_positions()

    elif cmd == "check":
        check_positions(config)

    elif cmd == "setup-line":
        setup_line()

    elif cmd == "setup-cron":
        setup_cron()

    elif cmd == "test-notify":
        print("  テスト通知を送信中...")
        notify(config, "テスト通知", "📊 株アラートシステムのテストです。\n正常に動作しています！")

    elif cmd == "log":
        show_log()

    else:
        show_help()


if __name__ == "__main__":
    main()
