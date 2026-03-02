import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# ============================================================
# 株式分析スクリプト - 詳細レポート
# ============================================================

TICKERS = [
    "PLTR", "HAL", "RTX", "NU", "SOFI", "DKNG", "AFRM", "HOOD",
    "RKLB", "COIN", "XOM", "CVX", "OXY", "LMT", "NOC", "CRWD",
    "NET", "UBER", "IONQ", "MARA", "NFLX"
]

SECTOR_MAP = {
    "PLTR": "AI/データ分析", "HAL": "エネルギーサービス", "RTX": "防衛/航空宇宙",
    "NU": "フィンテック(ブラジル)", "SOFI": "フィンテック", "DKNG": "オンラインギャンブル",
    "AFRM": "BNPL/フィンテック", "HOOD": "証券/フィンテック", "RKLB": "宇宙/ロケット",
    "COIN": "暗号資産取引所", "XOM": "石油メジャー", "CVX": "石油メジャー",
    "OXY": "石油/エネルギー", "LMT": "防衛大手", "NOC": "防衛大手",
    "CRWD": "サイバーセキュリティ", "NET": "CDN/セキュリティ", "UBER": "ライドシェア/配達",
    "IONQ": "量子コンピュータ", "MARA": "ビットコインマイニング",
    "NFLX": "ストリーミング/GAFAM"
}

def calculate_rsi(prices, period=14):
    """RSI（相対力指数）を計算"""
    delta = prices.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta.where(delta < 0, 0.0))
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    # Wilder's smoothing after initial SMA
    for i in range(period, len(avg_gain)):
        avg_gain.iloc[i] = (avg_gain.iloc[i-1] * (period - 1) + gain.iloc[i]) / period
        avg_loss.iloc[i] = (avg_loss.iloc[i-1] * (period - 1) + loss.iloc[i]) / period
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def format_market_cap(mc):
    """時価総額を読みやすい形式に変換"""
    if mc is None or mc == 0:
        return "N/A"
    if mc >= 1e12:
        return f"${mc/1e12:.2f}T"
    elif mc >= 1e9:
        return f"${mc/1e9:.1f}B"
    elif mc >= 1e6:
        return f"${mc/1e6:.0f}M"
    return f"${mc:,.0f}"

def categorize_cap(mc):
    """時価総額カテゴリ"""
    if mc is None or mc == 0:
        return "不明"
    if mc >= 200e9:
        return "メガキャップ"
    elif mc >= 10e9:
        return "ラージキャップ"
    elif mc >= 2e9:
        return "ミッドキャップ"
    else:
        return "スモールキャップ"

def get_stock_data(ticker):
    """個別銘柄のデータを取得・分析"""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        # 過去1年分の日足データ取得
        hist = stock.history(period="1y")
        if hist.empty or len(hist) < 20:
            return None

        current_price = hist['Close'].iloc[-1]

        # --- 価格変動率の計算 ---
        # 1週間前
        if len(hist) >= 5:
            price_1w_ago = hist['Close'].iloc[-6] if len(hist) > 5 else hist['Close'].iloc[0]
            change_1w = ((current_price - price_1w_ago) / price_1w_ago) * 100
        else:
            change_1w = None

        # 1ヶ月前 (~21営業日)
        if len(hist) >= 21:
            price_1m_ago = hist['Close'].iloc[-22]
            change_1m = ((current_price - price_1m_ago) / price_1m_ago) * 100
        else:
            change_1m = None

        # 3ヶ月前 (~63営業日)
        if len(hist) >= 63:
            price_3m_ago = hist['Close'].iloc[-64]
            change_3m = ((current_price - price_3m_ago) / price_3m_ago) * 100
        else:
            change_3m = None

        # --- RSI計算 ---
        rsi_series = calculate_rsi(hist['Close'], 14)
        rsi = rsi_series.iloc[-1] if not pd.isna(rsi_series.iloc[-1]) else None

        # --- 3ヶ月高値/安値 ---
        hist_3m = hist.tail(63)
        high_3m = hist_3m['High'].max()
        low_3m = hist_3m['Low'].min()
        range_3m = high_3m - low_3m
        if range_3m > 0:
            position_in_range = ((current_price - low_3m) / range_3m) * 100
        else:
            position_in_range = 50.0

        # --- 出来高分析 ---
        avg_vol_90 = hist['Volume'].tail(63).mean()
        recent_vol = hist['Volume'].tail(5).mean()
        if avg_vol_90 > 0:
            vol_ratio = recent_vol / avg_vol_90
        else:
            vol_ratio = 1.0

        # --- 52週高値 ---
        high_52w = hist['High'].max()
        pct_from_52w_high = ((current_price - high_52w) / high_52w) * 100

        low_52w = hist['Low'].min()

        # --- ファンダメンタルズ ---
        market_cap = info.get('marketCap', 0)
        pe_ratio = info.get('trailingPE', None)
        forward_pe = info.get('forwardPE', None)
        sector = info.get('sector', 'N/A')
        name = info.get('shortName', ticker)

        # --- 移動平均線 ---
        ma_20 = hist['Close'].tail(20).mean()
        ma_50 = hist['Close'].tail(50).mean()
        ma_200 = hist['Close'].tail(200).mean() if len(hist) >= 200 else None

        # --- カテゴリ判定 ---
        if rsi is not None:
            if rsi < 35 and position_in_range < 25:
                category = "今すぐ買い検討"
                cat_priority = 1
            elif rsi < 50 and pct_from_52w_high < -15:
                category = "チャンス待ち"
                cat_priority = 2
            elif rsi > 70:
                category = "見送り"
                cat_priority = 4
            elif rsi > 50 or position_in_range > 70:
                category = "様子見"
                cat_priority = 3
            elif 35 <= rsi <= 50 and pct_from_52w_high < -10:
                category = "チャンス待ち"
                cat_priority = 2
            else:
                category = "様子見"
                cat_priority = 3
        else:
            category = "様子見"
            cat_priority = 3

        return {
            'ticker': ticker,
            'name': name,
            'sector': SECTOR_MAP.get(ticker, sector),
            'current_price': current_price,
            'change_1w': change_1w,
            'change_1m': change_1m,
            'change_3m': change_3m,
            'rsi': rsi,
            'high_3m': high_3m,
            'low_3m': low_3m,
            'position_in_range': position_in_range,
            'avg_vol_90': avg_vol_90,
            'recent_vol': recent_vol,
            'vol_ratio': vol_ratio,
            'high_52w': high_52w,
            'low_52w': low_52w,
            'pct_from_52w_high': pct_from_52w_high,
            'market_cap': market_cap,
            'cap_category': categorize_cap(market_cap),
            'pe_ratio': pe_ratio,
            'forward_pe': forward_pe,
            'ma_20': ma_20,
            'ma_50': ma_50,
            'ma_200': ma_200,
            'category': category,
            'cat_priority': cat_priority,
        }
    except Exception as e:
        print(f"  [エラー] {ticker}: {e}")
        return None


def generate_reasoning(d):
    """各銘柄の買い/見送り理由を生成"""
    reasons = []
    warnings_list = []

    # RSI分析
    if d['rsi'] is not None:
        if d['rsi'] < 30:
            reasons.append(f"RSI {d['rsi']:.1f} → 強い売られすぎシグナル（反発の可能性大）")
        elif d['rsi'] < 40:
            reasons.append(f"RSI {d['rsi']:.1f} → 売られすぎ圏に接近中")
        elif d['rsi'] > 70:
            warnings_list.append(f"RSI {d['rsi']:.1f} → 買われすぎ（調整リスク高い）")
        elif d['rsi'] > 60:
            warnings_list.append(f"RSI {d['rsi']:.1f} → やや買われすぎ")

    # 52週高値からの距離
    if d['pct_from_52w_high'] < -30:
        reasons.append(f"52週高値から{abs(d['pct_from_52w_high']):.1f}%下落 → 大幅ディスカウント")
    elif d['pct_from_52w_high'] < -20:
        reasons.append(f"52週高値から{abs(d['pct_from_52w_high']):.1f}%下落 → 割安水準")
    elif d['pct_from_52w_high'] < -10:
        reasons.append(f"52週高値から{abs(d['pct_from_52w_high']):.1f}%下落 → ある程度の調整")
    elif d['pct_from_52w_high'] > -5:
        warnings_list.append(f"52週高値に近い（{d['pct_from_52w_high']:.1f}%）→ 上値余地限定的")

    # 3ヶ月レンジ内のポジション
    if d['position_in_range'] < 20:
        reasons.append(f"3ヶ月レンジの下位{d['position_in_range']:.0f}%に位置 → 底値圏")
    elif d['position_in_range'] < 35:
        reasons.append(f"3ヶ月レンジの下位{d['position_in_range']:.0f}%に位置")
    elif d['position_in_range'] > 80:
        warnings_list.append(f"3ヶ月レンジの上位{d['position_in_range']:.0f}%に位置 → 高値掴みリスク")

    # 出来高分析
    if d['vol_ratio'] > 1.5:
        reasons.append(f"直近出来高が90日平均の{d['vol_ratio']:.1f}倍 → 注目度上昇中")
    elif d['vol_ratio'] < 0.7:
        warnings_list.append(f"出来高低下中（平均の{d['vol_ratio']:.1f}倍）→ 関心薄れ")

    # 移動平均線分析
    if d['ma_200'] is not None:
        if d['current_price'] < d['ma_200']:
            reasons.append(f"200日移動平均(${d['ma_200']:.2f})を下回り → 長期的に売られすぎの可能性")
        elif d['current_price'] > d['ma_200'] * 1.2:
            warnings_list.append(f"200日移動平均を大幅に上回り → 過熱感")

    if d['current_price'] < d['ma_50']:
        reasons.append(f"50日移動平均(${d['ma_50']:.2f})を下回り → 短中期で調整中")

    # 短期モメンタム
    if d['change_1w'] is not None and d['change_1w'] < -5:
        reasons.append(f"直近1週間で{d['change_1w']:.1f}%下落 → 短期的な押し目の可能性")
    if d['change_1m'] is not None and d['change_1m'] < -10:
        reasons.append(f"直近1ヶ月で{d['change_1m']:.1f}%下落 → 中期調整中")

    # P/E分析
    if d['pe_ratio'] is not None:
        if d['pe_ratio'] < 15:
            reasons.append(f"PER {d['pe_ratio']:.1f} → バリュエーション割安")
        elif d['pe_ratio'] > 60:
            warnings_list.append(f"PER {d['pe_ratio']:.1f} → 高バリュエーション")
        elif d['pe_ratio'] > 100:
            warnings_list.append(f"PER {d['pe_ratio']:.1f} → 極めて高いバリュエーション")

    return reasons, warnings_list


def print_analysis():
    print("=" * 100)
    print("  米国株 詳細分析レポート")
    print(f"  分析日時: {datetime.now().strftime('%Y年%m月%d日 %H:%M')}")
    print("=" * 100)
    print()

    # データ取得
    results = []
    print("データ取得中...")
    for ticker in TICKERS:
        print(f"  {ticker}...", end=" ", flush=True)
        data = get_stock_data(ticker)
        if data:
            results.append(data)
            print(f"OK (${data['current_price']:.2f})")
        else:
            print("失敗")
    print()

    if not results:
        print("データ取得に失敗しました。")
        return

    # カテゴリ別に分類・ソート
    results.sort(key=lambda x: (x['cat_priority'], x.get('rsi', 50) or 50))

    # ============================================================
    # サマリーテーブル
    # ============================================================
    print("=" * 100)
    print("【サマリーテーブル】")
    print("=" * 100)
    header = f"{'銘柄':<7} {'現在値':>9} {'1W%':>7} {'1M%':>7} {'3M%':>7} {'RSI':>6} {'3M位置':>6} {'52W高値比':>9} {'出来高比':>7} {'判定'}"
    print(header)
    print("-" * 100)

    for d in results:
        rsi_str = f"{d['rsi']:.1f}" if d['rsi'] is not None else "N/A"
        w1 = f"{d['change_1w']:+.1f}%" if d['change_1w'] is not None else "N/A"
        m1 = f"{d['change_1m']:+.1f}%" if d['change_1m'] is not None else "N/A"
        m3 = f"{d['change_3m']:+.1f}%" if d['change_3m'] is not None else "N/A"
        line = f"{d['ticker']:<7} ${d['current_price']:>8.2f} {w1:>7} {m1:>7} {m3:>7} {rsi_str:>6} {d['position_in_range']:>5.0f}% {d['pct_from_52w_high']:>+7.1f}% {d['vol_ratio']:>6.1f}x  {d['category']}"
        print(line)

    # ============================================================
    # カテゴリ別詳細
    # ============================================================
    categories_order = [
        ("今すぐ買い検討", 1, "RSI < 35 かつ 3ヶ月安値圏。売られすぎで反発の可能性が高い銘柄。"),
        ("チャンス待ち", 2, "RSI 35-50、52週高値から大きく下落。押し目買いの好機が近い銘柄。"),
        ("様子見", 3, "RSI > 50 またはすでに反発済み。エントリーポイントを待つべき銘柄。"),
        ("見送り", 4, "RSI > 70 または割高。現時点での新規購入は推奨しない銘柄。"),
    ]

    for cat_name, cat_id, cat_desc in categories_order:
        cat_stocks = [d for d in results if d['cat_priority'] == cat_id]
        if not cat_stocks:
            continue

        print()
        print("=" * 100)
        marker = "★★★" if cat_id == 1 else ("★★" if cat_id == 2 else ("★" if cat_id == 3 else ""))
        print(f"【{cat_name}】{marker}  ({len(cat_stocks)}銘柄)")
        print(f"  基準: {cat_desc}")
        print("=" * 100)

        for d in cat_stocks:
            print()
            print(f"  ━━━ {d['ticker']} ({d['name']}) ━━━")
            print(f"  セクター: {d['sector']} | {d['cap_category']} ({format_market_cap(d['market_cap'])})")
            print()
            print(f"    現在価格:     ${d['current_price']:.2f}")
            print(f"    52週高値:     ${d['high_52w']:.2f}  (現在値との差: {d['pct_from_52w_high']:+.1f}%)")
            print(f"    52週安値:     ${d['low_52w']:.2f}")
            print(f"    3ヶ月高値:    ${d['high_3m']:.2f}")
            print(f"    3ヶ月安値:    ${d['low_3m']:.2f}")
            print(f"    3ヶ月レンジ位置: {d['position_in_range']:.1f}% (0%=底, 100%=天井)")
            print()

            w1 = f"{d['change_1w']:+.1f}%" if d['change_1w'] is not None else "N/A"
            m1 = f"{d['change_1m']:+.1f}%" if d['change_1m'] is not None else "N/A"
            m3 = f"{d['change_3m']:+.1f}%" if d['change_3m'] is not None else "N/A"
            print(f"    価格変動:     1週間 {w1} | 1ヶ月 {m1} | 3ヶ月 {m3}")

            rsi_str = f"{d['rsi']:.1f}" if d['rsi'] is not None else "N/A"
            rsi_bar = ""
            if d['rsi'] is not None:
                filled = int(d['rsi'] / 5)
                rsi_bar = f" [{'█' * filled}{'░' * (20 - filled)}]"
            print(f"    RSI (14日):   {rsi_str}{rsi_bar}")

            pe_str = f"{d['pe_ratio']:.1f}" if d['pe_ratio'] is not None else "N/A"
            fpe_str = f"{d['forward_pe']:.1f}" if d['forward_pe'] is not None else "N/A"
            print(f"    PER:          実績 {pe_str} | 予想 {fpe_str}")

            vol_direction = "↑ 増加" if d['vol_ratio'] > 1.1 else ("↓ 減少" if d['vol_ratio'] < 0.9 else "→ 横ばい")
            print(f"    出来高:       90日平均比 {d['vol_ratio']:.2f}x ({vol_direction})")

            ma200_str = f"${d['ma_200']:.2f}" if d['ma_200'] is not None else "N/A"
            ma200_pos = ""
            if d['ma_200'] is not None:
                if d['current_price'] > d['ma_200']:
                    ma200_pos = " (上回り)"
                else:
                    ma200_pos = " (下回り ⚠)"
            print(f"    移動平均:     20日 ${d['ma_20']:.2f} | 50日 ${d['ma_50']:.2f} | 200日 {ma200_str}{ma200_pos}")

            # 買い/売り理由
            reasons, warnings_list = generate_reasoning(d)
            print()
            if reasons:
                print(f"    [買いポイント]")
                for r in reasons:
                    print(f"      + {r}")
            if warnings_list:
                print(f"    [注意点]")
                for w in warnings_list:
                    print(f"      - {w}")

            # 具体的なアクション提案
            print()
            if d['cat_priority'] == 1:
                target_entry = d['low_3m'] * 1.02
                target_stop = d['low_3m'] * 0.95
                target_profit = d['current_price'] * 1.15
                print(f"    >>> アクション提案:")
                print(f"        エントリー目安: ${d['current_price']:.2f} (現在値) 〜 ${target_entry:.2f}")
                print(f"        損切りライン:   ${target_stop:.2f} (3ヶ月安値の5%下)")
                print(f"        利確目標:       ${target_profit:.2f} (+15%)")
                print(f"        推奨: 分割買い（1/3ずつ3回に分けて購入）")
            elif d['cat_priority'] == 2:
                wait_price = d['current_price'] * 0.95
                print(f"    >>> アクション提案:")
                print(f"        待機指値:       ${wait_price:.2f} (現在値から-5%)")
                print(f"        理想エントリー: RSIが35以下に低下した時点")
                print(f"        推奨: アラート設定して待機")
            elif d['cat_priority'] == 3:
                print(f"    >>> アクション提案:")
                print(f"        現時点では新規エントリー非推奨")
                print(f"        監視ポイント: RSIが50以下に低下 or 10%以上の調整")
            else:
                print(f"    >>> アクション提案:")
                print(f"        現時点での購入は見送り")
                if d['rsi'] is not None and d['rsi'] > 70:
                    print(f"        利確検討: 保有している場合は一部利確を検討")

    # ============================================================
    # 全体サマリー
    # ============================================================
    print()
    print("=" * 100)
    print("【全体サマリー・投資判断まとめ】")
    print("=" * 100)

    buy_now = [d for d in results if d['cat_priority'] == 1]
    chance = [d for d in results if d['cat_priority'] == 2]
    watch = [d for d in results if d['cat_priority'] == 3]
    skip = [d for d in results if d['cat_priority'] == 4]

    print()
    print(f"  今すぐ買い検討: {len(buy_now)}銘柄 → {', '.join([d['ticker'] for d in buy_now]) if buy_now else 'なし'}")
    print(f"  チャンス待ち:   {len(chance)}銘柄 → {', '.join([d['ticker'] for d in chance]) if chance else 'なし'}")
    print(f"  様子見:         {len(watch)}銘柄 → {', '.join([d['ticker'] for d in watch]) if watch else 'なし'}")
    print(f"  見送り:         {len(skip)}銘柄 → {', '.join([d['ticker'] for d in skip]) if skip else 'なし'}")

    # セクター別分析
    print()
    print("  【セクター別コメント】")
    sectors = {}
    for d in results:
        s = d['sector']
        if s not in sectors:
            sectors[s] = []
        sectors[s].append(d)

    for s, stocks in sectors.items():
        avg_rsi = np.mean([d['rsi'] for d in stocks if d['rsi'] is not None])
        avg_change = np.mean([d['change_1m'] for d in stocks if d['change_1m'] is not None])
        tickers_str = ", ".join([d['ticker'] for d in stocks])
        print(f"    {s} ({tickers_str}): 平均RSI {avg_rsi:.1f}, 1ヶ月平均変動 {avg_change:+.1f}%")

    # 最も魅力的な銘柄トップ5
    print()
    print("  【注目度ランキング TOP5 (買い魅力度順)】")
    # スコアリング: RSIが低いほど良い、52W高値からの距離が大きいほど良い、3Mレンジ位置が低いほど良い
    for d in results:
        rsi_score = max(0, 70 - (d['rsi'] or 50)) * 2  # RSI低いほどスコア高い
        drop_score = abs(min(0, d['pct_from_52w_high']))  # 高値からの下落幅
        range_score = max(0, 50 - d['position_in_range'])  # レンジ下位ほどスコア高い
        vol_score = min(20, (d['vol_ratio'] - 1) * 10) if d['vol_ratio'] > 1 else 0
        d['attractiveness_score'] = rsi_score + drop_score + range_score + vol_score

    ranked = sorted(results, key=lambda x: x['attractiveness_score'], reverse=True)
    for i, d in enumerate(ranked[:5], 1):
        print(f"    {i}. {d['ticker']:>5} (スコア: {d['attractiveness_score']:.0f}) "
              f"- RSI {d['rsi']:.1f if d['rsi'] else 0}, "
              f"52W高値比 {d['pct_from_52w_high']:+.1f}%, "
              f"判定: {d['category']}")

    print()
    print("=" * 100)
    print("【免責事項】")
    print("  本レポートは情報提供のみを目的としており、投資助言ではありません。")
    print("  投資判断はご自身の責任で行ってください。")
    print("  過去のパフォーマンスは将来の結果を保証するものではありません。")
    print("=" * 100)


if __name__ == "__main__":
    print_analysis()
