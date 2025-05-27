# config/settings.py

# LLM Configuration
OLLAMA_HOST = "http://localhost:11434"
LLM_MODEL_NAME = "doomgrave/gemma3-tools:latest"  # Upgraded to Gemma3-Tools for better performance
LLM_REQUEST_TIMEOUT = 240 # 초 (더 큰 모델이므로 타임아웃 증가)
LLM_JSON_MODE = True # Ollama가 JSON 출력을 지원한다면 사용 (tool_calls는 별도 필드)
LLM_TEMPERATURE = 0.2 # Gemma3는 더 지능적이므로 온도를 낮춰 정확도 향상
LLM_NUM_CTX = 16384 # Gemma3는 더 긴 컨텍스트 지원 (8192 -> 16384)
LLM_MAX_TOKENS = 4096 # 최대 응답 토큰 수
LLM_TOP_P = 0.9 # Top-p 샘플링으로 더 일관된 응답
LLM_REPEAT_PENALTY = 1.1 # 반복 방지

# Web Search Configuration
SEARCH_MAX_RESULTS = 5 # 초기 검색 시 가져올 결과 수 (LLM이 판단하여 더 검색 가능)

# Browser Configuration
BROWSER_TIMEOUT = 60000
BROWSER_TYPE = "selenium"  # 'selenium' 또는 'playwright'

# Agent Configuration
AGENT_MAX_TURNS = 20 # Gemma3는 더 지능적이므로 더 많은 턴 허용 (15 -> 20)
MINIMUM_BLOGS_TO_COLLECT = 5  # 고성능 모델로 더 많은 블로그 수집 (3 -> 5)
AGENT_PARALLEL_PROCESSING = True  # 병렬 처리 활성화
AGENT_SMART_RETRY = True  # 지능적 재시도 기능
AGENT_CONTEXT_MEMORY = True  # 컨텍스트 메모리 활용

# Data Extraction Fields
DATA_FIELDS_TO_EXTRACT = [
    "blog_id",
    "blog_name",
    "blog_url",
    "recent_post_date",
    "first_post_date",
    "total_posts",
    "blog_creation_date",
    "average_visitors",
    "llm_summary" # LLM이 생성한 블로그 요약 (선택적 추가)
]

# Output Configuration
OUTPUT_DIR = "outputs"
OUTPUT_FORMAT = "csv"  # "csv" 또는 "excel"
FILE_TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"

# Logging Configuration
LOG_LEVEL = "INFO" # DEBUG로 하면 매우 상세한 로그 출력
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# Tool Definitions 불러오기 함수
def get_tools_for_ollama():
    """LLM을 위한 도구 정의를 반환합니다."""
    from tools.tool_definitions import TOOLS_SPEC
    return TOOLS_SPEC