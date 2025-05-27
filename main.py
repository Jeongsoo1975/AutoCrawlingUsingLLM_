# main.py
import streamlit as st
# from pipelines.blog_data_pipeline import BlogDataPipeline # 이전 파이프라인
from pipelines.agent_pipeline import AgentPipeline  # 새로 만든 에이전트 파이프라인
from utils.logger import setup_logger
import asyncio
import logging
import os
from config import settings

setup_logger()  # 로거 설정은 한번만
logger = logging.getLogger(__name__)

# Selenium을 사용하므로 Playwright 관련 WindowsSelectorEventLoopPolicy 코드 제거

if not os.path.exists(settings.OUTPUT_DIR):
    os.makedirs(settings.OUTPUT_DIR)


# Streamlit UI 상태 업데이트를 위한 콜백 함수
def streamlit_status_update(message):
    # st.info(message) # 모든 로그를 info로 하면 너무 많을 수 있음
    # st.session_state를 사용하거나, 특정 위젯에 표시
    # 여기서는 간단히 st.write 또는 st.status 내부에서 사용하도록 파이프라인에 전달
    # 실제 업데이트는 파이프라인을 호출하는 Streamlit 코드 블록 내에서 처리
    # 이 콜백은 로깅 목적으로 더 적합할 수 있음
    # logger.info(f"[UI_STATUS_CALLBACK] {message}")
    if "status_placeholder" in st.session_state:
        st.session_state.status_placeholder.info(message)


async def run_agent_pipeline_streamlit(keywords_list, status_placeholder_for_ui):
    """Streamlit UI에서 에이전트 파이프라인을 실행합니다."""
    # st.session_state에 상태 표시용 placeholder 저장
    st.session_state.status_placeholder = status_placeholder_for_ui

    pipeline = AgentPipeline(streamlit_status_callback=status_placeholder_for_ui.info)  # 콜백 전달
    output_filepath = await pipeline.run_agent_for_keywords(keywords_list)
    return output_filepath


def main_ui():
    st.set_page_config(page_title="LLM 에이전트 블로그 스크래퍼", layout="wide")
    st.title("🤖 LLM 에이전트 기반 블로그 데이터 수집기")

    st.sidebar.header("설정")
    # settings.py의 값을 UI에서 변경 가능하게 하려면 여기에 위젯 추가
    settings.AGENT_MAX_TURNS = st.sidebar.slider("에이전트 최대 작업 턴 수", 5, 20, getattr(settings, "AGENT_MAX_TURNS", 10))
    # 기타 LLM 온도 등의 설정도 추가 가능

    st.header("🔍 키워드 입력")
    keywords_input_area = st.text_area(
        "수집할 블로그의 키워드를 입력하세요 (AI 에이전트가 분석합니다):",
        height=100,
        placeholder="예시:\n최신 인공지능 모델 동향 분석\n친환경 에너지 기술 블로그 리뷰\n서울 맛집 추천 블로그 (2025년 기준)"
    )
    st.caption("여러 키워드는 각 줄로 구분하거나, 쉼표(,)로 구분하여 한 줄에 입력할 수 있습니다.")

    # 상태 메시지 표시 영역
    status_placeholder = st.empty()  # 동적 메시지 업데이트용

    if st.button("🚀 AI 에이전트 스크래핑 시작", type="primary", use_container_width=True):
        if not keywords_input_area.strip():
            status_placeholder.warning("키워드를 하나 이상 입력해주세요.")
        else:
            keywords_raw_lines = keywords_input_area.strip().split('\n')
            keywords_list = []
            for line in keywords_raw_lines:
                keywords_from_line = [kw.strip() for kw in line.split(',') if kw.strip()]
                keywords_list.extend(keywords_from_line)

            if not keywords_list:
                status_placeholder.warning("유효한 키워드가 없습니다. 입력값을 확인해주세요.")
            else:
                status_placeholder.info(f"다음 키워드로 AI 에이전트 스크래핑을 시작합니다: {', '.join(keywords_list)}")

                with st.spinner("AI 에이전트가 작업 중입니다... 🧠⚙️🌐 이 작업은 시간이 오래 걸릴 수 있습니다."):
                    try:
                        # Streamlit UI의 상태 표시 위젯을 run_agent_pipeline_streamlit에 전달
                        output_filepath = asyncio.run(run_agent_pipeline_streamlit(keywords_list, status_placeholder))

                        if output_filepath and os.path.exists(output_filepath):
                            status_placeholder.success(f"✅ 에이전트 작업 완료!")
                            st.markdown(f"**데이터 저장 위치:** `{output_filepath}`")
                            with open(output_filepath, "rb") as fp:
                                st.download_button(
                                    label="📥 Excel 파일 다운로드",
                                    data=fp,
                                    file_name=os.path.basename(output_filepath),
                                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                    use_container_width=True
                                )
                        elif output_filepath:
                            status_placeholder.error(f"에이전트 작업은 보고되었으나 다음 경로에서 출력 파일을 찾을 수 없습니다: {output_filepath}")
                        else:
                            status_placeholder.warning("에이전트 작업은 완료되었으나, 생성된 파일이 없거나 추출된 데이터가 없습니다.")

                    except Exception as e:
                        status_placeholder.error(f"에이전트 작업 중 오류가 발생했습니다: {e}")
                        logger.critical(f"Streamlit UI에서 에이전트 파이프라인 실행 중 오류: {e}", exc_info=True)

    # ... (나머지 UI 설명 부분은 이전과 유사하게 추가 가능) ...


if __name__ == "__main__":
    main_ui()