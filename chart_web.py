import streamlit as st
import pandas as pd
import yfinance as yf
from ta.momentum import RSIIndicator
from ta.trend import MACD
from ta.volatility import BollingerBands
import FinanceDataReader as fdr
import concurrent.futures
from datetime import datetime, timedelta
import re

# ==========================================
# 💎 1. 웹페이지 기본 설정 (모바일 최적화)
# ==========================================
st.set_page_config(page_title="PRO 퀀트 스캐너 웹", page_icon="🚀", layout="wide")

# ==========================================
# 🧠 2. 데이터 캐싱 (매번 다운로드 방지하여 속도 극대화)
# ==========================================
@st.cache_data(ttl=3600) 
def load_krx_data():
    df_krx = fdr.StockListing('KRX')
    df_desc = fdr.StockListing('KRX-DESC')
    
    theme_dict = {}
    for _, row in df_desc.iterrows():
        sector = str(row['Sector']) if pd.notna(row['Sector']) else ""
        industry = str(row['Industry']) if pd.notna(row['Industry']) else ""
        theme_dict[row['Code']] = f"{sector} ({industry})" if sector and industry else (sector or industry or "정보 없음")
        
    return df_krx, df_desc, theme_dict

# ==========================================
# ⚙️ 3. 단일 종목 분석 엔진
# ==========================================
def analyze_single_stock(code, name, ticker_yf, condition_type, start_date, use_shield):
    try:
        df = fdr.DataReader(code, start_date)
        if df.empty or len(df) < 230: return None
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']: df[col] = pd.to_numeric(df[col], errors='coerce')
        df = df.dropna(subset=['Close'])

        df['SMA20'] = df['Close'].rolling(window=20).mean(); df['SMA224'] = df['Close'].rolling(window=224).mean()
        bb = BollingerBands(close=df['Close'], window=20, window_dev=2); df['BB_L'] = bb.bollinger_lband()
        df['RSI'] = RSIIndicator(close=df['Close'], window=14).rsi()
        macd = MACD(close=df['Close']); df['MACD_Line'] = macd.macd(); df['MACD_Hist'] = macd.macd_diff()
        
        curr_close = float(df['Close'].iloc[-1]); prev_close = float(df['Close'].iloc[-2])
        curr_volume = float(df['Volume'].iloc[-1]); avg_volume = float(df['Volume'].tail(6).head(5).mean())
        curr_rsi = float(df['RSI'].iloc[-1]); curr_bb_l = float(df['BB_L'].iloc[-1])
        curr_macd_hist = float(df['MACD_Hist'].iloc[-1]); prev_macd_hist = float(df['MACD_Hist'].iloc[-2])
        curr_macd_line = float(df['MACD_Line'].iloc[-1])
        curr_sma224 = float(df['SMA224'].iloc[-1]); prev_sma224 = float(df['SMA224'].iloc[-2])

        matched_conds = []; reasons = []

        if condition_type in ["A", "ALL"]:
            if curr_rsi <= 40 and curr_close <= curr_bb_l * 1.03: matched_conds.append("A"); reasons.append(f"[A] RSI바닥+볼린저")
        if condition_type in ["B", "ALL"]:
            if curr_macd_line < 0 and curr_macd_hist > prev_macd_hist and prev_macd_hist < 0: matched_conds.append("B"); reasons.append("[B] MACD 턴어라운드")
        if condition_type in ["C", "ALL"]:
            score = 0
            if curr_rsi <= 40: score += 1
            elif curr_rsi > float(df['RSI'].iloc[-2]) and float(df['RSI'].iloc[-2]) < 35: score += 2
            if curr_close <= curr_bb_l * 1.02: score += 1
            if curr_macd_hist > 0 and prev_macd_hist <= 0: score += 2
            elif curr_macd_hist > prev_macd_hist and curr_macd_hist < 0: score += 1
            if score >= 3: matched_conds.append("C"); reasons.append(f"[C] 퀀트점수 {score}점")
        if condition_type in ["D", "ALL"]:
            if curr_rsi <= 45:
                try:
                    pbr = yf.Ticker(ticker_yf).info.get('priceToBook', 99)
                    if pbr and float(pbr) <= 1.0: matched_conds.append("D"); reasons.append(f"[D] PBR {float(pbr):.2f}+차트바닥")
                except: pass
        if condition_type in ["E", "ALL"]:
            if (prev_close <= prev_sma224) and (curr_close > curr_sma224) and (curr_volume >= avg_volume * 2.0):
                matched_conds.append("E"); reasons.append(f"[🍚E] 밥그릇3번(거래량 {curr_volume / avg_volume if avg_volume > 0 else 0:.1f}배)")

        if matched_conds:
            if use_shield:
                try:
                    eps = yf.Ticker(ticker_yf).info.get('trailingEps', 1)
                    if eps is not None and float(eps) < 0: return None 
                except: pass

            final_reason = f"🔥 [중복 포착: {', '.join(matched_conds)}] " + " / ".join(reasons) if len(matched_conds) >= 2 else reasons[0]
            return {"code": code, "name": name, "close": curr_close, "reason": final_reason}
        return None
    except Exception: return None

# ==========================================
# 🎨 4. 웹 화면 UI 구성 (사이드바 & 메인)
# ==========================================
st.title("🚀 PRO 퀀트 스캐너 (Web Edition)")
st.markdown("스마트폰에서도 언제 어디서나 시장을 스캔하세요!")

with st.sidebar:
    st.header("⚙️ 스캔 설정")
    
    strategy_options = {
        "A. 바닥권 줍기": "A", "B. 턴어라운드": "B", 
        "C. 퀀트 판독기": "C", "D. 가치투자 융합": "D", 
        "🍚 E. 밥그릇 3번 자리": "E", "🌟 전술 통합 스캔 (ALL)": "ALL"
    }
    selected_strategy = st.selectbox("1. 전술을 선택하세요", list(strategy_options.keys()))
    condition_type = strategy_options[selected_strategy]
    
    st.divider() 
    
    theme_keyword = st.text_input("🔍 2. 테마 필터링 (선택)", placeholder="예: 반도체, 로봇")
    use_shield = st.checkbox("🛡️ 상폐 방어막 가동 (적자 제외)", value=True)
    
    st.divider()
    
    vip_file = st.file_uploader("🎯 3. VIP 관심종목 텍스트 업로드", type=['txt'])
    custom_tickers = None
    if vip_file is not None:
        content = vip_file.getvalue().decode("utf-8")
        custom_tickers = [re.search(r'\d{6}', line).group() for line in content.splitlines() if re.search(r'\d{6}', line)]
        st.success(f"{len(custom_tickers)}개 관심종목 로드 완료!")

    st.divider()
    start_btn = st.button("▶️ 스캔 시작", use_container_width=True, type="primary")

# ==========================================
# 🏃‍♂️ 5. 스캔 실행 및 결과 출력
# ==========================================
if 'scan_result' not in st.session_state:
    st.session_state['scan_result'] = pd.DataFrame()

if start_btn:
    df_krx, df_desc, theme_dict = load_krx_data()
    
    if theme_keyword:
        mask = df_desc['Sector'].fillna('').str.contains(theme_keyword, case=False) | df_desc['Industry'].fillna('').str.contains(theme_keyword, case=False) | df_desc['Name'].fillna('').str.contains(theme_keyword, case=False)
        theme_codes = df_desc[mask]['Code'].tolist()
        df_krx = df_krx[df_krx['Code'].isin(theme_codes)]
    elif custom_tickers:
        df_krx = df_krx[df_krx['Code'].isin(custom_tickers)]
    else:
        df_krx = df_krx[df_krx['Marcap'] > 0].sort_values('Marcap', ascending=False)
        
    total_stocks = len(df_krx)
    
    if total_stocks == 0:
        st.error("⚠️ 조건에 맞는 종목이 없습니다.")
    else:
        progress_text = st.empty()
        progress_bar = st.progress(0)
        
        start_date = (datetime.now() - timedelta(days=550)).strftime('%Y-%m-%d')
        results_list = []
        completed_count = 0

        with concurrent.futures.ThreadPoolExecutor(max_workers=7) as executor:
            futures = {}
            for _, row in df_krx.iterrows():
                code = row['Code']; name = row['Name']
                ticker_yf = code + (".KS" if row['Market'] == 'KOSPI' else ".KQ")
                futures[executor.submit(analyze_single_stock, code, name, ticker_yf, condition_type, start_date, use_shield)] = name

            for future in concurrent.futures.as_completed(futures):
                completed_count += 1
                name = futures[future]
                
                if completed_count % 5 == 0 or completed_count == total_stocks:
                    progress_val = int((completed_count / total_stocks) * 100)
                    progress_bar.progress(progress_val)
                    progress_text.text(f"🔍 스캔 중... [{completed_count}/{total_stocks}] {name} 분석 완료 | 포착: {len(results_list)}개")

                try:
                    res = future.result(timeout=10)
                    if res:
                        res['theme'] = theme_dict.get(res['code'], "정보 없음")
                        results_list.append([res['code'], res['name'], res['theme'], f"{res['close']:,.0f}", res['reason']])
                except: continue

        progress_text.success(f"✅ 스캔 완료! 총 {len(results_list)}개의 종목이 포착되었습니다.")
        
        if results_list:
            df_result = pd.DataFrame(results_list, columns=["종목코드", "종목명", "테마/업종", "현재가(원)", "상세 포착 이유"])
            st.session_state['scan_result'] = df_result

# ==========================================
# 📊 6. 결과 렌더링 및 필터링 기능 (UI 강조 업데이트 적용)
# ==========================================
if not st.session_state['scan_result'].empty:
    st.markdown("---")
    st.subheader("📊 스캔 결과")
    
    df_view = st.session_state['scan_result']
    total_count = len(df_view)
    
    with st.container(border=True):
        st.markdown("#### 🎯 핵심 타점 압축 필터")
        col1, col2 = st.columns([1, 1])
        with col1:
            show_multi_only = st.toggle("🔥 [강력 추천] 2개 이상 조건이 겹친 '진국 종목'만 남기기", value=False)
        with col2:
            if show_multi_only:
                st.success("✅ 필터 ON: 노이즈가 제거된 최상급 타점만 표시 중입니다.")
            else:
                st.caption("👈 스위치를 켜면 승률이 가장 높은 알짜 종목만 골라냅니다.")
        
    if show_multi_only:
        df_view = df_view[df_view['상세 포착 이유'].str.contains("중복 포착", na=False)]
        filtered_count = len(df_view)
        st.warning(f"💡 전체 {total_count}개 중, 강력한 다중 조건이 겹친 **{filtered_count}개** 종목만 엑기스로 뽑아냈습니다.")
    else:
        st.info(f"💡 전체 {total_count}개 종목이 표시 중입니다. (위 스위치를 켜서 종목을 압축해 보세요!)")
    
    st.dataframe(df_view, use_container_width=True)
    
    @st.cache_data
    def convert_df(df):
        from io import BytesIO
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='스캔결과')
        return output.getvalue()
    
    excel_data = convert_df(df_view)
    st.download_button(
        label="📥 엑셀 파일로 다운로드 (현재 보이는 표 기준)",
        data=excel_data,
        file_name=f"웹스캔결과_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary"
    )
