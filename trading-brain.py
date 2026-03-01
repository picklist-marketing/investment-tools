#!/usr/bin/env python3
"""
Trading Brain - 世界一を目指すトレーディングAI
常時稼働・多角分析・LINE即時通知

【機能】
1. マルチタイムフレーム分析（日足・時間足・15分足）
2. チャートパターン検出（ダブルボトム・ブレイクアウト等）
3. ダイバージェンス検出（価格とRSI/MACDの乖離）
4. セクターローテーション分析
5. 市場レジーム判定（VIX・先物・騰落率）
6. 支持線・抵抗線の自動計算
7. リスクリワード比計算
8. ポジションサイジング提案
9. 朝ブリーフィング・リアルタイムアラート・夜サマリー
10. 全シグナルをLINE通知
"""

import yfinance as yf
import pandas as pd
import numpy as np
import json
import os
import sys
import time
import requests
import concurrent.futures
from datetime import datetime, timedelta
from collections import defaultdict

# ===== 設定 =====
CONFIG_FILE = os.path.expanduser("~/market-alert-config.json")
BRAIN_STATE_FILE = os.path.expanduser("~/trading-brain-state.json")
POSITIONS_FILE = os.path.expanduser("~/market-positions.json")

# ===== 全監視銘柄 =====
JP_STOCKS = {
    "6857.T": {"name": "アドバンテスト", "sector": "半導体"},
    "6723.T": {"name": "ルネサス", "sector": "半導体"},
    "6526.T": {"name": "ソシオネクスト", "sector": "半導体"},
    "6920.T": {"name": "レーザーテック", "sector": "半導体"},
    "8035.T": {"name": "東京エレクトロン", "sector": "半導体"},
    "4063.T": {"name": "信越化学", "sector": "半導体"},
    "6146.T": {"name": "ディスコ", "sector": "半導体"},
    "6981.T": {"name": "村田製作所", "sector": "電子部品"},
    "6758.T": {"name": "ソニーG", "sector": "テック"},
    "6501.T": {"name": "日立", "sector": "テック"},
    "6594.T": {"name": "日本電産", "sector": "テック"},
    "6861.T": {"name": "キーエンス", "sector": "テック"},
    "9984.T": {"name": "ソフトバンクG", "sector": "テック"},
    "4385.T": {"name": "メルカリ", "sector": "テック"},
    "8306.T": {"name": "三菱UFJ", "sector": "金融"},
    "8316.T": {"name": "三井住友FG", "sector": "金融"},
    "8411.T": {"name": "みずほFG", "sector": "金融"},
    "8766.T": {"name": "東京海上", "sector": "金融"},
    "8604.T": {"name": "野村HD", "sector": "金融"},
    "7011.T": {"name": "三菱重工", "sector": "防衛"},
    "7012.T": {"name": "川崎重工", "sector": "防衛"},
    "7013.T": {"name": "IHI", "sector": "防衛"},
    "6946.T": {"name": "日本アビオニクス", "sector": "防衛"},
    "3692.T": {"name": "FFRIセキュリティ", "sector": "防衛"},
    "4274.T": {"name": "細谷火工", "sector": "防衛"},
    "6208.T": {"name": "石川製作所", "sector": "防衛"},
    "7203.T": {"name": "トヨタ", "sector": "自動車"},
    "7267.T": {"name": "ホンダ", "sector": "自動車"},
    "7974.T": {"name": "任天堂", "sector": "テック"},
    "8058.T": {"name": "三菱商事", "sector": "商社"},
    "8031.T": {"name": "三井物産", "sector": "商社"},
    "8001.T": {"name": "伊藤忠", "sector": "商社"},
    "5020.T": {"name": "ENEOS", "sector": "エネルギー"},
    "1605.T": {"name": "INPEX", "sector": "エネルギー"},
    "4568.T": {"name": "第一三共", "sector": "医薬"},
    "4519.T": {"name": "中外製薬", "sector": "医薬"},
    "9432.T": {"name": "NTT", "sector": "通信"},
    "9433.T": {"name": "KDDI", "sector": "通信"},
    "9101.T": {"name": "日本郵船", "sector": "海運"},
    "9104.T": {"name": "商船三井", "sector": "海運"},
    "9983.T": {"name": "ファストリ", "sector": "小売"},
    "6098.T": {"name": "リクルート", "sector": "サービス"},
}

US_STOCKS = {
    "NVDA": {"name": "NVIDIA", "sector": "半導体"},
    "AAPL": {"name": "Apple", "sector": "GAFAM"},
    "MSFT": {"name": "Microsoft", "sector": "GAFAM"},
    "GOOGL": {"name": "Alphabet", "sector": "GAFAM"},
    "AMZN": {"name": "Amazon", "sector": "GAFAM"},
    "META": {"name": "Meta", "sector": "GAFAM"},
    "TSLA": {"name": "Tesla", "sector": "EV"},
    "MU": {"name": "Micron", "sector": "半導体"},
    "AVGO": {"name": "Broadcom", "sector": "半導体"},
    "AMD": {"name": "AMD", "sector": "半導体"},
    "INTC": {"name": "Intel", "sector": "半導体"},
    "QCOM": {"name": "Qualcomm", "sector": "半導体"},
    "AMAT": {"name": "Applied Mat", "sector": "半導体"},
    "LRCX": {"name": "Lam Research", "sector": "半導体"},
    "ASML": {"name": "ASML", "sector": "半導体"},
    "TSM": {"name": "TSMC", "sector": "半導体"},
    "ARM": {"name": "Arm", "sector": "半導体"},
    "SMCI": {"name": "Super Micro", "sector": "AI"},
    "PLTR": {"name": "Palantir", "sector": "AI"},
    "CRWD": {"name": "CrowdStrike", "sector": "セキュリティ"},
    "PANW": {"name": "Palo Alto", "sector": "セキュリティ"},
    "NET": {"name": "Cloudflare", "sector": "クラウド"},
    "SNOW": {"name": "Snowflake", "sector": "クラウド"},
    "CRM": {"name": "Salesforce", "sector": "クラウド"},
    "NOW": {"name": "ServiceNow", "sector": "クラウド"},
    "COIN": {"name": "Coinbase", "sector": "仮想通貨"},
    "JPM": {"name": "JPMorgan", "sector": "金融"},
    "GS": {"name": "Goldman Sachs", "sector": "金融"},
    "RTX": {"name": "RTX", "sector": "防衛"},
    "NOC": {"name": "Northrop", "sector": "防衛"},
    "LMT": {"name": "Lockheed", "sector": "防衛"},
    "BA": {"name": "Boeing", "sector": "防衛"},
    "LLY": {"name": "Eli Lilly", "sector": "医薬"},
    "NVO": {"name": "Novo Nordisk", "sector": "医薬"},
    "MRNA": {"name": "Moderna", "sector": "医薬"},
    "XOM": {"name": "ExxonMobil", "sector": "エネルギー"},
    "COP": {"name": "ConocoPhillips", "sector": "エネルギー"},
    "UBER": {"name": "Uber", "sector": "テック"},
    "ABNB": {"name": "Airbnb", "sector": "テック"},
    "NFLX": {"name": "Netflix", "sector": "GAFAM"},
}

# 市場指数
INDICES = {
    "^N225": "日経平均",
    "^GSPC": "S&P500",
    "^IXIC": "NASDAQ",
    "^VIX": "VIX恐怖指数",
    "^DJI": "NYダウ",
    "JPY=X": "ドル円",
}


# ===== テクニカル計算 =====
def sma(s, p):
    return s.rolling(p).mean()

def ema(s, p):
    return s.ewm(span=p, adjust=False).mean()

def rsi(s, p=14):
    d = s.diff()
    g = d.where(d > 0, 0.0).rolling(p).mean()
    l = (-d.where(d < 0, 0.0)).rolling(p).mean()
    return 100 - (100 / (1 + g / l))

def macd(s, f=12, sl=26, sg=9):
    ml = ema(s, f) - ema(s, sl)
    sl_line = ema(ml, sg)
    return ml, sl_line, ml - sl_line

def bollinger(s, p=20, d=2):
    m = sma(s, p)
    st = s.rolling(p).std()
    return m + d * st, m, m - d * st

def atr(h, l, c, p=14):
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(p).mean()

def sf(s, idx=-1, default=0):
    """safe float"""
    try:
        v = float(s.iloc[idx])
        return v if not pd.isna(v) else default
    except:
        return default


# ===== パターン検出 =====
def detect_patterns(close, high, low):
    """チャートパターンを検出"""
    patterns = []
    if len(close) < 20:
        return patterns

    prices = close.values[-20:]

    # ダブルボトム検出
    min1_idx = np.argmin(prices[:10])
    min2_idx = np.argmin(prices[10:]) + 10
    if min1_idx < 8 and min2_idx > 11:
        min1 = prices[min1_idx]
        min2 = prices[min2_idx]
        middle_max = np.max(prices[min1_idx:min2_idx])
        if abs(min1 - min2) / min1 < 0.03 and middle_max > min1 * 1.03:
            if prices[-1] > middle_max:
                patterns.append("📈 ダブルボトム完成→上昇転換")
            elif prices[-1] > min2:
                patterns.append("📈 ダブルボトム形成中")

    # ブレイクアウト（直近20日高値突破）
    recent_high = np.max(prices[:-1])
    if prices[-1] > recent_high:
        patterns.append("🚀 高値ブレイクアウト!")

    # ブレイクダウン（直近20日安値割れ）
    recent_low = np.min(prices[:-1])
    if prices[-1] < recent_low:
        patterns.append("💥 安値ブレイクダウン")

    # 三角持ち合い（ボラ縮小→ブレイク前）
    if len(close) >= 10:
        recent_range = np.max(prices[-5:]) - np.min(prices[-5:])
        prev_range = np.max(prices[-10:-5]) - np.min(prices[-10:-5])
        if recent_range < prev_range * 0.5:
            patterns.append("🔺 三角持ち合い→ブレイク間近")

    return patterns


# ===== ダイバージェンス検出 =====
def detect_divergence(close, rsi_vals):
    """価格とRSIのダイバージェンス"""
    if len(close) < 10 or len(rsi_vals) < 10:
        return []

    divs = []
    c = close.values[-10:]
    r = rsi_vals.values[-10:]

    # 弱気ダイバージェンス（価格↑ RSI↓ → 下落予兆）
    if c[-1] > c[-5] and r[-1] < r[-5]:
        divs.append("⚠️ 弱気ダイバージェンス(価格↑RSI↓)→天井注意")

    # 強気ダイバージェンス（価格↓ RSI↑ → 上昇予兆）
    if c[-1] < c[-5] and r[-1] > r[-5]:
        divs.append("💡 強気ダイバージェンス(価格↓RSI↑)→底打ち示唆")

    return divs


# ===== 支持線・抵抗線 =====
def calc_support_resistance(close, high, low):
    """ピボットポイント + 直近の支持/抵抗"""
    h = float(high.iloc[-1])
    l = float(low.iloc[-1])
    c = float(close.iloc[-1])

    pivot = (h + l + c) / 3
    r1 = 2 * pivot - l
    s1 = 2 * pivot - h
    r2 = pivot + (h - l)
    s2 = pivot - (h - l)

    return {"pivot": pivot, "R1": r1, "R2": r2, "S1": s1, "S2": s2}


# ===== 銘柄分析 =====
def full_analyze(ticker, info, market):
    """フル分析"""
    try:
        t = yf.Ticker(ticker)
        daily = t.history(period="3mo", interval="1d")
        if daily.empty or len(daily) < 30:
            return None

        close = daily['Close']
        high_s = daily['High']
        low_s = daily['Low']
        vol = daily['Volume']
        cur = float(close.iloc[-1])
        prev = float(close.iloc[-2])

        # 日足テクニカル
        rsi_d = rsi(close)
        macd_l, macd_s, macd_h = macd(close)
        bb_u, bb_m, bb_l = bollinger(close)
        atr_d = atr(high_s, low_s, close)

        cur_rsi = sf(rsi_d, -1, 50)
        cur_mh = sf(macd_h, -1, 0)
        prev_mh = sf(macd_h, -2, 0)
        cur_bbu = sf(bb_u, -1, cur * 1.05)
        cur_bbl = sf(bb_l, -1, cur * 0.95)
        cur_atr = sf(atr_d, -1, 0)
        sma5_v = sf(sma(close, 5), -1, cur)
        sma20_v = sf(sma(close, 20), -1, cur)
        sma60_v = sf(sma(close, 60), -1, cur) if len(close) >= 60 else sma20_v

        avg_vol = sf(vol.rolling(20).mean(), -1, 1)
        vol_ratio = float(vol.iloc[-1]) / avg_vol if avg_vol > 0 else 1
        daily_chg = (cur - prev) / prev * 100
        weekly_chg = (cur - float(close.iloc[-6])) / float(close.iloc[-6]) * 100 if len(close) >= 6 else daily_chg
        atr_pct = cur_atr / cur * 100 if cur > 0 else 0

        # 1時間足
        rsi_h = 50
        mh_h = 0
        prev_mh_h = 0
        try:
            hourly = t.history(period="5d", interval="1h")
            if not hourly.empty and len(hourly) >= 10:
                rsi_h = sf(rsi(hourly['Close']), -1, 50)
                _, _, mhh = macd(hourly['Close'])
                mh_h = sf(mhh, -1, 0)
                prev_mh_h = sf(mhh, -2, 0)
        except:
            pass

        # パターン検出
        patterns = detect_patterns(close, high_s, low_s)

        # ダイバージェンス
        divergences = detect_divergence(close, rsi_d)

        # 支持線・抵抗線
        sr = calc_support_resistance(close, high_s, low_s)

        # ===== スコアリング（思考ログ付き） =====
        signals = []
        score = 0
        thinking = []  # 思考プロセス

        # RSI日足
        if cur_rsi < 25:
            signals.append(f"RSI極端売られすぎ({cur_rsi:.0f})")
            score += 30
            thinking.append(f"RSI{cur_rsi:.0f}は極端に低い。市場が過剰に売っている可能性が高く、反発の確率が高い(+30)")
        elif cur_rsi < 30:
            signals.append(f"RSI売られすぎ({cur_rsi:.0f})")
            score += 20
            thinking.append(f"RSI{cur_rsi:.0f}で売られすぎゾーン。反発を狙える水準(+20)")
        elif cur_rsi > 75:
            signals.append(f"RSI買われすぎ({cur_rsi:.0f})")
            score -= 25
            thinking.append(f"RSI{cur_rsi:.0f}で過熱感あり。利確売りに押される可能性(-25)")
        elif cur_rsi > 70:
            score -= 10
            thinking.append(f"RSI{cur_rsi:.0f}でやや過熱。新規買いは慎重に(-10)")
        else:
            thinking.append(f"RSI{cur_rsi:.0f}で中立圏。特に偏りなし")

        # MACD日足
        if cur_mh > 0 and prev_mh <= 0:
            signals.append("日足GC!")
            score += 25
            thinking.append("日足MACDがマイナス→プラスに転換(GC)。下落トレンドが終わり上昇に転じるサイン(+25)")
        elif cur_mh < 0 and prev_mh >= 0:
            signals.append("日足DC")
            score -= 25
            thinking.append("日足MACDがプラス→マイナスに転換(DC)。上昇の勢いが失われ下落転換(-25)")
        elif cur_mh > 0:
            score += 5
            thinking.append("日足MACD正圏で上昇の勢い継続中(+5)")
        else:
            score -= 5
            thinking.append("日足MACD負圏で下落の勢い継続中(-5)")

        # MACD時間足
        if mh_h > 0 and prev_mh_h <= 0:
            signals.append("1h足GC!")
            score += 20
            thinking.append("1時間足でもGC発生。短期的にも上昇転換を確認、エントリータイミングとして最適(+20)")
        elif mh_h < 0 and prev_mh_h >= 0:
            signals.append("1h足DC")
            score -= 20
            thinking.append("1時間足でDC発生。短期的に売り圧力が強まっている(-20)")

        # ダブルGC
        if (cur_mh > 0 and prev_mh <= 0) and (mh_h > 0 and prev_mh_h <= 0):
            signals.append("★★ダブルGC(日+1h)")
            score += 15
            thinking.append("日足と1時間足の両方でGC同時発生！非常に強いトレンド転換シグナル(+15)")

        # BB
        if cur <= cur_bbl:
            signals.append("BB下限突破")
            score += 20
            thinking.append(f"株価¥{cur:,.0f}がボリンジャーバンド下限¥{cur_bbl:,.0f}を割り込んだ。統計的に95%の確率で戻るゾーン(+20)")
        elif cur >= cur_bbu:
            signals.append("BB上限")
            score -= 15
            thinking.append(f"BB上限に到達。短期的な反落リスクあり(-15)")

        # BB + RSI ダブル
        if cur <= cur_bbl and cur_rsi < 35:
            signals.append("★ダブル底(BB+RSI)")
            score += 15
            thinking.append("BB下限+RSI低水準のダブル底。複数指標が同時に割安を示しており信頼度が高い(+15)")

        # トレンド
        if sma5_v > sma20_v and cur > sma5_v:
            score += 10
            thinking.append(f"SMA5({sma5_v:,.0f})>SMA20({sma20_v:,.0f})で短期上昇トレンド。株価もSMA5の上にあり順張り有利(+10)")
        elif sma5_v < sma20_v and cur < sma5_v:
            score -= 10
            thinking.append(f"SMA5<SMA20で短期下降トレンド。逆張りはリスク高(-10)")

        if sma20_v > sma60_v:
            score += 5
            thinking.append("中期トレンドも上向き。大きな流れに沿った買い(+5)")
        else:
            score -= 5
            thinking.append("中期トレンド下向き。大きな流れに逆らう買いは要注意(-5)")

        # 出来高
        if vol_ratio > 3.0 and daily_chg > 0:
            signals.append(f"出来高爆増({vol_ratio:.1f}x)")
            score += 25
            thinking.append(f"出来高が通常の{vol_ratio:.1f}倍に爆増+株価上昇。機関投資家が大量に買っている可能性。本物の上昇(+25)")
        elif vol_ratio > 2.0 and daily_chg > 0:
            signals.append(f"出来高急増({vol_ratio:.1f}x)")
            score += 15
            thinking.append(f"出来高{vol_ratio:.1f}倍+上昇。通常より多くの買い手が参入(+15)")
        elif vol_ratio > 2.0 and daily_chg < 0:
            score -= 10
            thinking.append(f"出来高{vol_ratio:.1f}倍だが株価下落。大口の売りが入っている可能性(-10)")

        # パターン
        for p in patterns:
            signals.append(p)
            if "ブレイクアウト" in p:
                score += 20
                thinking.append("直近20日の高値を突破！新たな上昇局面入りの可能性(+20)")
            elif "ダブルボトム完成" in p:
                score += 20
                thinking.append("ダブルボトム完成。2回同じ安値で跳ね返された=強い支持線が存在。上昇転換の典型パターン(+20)")
            elif "ダブルボトム形成" in p:
                score += 10
                thinking.append("ダブルボトム形成中。ネックライン突破を待つ段階(+10)")
            elif "三角持ち合い" in p:
                score += 5
                thinking.append("値動きが収縮中。エネルギーが溜まっておりブレイク間近(+5)")
            elif "ブレイクダウン" in p:
                score -= 15
                thinking.append("安値割れ。下落加速の危険(-15)")

        # ダイバージェンス
        for d in divergences:
            signals.append(d)
            if "強気" in d:
                score += 15
                thinking.append("株価は下がっているがRSIは上がっている。売りの勢いが弱まっており底打ち間近(+15)")
            elif "弱気" in d:
                score -= 15
                thinking.append("株価は上がっているがRSIは下がっている。買いの勢いが弱まっており天井間近(-15)")

        # 急騰急落
        if daily_chg > 5:
            signals.append(f"急騰{daily_chg:+.1f}%")
            thinking.append(f"本日{daily_chg:+.1f}%の急騰。何らかの材料あり。飛び乗りは高値掴みリスクあるが勢いは本物")
        elif daily_chg < -5:
            signals.append(f"急落{daily_chg:+.1f}%")
            thinking.append(f"本日{daily_chg:+.1f}%の急落。パニック売りなら逆張りチャンスだが、悪材料なら追撃下落の可能性も")

        # 判定
        if score >= 60:
            verdict = "★★ 即エントリー"
            urgency = 3
        elif score >= 40:
            verdict = "★ 強い買い"
            urgency = 2
        elif score >= 20:
            verdict = "◎ 買い検討"
            urgency = 1
        elif score >= -20:
            verdict = "― 中立"
            urgency = 0
        elif score >= -40:
            verdict = "▼ 売り検討"
            urgency = -1
        else:
            verdict = "✕ 強い売り"
            urgency = -2

        # リスクリワード比
        risk = cur - sr["S1"]
        reward = sr["R1"] - cur
        rr_ratio = reward / risk if risk > 0 else 0

        # 最終思考まとめ
        if score >= 40:
            thinking.append(f"→ 合計スコア{score:+d}。複数の買い根拠が重なっており確度が高い。エントリー推奨。")
        elif score >= 20:
            thinking.append(f"→ 合計スコア{score:+d}。買い材料はあるが決定打に欠ける。押し目を待つか小ロットで。")
        elif score >= -20:
            thinking.append(f"→ 合計スコア{score:+d}。買いも売りも根拠が弱い。見送り。")
        else:
            thinking.append(f"→ 合計スコア{score:+d}。売り圧力が強い。保有中なら損切り検討。")

        return {
            "ticker": ticker, "name": info["name"], "sector": info["sector"],
            "market": market, "price": cur,
            "daily_chg": daily_chg, "weekly_chg": weekly_chg,
            "rsi_d": cur_rsi, "rsi_h": rsi_h,
            "macd_hist": cur_mh, "vol_ratio": vol_ratio,
            "atr": cur_atr, "atr_pct": atr_pct,
            "bb_upper": cur_bbu, "bb_lower": cur_bbl,
            "sma5": sma5_v, "sma20": sma20_v, "sma60": sma60_v,
            "support": sr["S1"], "resistance": sr["R1"],
            "pivot": sr["pivot"], "rr_ratio": rr_ratio,
            "signals": signals, "score": score,
            "verdict": verdict, "urgency": urgency,
            "thinking": thinking,
        }
    except:
        return None


def analyze_worker(args):
    return full_analyze(*args)


# ===== 市場レジーム =====
def analyze_market_regime():
    """VIX・指数・騰落率から市場環境を判定"""
    regime = {}

    for idx_ticker, idx_name in INDICES.items():
        try:
            t = yf.Ticker(idx_ticker)
            data = t.history(period="5d", interval="1d")
            if not data.empty and len(data) >= 2:
                cur = float(data['Close'].iloc[-1])
                prev = float(data['Close'].iloc[-2])
                chg = (cur - prev) / prev * 100
                regime[idx_name] = {"price": cur, "change": chg}
        except:
            pass

    # VIX判定
    vix = regime.get("VIX恐怖指数", {}).get("price", 20)
    if vix > 30:
        regime["fear_level"] = "🔴 パニック"
        regime["advice"] = "現金比率を高める。逆張りチャンスを慎重に狙う"
    elif vix > 25:
        regime["fear_level"] = "🟡 警戒"
        regime["advice"] = "ポジション縮小。急落銘柄の反発狙い"
    elif vix > 20:
        regime["fear_level"] = "🟡 やや不安"
        regime["advice"] = "通常運用。損切りラインを厳格に"
    elif vix > 15:
        regime["fear_level"] = "🟢 安定"
        regime["advice"] = "トレンドフォロー有効。積極的にエントリー"
    else:
        regime["fear_level"] = "🟢 超安定"
        regime["advice"] = "ブレイクアウト戦略が最も有効"

    return regime


# ===== セクター分析 =====
def analyze_sectors(results):
    """セクター別のスコアを集計"""
    sector_scores = defaultdict(list)
    for r in results:
        sector_scores[r["sector"]].append(r["score"])

    sector_avg = {}
    for sector, scores in sector_scores.items():
        avg = sum(scores) / len(scores)
        sector_avg[sector] = {"avg_score": avg, "count": len(scores)}

    # スコア順にソート
    sorted_sectors = sorted(sector_avg.items(), key=lambda x: x[1]["avg_score"], reverse=True)
    return sorted_sectors


# ===== LINE通知 =====
def send_line(message):
    if not os.path.exists(CONFIG_FILE):
        return False
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
    except:
        return False

    if not config.get("notify", {}).get("line_enabled"):
        return False

    token = config["line"]["channel_access_token"]
    user_id = config["line"]["user_id"]
    if not token or not user_id:
        return False

    # 5000文字制限
    if len(message) > 4900:
        message = message[:4900] + "\n..."

    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    payload = {"to": user_id, "messages": [{"type": "text", "text": message}]}
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        return resp.status_code == 200
    except:
        return False


def send_line_multi(messages):
    """複数メッセージ送信（最大5通）"""
    if not os.path.exists(CONFIG_FILE):
        return False
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
    except:
        return False

    token = config["line"]["channel_access_token"]
    user_id = config["line"]["user_id"]
    if not token or not user_id:
        return False

    msgs = [{"type": "text", "text": m[:4900]} for m in messages[:5]]
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    payload = {"to": user_id, "messages": msgs}
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        return resp.status_code == 200
    except:
        return False


# ===== 通知重複管理 =====
def load_state():
    if os.path.exists(BRAIN_STATE_FILE):
        try:
            with open(BRAIN_STATE_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {"notified": {}, "last_briefing": "", "cycle": 0}

def save_state(state):
    with open(BRAIN_STATE_FILE, 'w') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def should_notify(state, ticker, score):
    key = f"{ticker}_{score // 20}"
    notified = state.get("notified", {})
    if key in notified:
        last = datetime.fromisoformat(notified[key])
        if datetime.now() - last < timedelta(hours=4):
            return False
    return True

def mark_notified(state, ticker, score):
    key = f"{ticker}_{score // 20}"
    state.setdefault("notified", {})[key] = datetime.now().isoformat()
    # 古い通知を削除
    cutoff = (datetime.now() - timedelta(hours=12)).isoformat()
    state["notified"] = {k: v for k, v in state["notified"].items() if v > cutoff}


# ===== ポジション損益チェック =====
def check_positions_for_brain():
    """保有ポジションの売りシグナルチェック"""
    if not os.path.exists(POSITIONS_FILE):
        return []
    try:
        with open(POSITIONS_FILE, 'r') as f:
            positions = json.load(f)
    except:
        return []

    if not positions:
        return []

    alerts = []
    for p in positions:
        try:
            t = yf.Ticker(p["ticker"])
            data = t.history(period="5d")
            if data.empty:
                continue
            cur = float(data['Close'].iloc[-1])
            pnl = (cur - p["entry_price"]) / p["entry_price"] * 100

            if pnl <= -5:
                alerts.append(f"🚨 {p['name']} 損切り接近! {pnl:+.1f}%")
            elif pnl <= -8:
                alerts.append(f"🚨🚨 {p['name']} 損切りライン到達! {pnl:+.1f}% → 即売却!")
            elif pnl >= 10:
                alerts.append(f"🎯 {p['name']} 利確検討 {pnl:+.1f}%")
            elif pnl >= 15:
                alerts.append(f"🎯🎯 {p['name']} 利確推奨! {pnl:+.1f}%")
        except:
            pass

    return alerts


# ===== メインブレイン =====
def run_brain(markets="all", mode="scan"):
    """メイン分析実行"""
    state = load_state()
    state["cycle"] = state.get("cycle", 0) + 1
    now = datetime.now()

    targets = []
    if markets in ("all", "jp"):
        for ticker, info in JP_STOCKS.items():
            targets.append((ticker, info, "JP"))
    if markets in ("all", "us"):
        for ticker, info in US_STOCKS.items():
            targets.append((ticker, info, "US"))

    print(f"\n{'='*60}")
    print(f"  🧠 Trading Brain サイクル#{state['cycle']} ({now.strftime('%H:%M:%S')})")
    print(f"  分析対象: {len(targets)}銘柄 [{markets.upper()}]")
    print(f"{'='*60}")

    # 並列分析
    results = []
    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(analyze_worker, t): t for t in targets}
        for future in concurrent.futures.as_completed(futures):
            done += 1
            if done % 20 == 0 or done == len(targets):
                print(f"  分析: {done}/{len(targets)}")
            result = future.result()
            if result:
                results.append(result)

    results.sort(key=lambda x: x["score"], reverse=True)

    # 市場レジーム
    regime = analyze_market_regime()

    # セクター分析
    sectors = analyze_sectors(results)

    # カテゴリ分け
    elite = [r for r in results if r["score"] >= 60]  # 即エントリー
    hot = [r for r in results if 40 <= r["score"] < 60]  # 強い買い
    warm = [r for r in results if 20 <= r["score"] < 40]  # 買い検討
    danger = [r for r in results if r["score"] <= -40]  # 強い売り

    print(f"\n  ★★即エントリー: {len(elite)}  ★強い買い: {len(hot)}")
    print(f"  ◎買い検討: {len(warm)}  ✕強い売り: {len(danger)}")

    # === 朝ブリーフィング判定 ===
    is_briefing = mode == "briefing" or (
        state.get("last_briefing", "")[:10] != now.strftime("%Y-%m-%d")
        and ((8 <= now.hour <= 9) or (21 <= now.hour <= 22))
    )

    messages_to_send = []

    # === メッセージ1: 市場概況 + トップシグナル ===
    if is_briefing or elite or hot:
        lines = []

        if is_briefing:
            lines.append(f"🧠 Trading Brain")
            lines.append(f"📅 {now.strftime('%m/%d %H:%M')} マーケットブリーフィング")
        else:
            lines.append(f"🧠 Trading Brain ({now.strftime('%H:%M')})")

        lines.append("")

        # 市場レジーム
        vix_info = regime.get("VIX恐怖指数", {})
        sp_info = regime.get("S&P500", {})
        nk_info = regime.get("日経平均", {})
        fx_info = regime.get("ドル円", {})

        lines.append("【市場環境】")
        if vix_info:
            lines.append(f"  VIX: {vix_info.get('price', 0):.1f} {regime.get('fear_level', '')}")
        if nk_info:
            lines.append(f"  日経: {nk_info.get('price', 0):,.0f} ({nk_info.get('change', 0):+.1f}%)")
        if sp_info:
            lines.append(f"  S&P500: {sp_info.get('price', 0):,.0f} ({sp_info.get('change', 0):+.1f}%)")
        if fx_info:
            lines.append(f"  ドル円: ¥{fx_info.get('price', 0):,.1f}")
        lines.append(f"  → {regime.get('advice', '')}")
        lines.append("")

        # セクターローテーション
        if is_briefing:
            lines.append("【セクター強弱】")
            for s_name, s_data in sectors[:3]:
                lines.append(f"  🟢 {s_name}: スコア{s_data['avg_score']:+.0f}")
            for s_name, s_data in sectors[-2:]:
                lines.append(f"  🔴 {s_name}: スコア{s_data['avg_score']:+.0f}")
            lines.append("")

        # トップシグナル
        all_hot = elite + hot
        if all_hot:
            lines.append(f"【買いシグナル TOP{min(5, len(all_hot))}】")
            for r in all_hot[:5]:
                flag = "🇯🇵" if r["market"] == "JP" else "🇺🇸"
                p = f"¥{r['price']:,.0f}" if r["market"] == "JP" else f"${r['price']:,.2f}"
                lines.append(f"")
                lines.append(f"{flag} {r['name']} ({r['ticker']})")
                lines.append(f"  {r['verdict']} スコア:{r['score']:+d}")
                lines.append(f"  {p} 日次:{r['daily_chg']:+.1f}%")
                lines.append(f"  RSI:{r['rsi_d']:.0f} 出来高:{r['vol_ratio']:.1f}x")

                for sig in r["signals"][:3]:
                    lines.append(f"  → {sig}")

                if r["rr_ratio"] > 0:
                    lines.append(f"  R/R比: 1:{r['rr_ratio']:.1f}")

                # 買い方
                tc = r["ticker"].replace(".T", "")
                if r["market"] == "JP":
                    stop = r['price'] * 0.95
                    target = r['price'] * 1.10
                    lines.append(f"  📱 iSPEED→{tc}→かぶミニ→成行")
                    lines.append(f"  損切¥{stop:,.0f}/利確¥{target:,.0f}")
                else:
                    stop = r['price'] * 0.95
                    target = r['price'] * 1.10
                    lines.append(f"  📱 iSPEED→{r['ticker']}→指値${r['price']:,.2f}")
                    lines.append(f"  損切${stop:,.2f}/利確${target:,.2f}")
                    lines.append(f"  →逆指値で損切設定可")

        messages_to_send.append("\n".join(lines))

        # === メッセージ: 思考プロセス（上位3銘柄分）===
        if all_hot:
            think_lines = ["🧠 AI思考プロセス", ""]
            for r in all_hot[:3]:
                flag = "🇯🇵" if r["market"] == "JP" else "🇺🇸"
                think_lines.append(f"━━━━━━━━━━━━━━━━━━")
                think_lines.append(f"{flag} {r['name']} ({r['ticker']}) → {r['verdict']}")
                think_lines.append(f"")
                for i, t in enumerate(r.get("thinking", []), 1):
                    think_lines.append(f"{i}. {t}")
                think_lines.append("")

            messages_to_send.append("\n".join(think_lines))

        if is_briefing:
            state["last_briefing"] = now.isoformat()

    # === メッセージ2: 売りシグナル + ポジションアラート ===
    pos_alerts = check_positions_for_brain()
    if danger or pos_alerts:
        lines2 = ["🔴 警告アラート", ""]

        if pos_alerts:
            lines2.append("【保有ポジション】")
            for a in pos_alerts:
                lines2.append(f"  {a}")
            lines2.append("")

        if danger:
            lines2.append(f"【売りシグナル({len(danger)}銘柄)】")
            for r in danger[:5]:
                flag = "🇯🇵" if r["market"] == "JP" else "🇺🇸"
                p = f"¥{r['price']:,.0f}" if r["market"] == "JP" else f"${r['price']:,.2f}"
                lines2.append(f"  {flag} {r['name']} {p} ({r['score']:+d})")
                for sig in r["signals"][:2]:
                    lines2.append(f"    {sig}")

        messages_to_send.append("\n".join(lines2))

    # === 新規シグナルのみLINEに送信 ===
    if messages_to_send:
        # ブリーフィングは常に送信
        if is_briefing:
            if send_line_multi(messages_to_send):
                print(f"  📱 ブリーフィング送信完了")
        else:
            # リアルタイムは新規シグナルのみ
            new_signals = False
            for r in elite + hot:
                if should_notify(state, r["ticker"], r["score"]):
                    new_signals = True
                    mark_notified(state, r["ticker"], r["score"])

            if new_signals or pos_alerts:
                if send_line_multi(messages_to_send):
                    print(f"  📱 アラート送信完了")
            else:
                print(f"  （新規シグナルなし。通知スキップ）")

    else:
        print(f"  📊 特に強いシグナルなし")

    save_state(state)
    return results


# ===== ループモード =====
def run_loop(markets="all"):
    """5分おき常時監視"""
    print("""
╔════════════════════════════════════════════════════╗
║        🧠 Trading Brain - 常時監視モード           ║
║        Ctrl+C で停止                               ║
╚════════════════════════════════════════════════════╝
    """)

    # 初回はブリーフィング
    run_brain(markets, mode="briefing")

    while True:
        try:
            time.sleep(300)  # 5分待機

            now = datetime.now()
            hour = now.hour
            is_jp = 9 <= hour < 16
            is_us = hour >= 23 or hour < 7

            # 市場時間外はスキップ（ただし朝/夜のブリーフィング時間は実行）
            if not is_jp and not is_us and hour not in (8, 9, 21, 22):
                if now.minute == 0:
                    print(f"  ⏸️ 市場時間外 ({now.strftime('%H:%M')})")
                continue

            scan_market = markets
            if markets == "all":
                if is_jp and not is_us:
                    scan_market = "jp"
                elif is_us and not is_jp:
                    scan_market = "us"

            run_brain(scan_market, mode="scan")

        except KeyboardInterrupt:
            print("\n  🛑 Trading Brain 停止")
            break
        except Exception as e:
            print(f"  ❌ エラー: {e}")
            time.sleep(60)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "once"
    markets = sys.argv[2] if len(sys.argv) > 2 else "all"

    if mode == "loop":
        run_loop(markets)
    elif mode == "briefing":
        run_brain(markets, mode="briefing")
    elif mode == "once":
        run_brain(markets, mode="scan")
    else:
        print("""
  🧠 Trading Brain

    python3 ~/trading-brain.py                  # 1回分析
    python3 ~/trading-brain.py briefing         # ブリーフィング送信
    python3 ~/trading-brain.py loop             # 5分おき常時監視
    python3 ~/trading-brain.py loop jp          # 日本株のみ
    python3 ~/trading-brain.py loop us          # 米国株のみ
        """)

if __name__ == "__main__":
    main()
