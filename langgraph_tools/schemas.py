"""
도구 입력 및 출력 구조화를 위한 Pydantic 모델 정의.

이 모듈은 LangChain @tool 데코레이터와 함께 사용할 Pydantic 모델을 정의합니다.
각 모델은 기존 TOOLS_SPEC에 정의된 스키마를 기반으로 합니다.
"""

from typing import Dict, List, Optional, Any, Union
from pydantic import BaseModel, Field


class SearchWebInput(BaseModel):
    """블로그 검색을 위한 입력 스키마."""
    
    keyword: str = Field(
        ..., 
        description="블로그 검색을 위한 키워드"
    )


class WebpageContentInput(BaseModel):
    """웹페이지 접근 및 상호작용을 위한 입력 스키마."""
    
    url: str = Field(
        ...,
        description="분석하거나 상호작용할 웹사이트 URL"
    )
    fields_to_extract: List[str] = Field(
        ...,
        description="추출할 정보 필드 목록 (예: ['blog_name', 'recent_post_date', 'main_content_summary', 'average_visitors_hint'])"
    )
    action_details: Optional[Dict[str, Any]] = Field(
        None,
        description="페이지와 상호작용하기 위한 세부 정보 (선택 사항)"
    )


class ActionDetails(BaseModel):
    """웹페이지와 상호작용하기 위한 세부 정보."""
    
    action_type: str = Field(
        ...,
        description="수행할 액션 타입",
        enum=["click", "type", "extract_specific_text"]
    )
    selector: str = Field(
        ...,
        description="CSS 선택자"
    )
    input_text: Optional[str] = Field(
        None,
        description="'type' 액션 시 입력할 텍스트"
    )


class ExtractBlogFieldsInput(BaseModel):
    """블로그 데이터 추출을 위한 입력 스키마."""
    
    text_content: str = Field(
        ...,
        description="분석할 웹페이지의 텍스트 내용"
    )
    original_url: str = Field(
        ...,
        description="분석 중인 웹페이지의 원본 URL"
    )


class BlogData(BaseModel):
    """추출된 블로그 데이터 구조."""
    
    blog_id: str = Field(
        ...,
        description="블로그의 고유 ID"
    )
    blog_name: str = Field(
        ...,
        description="블로그 이름"
    )
    blog_url: str = Field(
        ...,
        description="블로그 URL"
    )
    recent_post_date: str = Field(
        ...,
        description="가장 최근 게시글 날짜"
    )
    llm_summary: str = Field(
        ...,
        description="블로그 콘텐츠에 대한 요약"
    )


class FinalizeBlogDataInput(BaseModel):
    """데이터 수집 완료를 위한 입력 스키마."""
    
    collected_blogs_summary: List[Dict[str, Any]] = Field(
        ...,
        description="지금까지 수집된 블로그들의 요약 정보 목록"
    )
    all_tasks_completed: bool = Field(
        ...,
        description="모든 요청된 블로그 정보 수집 작업이 완료되었는지 여부"
    )
    quality_score: Optional[float] = Field(
        None,
        description="수집된 데이터의 전체 품질 점수 (1-10)"
    )
    recommendations: Optional[List[str]] = Field(
        None,
        description="추가 검색이나 개선을 위한 지능적 제안사항"
    )


class ToolResponse(BaseModel):
    """도구 응답을 위한 표준 형식."""
    
    status: str = Field(
        ...,
        description="응답 상태 (success 또는 error)"
    )
    data: Optional[Dict[str, Any]] = Field(
        None,
        description="성공 시 반환되는 데이터"
    )
    error_message: Optional[str] = Field(
        None,
        description="오류 발생 시 오류 메시지"
    ) 