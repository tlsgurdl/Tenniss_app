import streamlit as st
import pandas as pd
from datetime import datetime
import json
import gspread

# ==========================================
# ⚙️ 1. 기본 환경 세팅 및 구글 시트 연동
# ==========================================
st.set_page_config(page_title="고촌 테니스클럽 야간반 출석부", layout="centered")

# 💡 고정 코트 3면 (6번, 7번, 8번) & 야간 시간대 세팅
COURT_NUMBERS = [6, 7, 8]
TOTAL_COURTS = len(COURT_NUMBERS)

time_slots = [
    "18:00 ~ 19:00", 
    "19:00 ~ 20:00", 
    "20:00 ~ 21:00", 
    "21:00 ~ 22:00"
]

@st.cache_resource
def init_connection():
    try:
        secret_raw = st.secrets["gcp_service_account"]
        # JSON 문자열 또는 딕셔너리 형태 모두 유연하게 처리
        key_info = json.loads(secret_raw) if isinstance(secret_raw, str) else dict(secret_raw)
        
        # gspread 최신 인증 엔진 사용 (더 빠르고 안정적)
        client = gspread.service_account_from_dict(key_info)
        # 이름(Sheet1, 시트1) 상관없이 무조건 첫 번째 탭(0)을 엽니다
        sheet = client.open("고촌테니스_출석부").get_worksheet(0)
        return sheet
    except Exception as e:
        st.error(f"⚠️ 구글 시트 연동 실패: {e}")
        return None

sheet = init_connection()

def fetch_data():
    if sheet:
        try:
            data = sheet.get_all_records()
            return pd.DataFrame(data)
        except Exception:
            pass
    return pd.DataFrame(columns=["이름", "참석시간", "등록일시"])

def add_attendance(name, times):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows_to_insert = [[name, t, now] for t in times]
    if sheet:
        sheet.append_rows(rows_to_insert)

# ==========================================
# 🖥️ 2. 웹사이트 UI: 회원용 3초 출석 체크
# ==========================================
st.title("🎾 고촌 테니스클럽 출석부")
st.markdown("**복잡한 투표는 그만! 참석할 시간만 터치하세요.**")

current_db = fetch_data()

with st.expander("🙋‍♂️ [회원용] 3초 출석 체크하기", expanded=True):
    col1, col2 = st.columns([1, 2])
    with col1:
        user_name = st.text_input("닉네임(이름) 입력", placeholder="예: 김보람")
    
    with col2:
        st.markdown("참석 시간 선택 (복수 선택 가능)")
        selected_times = []
        for time_slot in time_slots:
            if st.checkbox(time_slot):
                selected_times.append(time_slot)
                
    if st.button("🚀 출석 등록 완료", use_container_width=True):
        if not sheet:
            st.error("⚠️ 데이터베이스에 연결되지 않았습니다.")
        elif not user_name.strip():
            st.warning("⚠️ 닉네임을 먼저 입력해 주세요!")
        elif not selected_times:
            st.warning("⚠️ 참석할 시간을 하나 이상 선택해 주세요!")
        else:
            if not current_db.empty and user_name in current_db['이름'].values:
                st.error(f"🚨 '{user_name}'님은 이미 등록되어 있습니다. 변경은 총무에게 문의하세요!")
            else:
                with st.spinner("구글 장부에 안전하게 기록 중입니다..."):
                    add_attendance(user_name, selected_times)
                    st.success(f"🎉 {user_name}님, 등록이 완료되었습니다!")
                    st.rerun()

st.divider()

# ==========================================
# 📊 3. 웹사이트 UI: 테니스 코트 시각화 혼잡도
# ==========================================
st.subheader("🚥 실시간 코트 현황판")
st.info("초록색 타임에 나오시면 쾌적하게 게임을 즐기실 수 있습니다!")

if not current_db.empty and '참석시간' in current_db.columns:
    attendance_counts = current_db['참석시간'].value_counts().to_dict()
else:
    attendance_counts = {}

for time_slot in time_slots:
    people = attendance_counts.get(time_slot, 0)
    density = people / TOTAL_COURTS
    
    if density < 4.5:
        status_text = "쾌적"
        bg_color = "#4CAF50"
        text_color = "white"
    elif density <= 6.5:
        status_text = "적정"
        bg_color = "#FFC107"
        text_color = "black"
    else:
        status_text = "포화"
        bg_color = "#F44336"
        text_color = "white"

    # 코트 HTML 조립 (들여쓰기 제거하여 오류 원천 차단)
    courts_html = ""
    for court_num in COURT_NUMBERS:
        courts_html += f"<div style='width: 80px; height: 50px; background-color: {bg_color}; border: 2px solid white; border-radius: 4px; position: relative; display: flex; align-items: center; justify-content: center; box-shadow: 2px 2px 5px rgba(0,0,0,0.1);'><div style='position: absolute; left: 50%; top: 0; bottom: 0; border-left: 2px dashed rgba(255,255,255,0.7);'></div><span style='color: {text_color}; font-weight: bold; font-size: 13px; z-index: 1;'>{court_num}번</span></div>"

    # 전체 블록 HTML 조립 (들여쓰기 제거)
    final_html = f"<div style='background-color: #f8f9fa; padding: 15px; border-radius: 12px; margin-bottom: 12px; border: 1px solid #e0e0e0; display: flex; align-items: center; justify-content: space-between;'><div style='flex: 1;'><h4 style='margin: 0; color: #333; font-size: 18px;'>{time_slot}</h4><p style='margin: 5px 0 0 0; font-size: 14px; color: #555;'>현재 <strong>{people}명</strong> (코트당 {density:.1f}명) <br><span style='font-weight: bold; color: {bg_color if bg_color != \"#FFC107\" else \"#d4a100\"};'>상태: {status_text}</span></p></div><div style='display: flex; gap: 8px;'>{courts_html}</div></div>"
    
    st.markdown(final_html, unsafe_allow_html=True)

# ==========================================
# 📝 4. 상세 참석자 명단
# ==========================================
with st.expander("📋 시간대별 상세 참석자 명단 보기"):
    if current_db.empty or '참석시간' not in current_db.columns:
        st.write("아직 등록된 회원이 없습니다.")
    else:
        summary_df = current_db.groupby('참석시간')['이름'].apply(lambda x: ', '.join(x.astype(str))).reset_index()
        st.table(summary_df)
