import streamlit as st
import pandas as pd
from datetime import datetime

# ==========================================
# ⚙️ 1. 기본 환경 세팅 및 데이터베이스(메모리) 초기화
# ==========================================
st.set_page_config(page_title="고촌 테니스클럽 출석부", layout="centered")

# 시간대별 기본 코트 면수 세팅
default_schedule = {
    "14:00 ~ 15:00": {"코트수": 1},
    "15:00 ~ 16:00": {"코트수": 1},
    "16:00 ~ 17:00": {"코트수": 2},
    "17:00 ~ 18:00": {"코트수": 2}
}

# 임시 데이터베이스 (앱이 켜져 있는 동안만 유지)
if 'attendance_db' not in st.session_state:
    st.session_state['attendance_db'] = pd.DataFrame(columns=["이름", "참석시간", "등록일시"])

def add_attendance(name, times):
    """회원 출석 데이터를 DB에 밀어넣는 함수"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new_data = [{"이름": name, "참석시간": t, "등록일시": now} for t in times]
    df_new = pd.DataFrame(new_data)
    st.session_state['attendance_db'] = pd.concat([st.session_state['attendance_db'], df_new], ignore_index=True)

# ==========================================
# 🖥️ 2. 웹사이트 UI: 회원용 3초 출석 체크
# ==========================================
st.title("🎾 고촌 테니스클럽")
st.markdown("**복잡한 투표는 그만! 참석할 시간만 터치하세요.**")

with st.expander("🙋‍♂️ [회원용] 3초 출석 체크하기", expanded=True):
    col1, col2 = st.columns([1, 2])
    with col1:
        user_name = st.text_input("닉네임(이름) 입력", placeholder="예: 김보람")
    
    with col2:
        st.markdown("참석 시간 선택 (복수 선택 가능)")
        selected_times = []
        for time_slot in default_schedule.keys():
            if st.checkbox(time_slot):
                selected_times.append(time_slot)
                
    if st.button("🚀 출석 등록 완료", use_container_width=True):
        if not user_name.strip():
            st.warning("⚠️ 닉네임을 먼저 입력해 주세요!")
        elif not selected_times:
            st.warning("⚠️ 참석할 시간을 하나 이상 선택해 주세요!")
        else:
            # 중복 등록 방지 로직
            existing = st.session_state['attendance_db']
            if user_name in existing['이름'].values:
                st.error("이미 등록된 닉네임입니다. 수정을 원하시면 총무에게 문의하세요!")
            else:
                add_attendance(user_name, selected_times)
                st.success(f"🎉 {user_name}님, 등록이 완료되었습니다! 아래 혼잡도를 확인하세요.")

st.divider()

# ==========================================
# 📊 3. 웹사이트 UI: 실시간 혼잡도 히트맵
# ==========================================
st.subheader("🚥 실시간 코트 혼잡도 (히트맵)")
st.info("초록색 타임에 나오시면 쉬지 않고 게임을 즐기실 수 있습니다!")

current_db = st.session_state['attendance_db']

# 시간대별 참석 인원 집계
attendance_counts = current_db['참석시간'].value_counts().to_dict()

# 히트맵 그리기
for time_slot, info in default_schedule.items():
    courts = info["코트수"]
    people = attendance_counts.get(time_slot, 0)
    
    # 1면당 적정 인원 계산 (신호등 로직)
    density = people / courts if courts > 0 else 0
    
    if density < 4.5:
        color = "🟢 쾌적"
        bg_color = "#e6ffe6"
    elif density <= 6.5:
        color = "🟡 적정 (대기 조금)"
        bg_color = "#ffffe6"
    else:
        color = "🔴 포화 (대기 지옥)"
        bg_color = "#ffe6e6"
        
    st.markdown(
        f"""
        <div style="background-color: {bg_color}; padding: 15px; border-radius: 10px; margin-bottom: 10px; border: 1px solid #ddd;">
            <h4 style="margin: 0; color: #333;">{time_slot} | 코트 {courts}면</h4>
            <p style="margin: 5px 0 0 0; font-size: 16px;">
                현재 참석: <strong>{people}명</strong> (코트당 평균 {density:.1f}명) ➔ <strong>{color}</strong>
            </p>
        </div>
        """,
        unsafe_allow_html=True
    )

# ==========================================
# 📝 4. 상세 참석자 명단 (접었다 펴기)
# ==========================================
with st.expander("📋 시간대별 상세 참석자 명단 보기"):
    if current_db.empty:
        st.write("아직 등록된 회원이 없습니다.")
    else:
        # 시간대별로 사람 이름 묶어서 보여주기
        summary_df = current_db.groupby('참석시간')['이름'].apply(lambda x: ', '.join(x)).reset_index()
        st.table(summary_df)
