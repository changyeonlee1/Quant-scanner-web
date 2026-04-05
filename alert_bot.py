import os
import requests
import FinanceDataReader as fdr
from supabase import create_client, Client
from datetime import datetime

# 1. 환경 변수 로드 (GitHub Secrets)
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")
TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

supabase: Client = create_client(URL, KEY)

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    params = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    requests.get(url, params=params)

def run_monitor():
    # 2. DB에서 관심종목 불러오기
    # 모든 유저의 관심종목을 통합해서 감시하거나 특정 유저것만 감시하도록 쿼리 조절 가능
    response = supabase.table("vip_tickers").select("ticker_list").execute()
    if not response.data: return
    
    all_tickers = []
    for row in response.data:
        all_tickers.extend([t.strip() for t in row['ticker_list'].split('\n') if t.strip()])
    
    unique_tickers = list(set(all_tickers)) # 중복 제거

    # 3. 실시간 가격 체크 및 알림 로직
    for code in unique_tickers:
        try:
            # 최근 2일 데이터 가져오기 (전일 종가 대비 현재가 비교)
            df = fdr.DataReader(code)
            if df.empty: continue
            
            prev_close = df['Close'].iloc[-2]
            curr_price = df['Close'].iloc[-1]
            change_rate = ((curr_price - prev_close) / prev_close) * 100

            # 🔥 급등 기준 설정 (예: +5% 이상)
            if change_rate >= 5.0:
                msg = f"🚀 [급등 포착] \n종목코드: {code}\n현재가: {curr_price:,.0f}원\n상승률: +{change_rate:.2f}%"
                send_telegram(msg)
        except:
            continue

if __name__ == "__main__":
    # 장 중에만 돌도록 시간 설정 가능 (9:00~15:30)
    now = datetime.now()
    if 9 <= now.hour <= 15:
        run_monitor()