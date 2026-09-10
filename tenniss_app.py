import streamlit as st
import pandas as pd
from datetime import datetime
import json
import gspread
from google.oauth2.service_account import Credentials

# ==========================================
# ⚙️ 1. 기본 환경 세팅 및 구글 시트 연동
# ==========================================
st.set_page_config(page_title="고촌 테니스클럽 출석부", layout="centered", page_icon="🎾")

# 화이트 모드에서도 입력창이 뚜렷하게 보이도록 커스텀 CSS 주입
st.markdown("""
<style>
    div[data-baseweb="input"] > div {
        border: 2px solid #ddd !important;
        background-color: #fefefe !important;
        border-radius: 8px !important;
        box-shadow: inset 0 1px 3px rgba(0,0,0,0.05);
    }
    div[data-testid="stCheckbox"] {
        padding: 5px 10px;
        background-color: #f8f9fa;
        border: 1px solid #eee;
        border-radius: 8px;
        margin-bottom: 5px;
    }
</style>
""", unsafe_allow_html=True)

time_slots_mapping = {
    "18:00": "18:00 ~ 19:00",
    "19:00": "19:00 ~ 20:00",
    "20:00": "20:00 ~ 21:00",
    "21:00": "21:00 ~ 22:00"
}

@st.cache_resource(ttl=600)
def init_connection():
    try:
        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        secret_raw = st.secrets["gcp_service_account"]
        key_info = json.loads(secret_raw) if isinstance(secret_raw, str) else dict(secret_raw)
        credentials = Credentials.from_service_account_info(key_info, scopes=scope)
        client = gspread.authorize(credentials)
        
        doc = client.open("고촌테니스_출석부")
        sheet_db = doc.get_worksheet(0)
        try:
            sheet_schedule = doc.worksheet("스케줄")
        except:
            sheet_schedule = None
        return sheet_db, sheet_schedule
    except Exception as e:
        st.error(f"⚠️ 연동 실패: {e}")
        return None, None

sheet, sheet_schedule = init_connection()

# ==========================================
# 📅 2. 스케줄 데이터 파싱
# ==========================================
today_str = datetime.today().strftime('%Y-%m-%d')
today_schedule = {}
schedule_df = pd.DataFrame()

if sheet_schedule:
    try:
        data = sheet_schedule.get_all_records()
        schedule_df = pd.DataFrame(data)
        today_row = schedule_df[schedule_df['날짜'].astype(str) == today_str]
        
        if not today_row.empty:
            row_data = today_row.iloc[0]
            for col_time, ui_time in time_slots_mapping.items():
                val = str(row_data.get(col_time, "")).strip()
                if val and "휴" not in val:
                    today_schedule[ui_time] = [int(x.strip()) for x in val.split(",") if x.strip().isdigit()]
                else:
                    today_schedule[ui_time] = []
    except:
        pass

available_time_slots = [t for t, courts in today_schedule.items() if len(courts) > 0]

# ==========================================
# 📝 3. 출석 데이터 처리
# ==========================================
def fetch_data():
    if sheet:
        try:
            data = sheet.get_all_records()
            df = pd.DataFrame(data)
            if not df.empty and '등록일시' in df.columns:
                df = df[df['등록일시'].str.startswith(today_str)]
            return df
        except:
            pass
    return pd.DataFrame(columns=["이름", "참석시간", "등록일시"])

def add_attendance(name, times):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows_to_insert = [[name, t, now] for t in times]
    if sheet:
        sheet.append_rows(rows_to_insert)

# ==========================================
# 🖥️ 4. UI 렌더링
# ==========================================
st.title("🎾 고촌 테니스클럽")

tab1, tab2 = st.tabs(["🎾 오늘의 출석부", "📅 월간 예약 현황"])

with tab1:
    st.markdown(f"**📅 오늘 날짜: {today_str}**")
    current_db = fetch_data()

    with st.expander("🙋‍♂️ [회원용] 3초 출석 체크하기", expanded=True):
        if not available_time_slots:
            st.error("오늘은 예약된 코트 일정이 없습니다! 푹 쉬세요 🍺")
        else:
            col1, col2 = st.columns([1, 2])
            with col1:
                user_name = st.text_input("닉네임(이름) 입력", placeholder="예: 김보람")
            
            with col2:
                st.markdown("**참석 시간 선택**")
                selected_times = []
                for time_slot in available_time_slots:
                    if st.checkbox(time_slot):
                        selected_times.append(time_slot)
                        
            if st.button("🚀 출석 등록 완료", use_container_width=True):
                if not sheet:
                    st.error("⚠️ 데이터베이스 연결 오류")
                elif not user_name.strip():
                    st.warning("⚠️ 닉네임을 먼저 입력해 주세요!")
                elif not selected_times:
                    st.warning("⚠️ 참석할 시간을 하나 이상 선택해 주세요!")
                else:
                    if not current_db.empty and user_name in current_db['이름'].values:
                        st.error(f"🚨 '{user_name}'님은 이미 오늘 출석을 등록하셨습니다!")
                    else:
                        with st.spinner("장부에 기록 중입니다..."):
                            add_attendance(user_name, selected_times)
                            st.success(f"🎉 {user_name}님, 등록 완료!")
                            st.rerun()

    st.divider()

    st.subheader("🚥 실시간 코트 현황판")
    if not available_time_slots:
        st.warning("⚠️ 오늘 예약된 코트가 없습니다.")
    else:
        attendance_counts = current_db['참석시간'].value_counts().to_dict() if not current_db.empty else {}

        for time_slot, active_courts in today_schedule.items():
            if not active_courts: continue
                
            num_courts = len(active_courts)
            people = attendance_counts.get(time_slot, 0)
            density = people / num_courts if num_courts > 0 else 0
            
            if density < 4.5:
                status_text, bg_color = "쾌적", "#4CAF50"
            elif density <= 6.5:
                status_text, bg_color = "적정", "#FFC107"
            else:
                status_text, bg_color = "포화", "#F44336"

            status_font_color = bg_color if bg_color != "#FFC107" else "#d4a100"

            # 💡 코트 디자인 수정: 숫자를 코트 안에서 빼고 아래로 배치
            courts_html = ""
            for court_num in active_courts:
                court_wrapper = (
                    f"<div style='display: flex; flex-direction: column; align-items: center; gap: 6px;'>"
                    f"<div style='width: 60px; height: 90px; background-color: {bg_color}; border: 2px solid white; border-radius: 4px; position: relative; box-shadow: 2px 2px 5px rgba(0,0,0,0.15); flex-shrink: 0;'>"
                    f"<div style='position: absolute; top: 0; bottom: 0; left: 15%; border-left: 1px solid rgba(255,255,255,0.5);'></div>"
                    f"<div style='position: absolute; top: 0; bottom: 0; right: 15%; border-right: 1px solid rgba(255,255,255,0.5);'></div>"
                    f"<div style='position: absolute; top: 50%; left: 0; right: 0; border-top: 2px dashed rgba(255,255,255,0.9); transform: translateY(-50%);'></div>"
                    f"<div style='position: absolute; top: 22%; left: 15%; right: 15%; border-top: 1px solid rgba(255,255,255,0.6);'></div>"
                    f"<div style='position: absolute; bottom: 22%; left: 15%; right: 15%; border-top: 1px solid rgba(255,255,255,0.6);'></div>"
                    f"<div style='position: absolute; top: 22%; bottom: 22%; left: 50%; border-left: 1px solid rgba(255,255,255,0.6); transform: translateX(-50%);'></div>"
                    f"</div>"
                    f"<span style='font-size: 13px; font-weight: 800; color: #444; background: #eee; padding: 2px 8px; border-radius: 12px;'>{court_num}번</span>"
                    f"</div>"
                )
                courts_html += court_wrapper

            final_html = (
                f"<div style='background-color: #f8f9fa; padding: 15px; border-radius: 12px; margin-bottom: 12px; border: 1px solid #e0e0e0; display: flex; align-items: center; justify-content: space-between; overflow-x: auto;'>"
                f"<div style='flex: 1; min-width: 120px;'>"
                f"<h4 style='margin: 0; color: #333; font-size: 18px;'>{time_slot}</h4>"
                f"<p style='margin: 5px 0 0 0; font-size: 14px; color: #555;'>"
                f"현재 <strong>{people}명</strong> (코트당 {density:.1f}명) <br>"
                f"<span style='font-weight: bold; color: {status_font_color};'>상태: {status_text}</span>"
                f"</p></div>"
                f"<div style='display: flex; gap: 12px;'>{courts_html}</div>"
                f"</div>"
            )
            st.markdown(final_html, unsafe_allow_html=True)

    with st.expander("📋 시간대별 상세 참석자 명단 보기"):
        if current_db.empty or '참석시간' not in current_db.columns:
            st.write("아직 등록된 회원이 없습니다.")
        else:
            summary_df = current_db.groupby('참석시간')['이름'].apply(lambda x: ', '.join(x.astype(str))).reset_index()
            st.table(summary_df)

# ==========================================
# 🗓️ 5. 두 번째 탭: 월간 달력 시각화 (디자인 개선)
# ==========================================
with tab2:
    st.subheader("📅 이달의 코트 예약 현황")
    if not schedule_df.empty:
        # 달력을 직관적인 HTML 표로 변환하는 로직
        calendar_html = "<table style='width: 100%; border-collapse: collapse; text-align: center; font-size: 14px;'>"
        calendar_html += "<tr style='background-color: #4CAF50; color: white;'>"
        calendar_html += "<th style='padding: 10px; border: 1px solid #ddd;'>날짜</th>"
        for t in time_slots_mapping.keys():
            calendar_html += f"<th style='padding: 10px; border: 1px solid #ddd;'>{t}</th>"
        calendar_html += "</tr>"

        for _, row in schedule_df.iterrows():
            calendar_html += "<tr>"
            calendar_html += f"<td style='padding: 10px; border: 1px solid #ddd; font-weight: bold;'>{row.get('날짜', '')}</td>"
            
            for t in time_slots_mapping.keys():
                val = str(row.get(t, "")).strip()
                if not val or "휴" in val:
                    cell_content = f"<span style='color: #999;'>{val if val else '-'}</span>"
                else:
                    # 6,7,8 숫자를 둥근 뱃지 디자인으로 변환
                    courts = [x.strip() for x in val.split(",") if x.strip().isdigit()]
                    badges = "".join([f"<span style='display: inline-block; background-color: #e3f2fd; color: #1565c0; padding: 3px 6px; border-radius: 4px; margin: 2px; font-weight: bold; font-size: 12px;'>{c}</span>" for c in courts])
                    cell_content = badges
                
                calendar_html += f"<td style='padding: 10px; border: 1px solid #ddd;'>{cell_content}</td>"
            calendar_html += "</tr>"
        calendar_html += "</table>"
        
        st.markdown(calendar_html, unsafe_allow_html=True)
    else:
        st.info("구글 시트 '스케줄' 탭에 데이터를 입력하시면 여기에 달력이 표시됩니다.")
