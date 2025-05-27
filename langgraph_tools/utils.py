"""
LangGraph 도구 구현에 필요한 공통 유틸리티 함수.

이 모듈은 도구 구현에 필요한 공통 유틸리티 함수를 제공합니다.
"""

import functools
import json
import logging
import traceback
from typing import Any, Callable, Dict, Optional, TypeVar, cast

from langgraph_tools.schemas import ToolResponse

# 로거 설정
logger = logging.getLogger(__name__)

# 제네릭 타입 변수 정의
T = TypeVar("T")


def format_tool_response(
    status: str = "success", 
    data: Optional[Dict[str, Any]] = None, 
    error_message: Optional[str] = None
) -> Dict[str, Any]:
    """
    일관된 도구 응답 형식을 생성합니다.

    Args:
        status: 응답 상태 (success 또는 error)
        data: 성공 시 반환할 데이터 딕셔너리
        error_message: 오류 발생 시 오류 메시지

    Returns:
        표준화된 응답 딕셔너리
    """
    response = ToolResponse(
        status=status,
        data=data or {},
        error_message=error_message
    )
    
    # LLM이 이해하기 쉽도록 JSON 문자열로 변환
    return json.loads(response.model_dump_json())


def handle_tool_error(func: Callable[..., T]) -> Callable[..., Dict[str, Any]]:
    """
    도구 함수를 래핑하여 오류 처리를 추가하는 데코레이터.

    Args:
        func: 래핑할 도구 함수

    Returns:
        오류 처리가 추가된 래핑된 함수
    """
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Dict[str, Any]:
        try:
            result = func(*args, **kwargs)
            
            # 결과가 이미 딕셔너리인 경우 format_tool_response를 적용하지 않음
            if isinstance(result, dict) and "status" in result:
                return result
            
            # 그 외의 경우 성공 응답으로 래핑
            return format_tool_response(status="success", data={"result": result})
            
        except Exception as e:
            # 오류 상세 정보 로깅
            error_details = f"{type(e).__name__}: {str(e)}"
            error_traceback = traceback.format_exc()
            logger.error(f"도구 실행 중 오류 발생: {error_details}\n{error_traceback}")
            
            # LLM이 이해할 수 있는 오류 메시지 반환
            return format_tool_response(
                status="error",
                error_message=f"도구 실행 중 오류가 발생했습니다: {error_details}"
            )
    
    return cast(Callable[..., Dict[str, Any]], wrapper)


def sanitize_url(url: str) -> str:
    """
    URL을 정규화하여 일관된 형식을 유지합니다.
    
    Args:
        url: 정규화할 URL 문자열
        
    Returns:
        정규화된 URL
    """
    # 모바일 URL을 데스크톱 URL로 변환 (네이버 블로그 특화)
    url = url.replace("m.blog.naver.com", "blog.naver.com")
    
    # URL에서 불필요한 매개변수 제거
    # 여기에 필요한 경우 추가 정규화 로직 구현
    
    return url


def truncate_text(text: str, max_length: int = 6000) -> str:
    """
    텍스트를 최대 길이로 제한합니다.
    
    Args:
        text: 원본 텍스트
        max_length: 최대 길이 (기본값: 6000)
        
    Returns:
        제한된 텍스트
    """
    if len(text) <= max_length:
        return text
        
    return text[:max_length] + "... (content truncated)" 