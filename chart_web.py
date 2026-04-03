import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from ta.momentum import RSIIndicator
from ta.trend import MACD
from ta.volatility import BollingerBands
import mplfinance as mpf
import json
import os
import requests
import xml.etree.ElementTree as ET

WATCHLIST_FILE = "watchlist_v6.json"

st.set_page_config(page_title="AI 퀀트 대시보드", page_icon="📊", layout="wide")

# ==========================================
# 🌟 관심종목 파일 로드 및 저장 함수
# ==========================================
def load_watchlist():
    if os.path.exists(WATCHLIST_FILE):
        try:
            with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: pass
    return ["BTC"]

def save_watchlist(watchlist):
    with open(WATCHLIST_FILE, 'w', encoding='utf-8') as f:
        json.dump(watchlist, f, ensure_ascii=False, indent=4)

# ==========================================
# 사이드바: 관심종목 관리 및 분석 설정
# ==========================================
st.sidebar.title("📌 관심종목 관리")
current_watchlist = load_watchlist()

# 종목 추가
new_ticker = st.sidebar.text_input("새 종목코드 입력 (예: ETH, 005930)").upper().strip()
if st.sidebar.button("➕ 리스트에 추가", use_container_width=True):
    if new_ticker and new_ticker not in current_watchlist:
        current_watchlist.append(new_ticker)
        save_watchlist(current_watchlist)
        st.sidebar.success(f"'{new_ticker}' 추가 완료!")
        st.rerun()
    elif new_ticker in current_watchlist:
        st.sidebar.warning("이미 등록된 종목입니다.")

# 종목 삭제
if current_watchlist:
    del_ticker = st.sidebar.selectbox("삭제할 종목 선택", current_watchlist)
    if st.sidebar.button("➖ 리스트에서 삭제", use_container_width=True):
        current_watchlist.remove(del_ticker)
        save_watchlist(current_watchlist)
        st.sidebar.success(f"'{del_ticker}' 삭제 완료!")
        st.rerun()

st.sidebar.markdown("---")
st.sidebar.title("⚙️ 분석 설정")
ticker = st.sidebar.selectbox("분석할 종목코드", current_watchlist) if current_watchlist else "BTC"
tf_selection = st.sidebar.selectbox("차트 시간대", ["1시간", "4시간", "일봉", "주봉"], index=1)
lookback = st.sidebar.number_input("파동 기준봉", min_value=30, max_value=300, value=60)
target_fib = st.sidebar.selectbox("피보나치 목표", [0.382, 0.500, 0.618, 0.786], index=2)

# ==========================================
# 메인 화면 영역
# ==========================================
st.title("📊 나만의 퀀트 분석 웹사이트")
st.markdown("PC는 물론 스마트폰에서도 접속하여 실시간 차트와 분석 리포트를 확인할 수 있습니다.")

@st.cache_data(ttl=300) 
def get_data(symbol, tf, limit):
    try:
        # 📈 1. 한국 주식 (네이버 금융 API 호출)
        if symbol.endswith(".KS") or symbol.endswith(".KQ") or (len(symbol) == 6 and symbol.isdigit()):
            clean_symbol = ''.join(filter(str.isdigit, symbol))
            naver_tf = {"일봉": "day", "주봉": "week"}.get(tf, "day") 
            
            url = f"https://fchart.stock.naver.com/sise.nhn?symbol={clean_symbol}&timeframe={naver_tf}&count={limit + 50}&requestType=0"
            res = requests.get(url)
            
            if res.status_code != 200:
                st.error("네이버 금융 서버와 연결할 수 없습니다.")
                return pd.DataFrame()
            
            xml_str = res.content.decode('euc-kr', 'replace').replace('EUC-KR', 'utf-8').replace('euc-kr', 'utf-8')
            root = ET.fromstring(xml_str.encode('utf-8'))
            
            items = root.findall('.//item')
            if not items:
                st.error(f"[{symbol}] 네이버 금융에 존재하지 않는 종목코드이거나 상장폐지된 종목입니다.")
                return pd.DataFrame()
                
            data = [item.attrib['data'].split('|') for item in items]
            df = pd.DataFrame(data, columns=['Date', 'Open', 'High', 'Low', 'Close', 'Volume'])
            
            df['Date'] = pd.to_datetime(df['Date'])
            df.set_index('Date', inplace=True)
            for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
                df[col] = df[col].astype(float)
                
            return df.tail(limit)

        # 🪙 2. 코인 (바이낸스 API 직접 호출)
        else:
            clean_symbol = symbol.replace("-USD", "").replace("USDT", "") + "USDT"
            binance_itv = {"1시간": "1h", "4시간": "4h", "일봉": "1d", "주봉": "1w"}.get(tf, "1d")
            
            url = "https://api.binance.com/api/v3/klines"
            params = {"symbol": clean_symbol, "interval": binance_itv, "limit": limit + 50}
            res = requests.get(url, params=params)
            
            if res.status_code != 200:
                st.error(f"바이낸스에서 {clean_symbol} 데이터를 찾을 수 없습니다.")
                return pd.DataFrame()

            data = res.json()
            df = pd.DataFrame(data, columns=['Open time', 'Open', 'High', 'Low', 'Close', 'Volume', 'Close time', 'Quote asset volume', 'Number of trades', 'Taker buy base asset volume', 'Taker buy quote asset volume', 'Ignore'])
            
            df.index = pd.to_datetime(df['Open time'], unit='ms') + pd.Timedelta(hours=9)
            for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
                df[col] = df[col].astype(float)

            return df[['Open', 'High', 'Low', 'Close', 'Volume']].tail(limit)

    except Exception as e:
        st.error(f"데이터 로딩 중 에러 발생: {e}")
        return pd.DataFrame()

if st.button("🔍 차트 분석 실행", type="primary"):
    with st.spinner(f"[{ticker}] 데이터를 불러오고 차트를 그리는 중..."):
        df = get_data(ticker, tf_selection, lookback + 50)
        
        if df.empty:
            st.error("데이터를 불러오지 못했습니다. 종목코드를 다시 확인해 주세요.")
        else:
            # 1. 보조지표 계산
            df['SMA20'] = df['Close'].rolling(20).mean()
            bb = BollingerBands(df['Close'], window=20, window_dev=2)
            df['BB_H'] = bb.bollinger_hband()
            df['BB_L'] = bb.bollinger_lband()
            df['RSI'] = RSIIndicator(df['Close'], window=14).rsi()
            macd = MACD(df['Close'])
            df['MACD_Line'] = macd.macd()
            df['MACD_Signal'] = macd.macd_signal()
            df['MACD_Hist'] = macd.macd_diff()
            
            plot_df = df.tail(lookback).copy()
            current_close = float(plot_df['Close'].iloc[-1])
            curr_rsi = float(plot_df['RSI'].iloc[-1])
            
            # 🌟 2. FVG (공정 가치 갭) 시각화 데이터 계산 (화면에 보이는 차트 기준)
            fvg_top = None
            fvg_bottom = None
            
            for i in range(len(plot_df)-30, len(plot_df)-2):
                if i < 0: continue
                c1_high = plot_df['High'].iloc[i]
                c3_low = plot_df['Low'].iloc[i+2]
                
                # 상승 FVG 발견
                if c3_low > c1_high:
                    is_filled = False
                    for j in range(i+3, len(plot_df)-1):
                        if plot_df['Low'].iloc[j] <= c1_high:
                            is_filled = True
                            break
                    
                    if not is_filled:
                        fvg_top = c3_low
                        fvg_bottom = c1_high
            
            # 3. 화면 분할 및 출력
            col1, col2 = st.columns([1, 2.5])
            
            with col1:
                st.subheader("📝 분석 리포트")
                
                currency = "₩" if ticker.endswith(".KS") or ticker.endswith(".KQ") or ticker.isdigit() else "$"
                format_str = ",.0f" if currency == "₩" else ",.2f"
                
                st.write(f"**현재가:** {currency}{current_close:{format_str}}")
                st.write(f"**현재 RSI:** {curr_rsi:.2f}")
                
                if curr_rsi < 35:
                    st.success("🟢 [매수 시그널] RSI 과매도 구간 진입")
                elif curr_rsi > 65:
                    st.error("🔴 [매도 시그널] RSI 과매수 구간 진입")
                else:
                    st.warning("⚪ [관망] 뚜렷한 진입 근거 부족")
                    
                st.metric(label="목표 피보나치 달성률", value=f"{target_fib * 100}%", delta="진입 대기")

                # 🌟 FVG 구간 리포트 추가
                st.markdown("---")
                st.write("**🏦 스마트 머니 (FVG) 분석**")
                if fvg_top and fvg_bottom:
                    st.info(f"🧲 대기 구간: {currency}{fvg_bottom:{format_str}} ~ {currency}{fvg_top:{format_str}}")
                    if fvg_bottom <= current_close <= fvg_top:
                        st.success("🎯 현재 주가가 FVG 구역 내부에 진입했습니다! (타점 포착)")
                    else:
                        st.write("주가가 아직 FVG 구역에 진입하지 않았습니다.")
                else:
                    st.write("발견된 미체결 FVG(빈 공간)가 없습니다.")

            with col2:
                s = mpf.make_mpf_style(base_mpf_style='nightclouds')
                macd_colors = ['#26a69a' if val > 0 else '#ef5350' for val in plot_df['MACD_Hist']]
                
                ap = [
                    mpf.make_addplot(plot_df['BB_H'], color='cyan', alpha=0.5),
                    mpf.make_addplot(plot_df['BB_L'], color='cyan', alpha=0.5),
                    mpf.make_addplot(plot_df['SMA20'], color='yellow'),
                    mpf.make_addplot(plot_df['RSI'], panel=1, color='magenta', ylabel='RSI'),
                    mpf.make_addplot(plot_df['MACD_Hist'], type='bar', panel=2, color=macd_colors, alpha=0.5, ylabel='MACD'),
                    mpf.make_addplot(plot_df['MACD_Line'], panel=2, color='deepskyblue'),
                    mpf.make_addplot(plot_df['MACD_Signal'], panel=2, color='orange'),
                ]
                
                # 🌟 차트에 FVG 라인 점선으로 그리기
                fvg_lines = None
                if fvg_top and fvg_bottom:
                    fvg_lines = dict(hlines=[fvg_bottom, fvg_top], colors=['#00FF00', '#00FF00'], linestyle='--', linewidths=1.5, alpha=0.7)

                # FVG 라인이 있으면 포함해서 그리고, 없으면 기본 차트만 그림
                if fvg_lines:
                    fig, axes = mpf.plot(
                        plot_df, type='candle', style=s, addplot=ap,
                        panel_ratios=(4, 1.5, 1.5), figsize=(10, 7), returnfig=True,
                        title=f"{ticker} ({tf_selection})", hlines=fvg_lines
                    )
                else:
                    fig, axes = mpf.plot(
                        plot_df, type='candle', style=s, addplot=ap,
                        panel_ratios=(4, 1.5, 1.5), figsize=(10, 7), returnfig=True,
                        title=f"{ticker} ({tf_selection})"
                    )
                st.pyplot(fig)
