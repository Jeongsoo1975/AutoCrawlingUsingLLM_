"""
데이터 수집 완료 도구 구현.

이 모듈은 블로그 데이터 수집을 완료하고 최종 결과를 저장하는 도구를 LangChain @tool 데코레이터를 사용해 구현합니다.
이 도구는 데이터 수집 파이프라인의 마지막 단계에서 사용되며, 모든 블로그 데이터의 유효성을 검증하고 지정된 형식으로 저장합니다.
"""

import logging
import os
import json
import traceback
import re
from datetime import datetime
from typing import Dict, List, Any, Optional, Union, Type, TypeVar, cast, Tuple
import urllib.parse

from langchain_core.tools import tool

from config import settings
from langgraph_tools.schemas import FinalizeBlogDataInput
from langgraph_tools.utils import format_tool_response

# 타입 정의
BlogData = Dict[str, Any]
ToolResponse = Dict[str, Any]
DataWriterType = TypeVar('DataWriterType')
ValidationResult = Tuple[List[str], List[str]]  # (errors, warnings)

# 로거 설정
logger = logging.getLogger(__name__)

# 싱글톤 패턴을 위한 글로벌 변수
_data_writer: Optional[Any] = None


def get_data_writer(custom_writer: Optional[Any] = None) -> Any:
    """
    DataWriter의 싱글톤 인스턴스를 반환합니다.
    
    재사용 가능한 데이터 저장 인스턴스를 관리하는 팩토리 함수입니다.
    의존성 주입을 통해 테스트 가능성을 높이고, 싱글톤 패턴으로 리소스 사용을 최적화합니다.
    
    Args:
        custom_writer: 선택적으로 주입할 DataWriter 인스턴스. 제공되면 이 인스턴스를 반환합니다.
                      None인 경우 기존 싱글톤 인스턴스를 반환하거나 새로 생성합니다.
    
    Returns:
        Any: DataWriter 인스턴스. 데이터를 저장하는 메서드를 제공합니다.
        
    Raises:
        ImportError: DataWriter 모듈을 임포트할 수 없는 경우 발생합니다.
        RuntimeError: DataWriter 인스턴스 생성 중 예상치 못한 오류가 발생한 경우 발생합니다.
    """
    global _data_writer
    
    logger.debug("get_data_writer 호출됨, custom_writer 제공 여부: %s", custom_writer is not None)
    
    # 사용자 지정 writer가 제공된 경우 해당 인스턴스 사용
    if custom_writer is not None:
        logger.debug("사용자 정의 DataWriter 인스턴스 사용")
        return custom_writer
    
    # 기존 싱글톤 인스턴스가 없는 경우 생성
    if _data_writer is None:
        try:
            # 런타임에 임포트하여 의존성 문제 방지
            logger.debug("DataWriter 인스턴스 생성 시도")
            from utils.excel_writer import DataWriter
            _data_writer = DataWriter()
            logger.info("DataWriter 인스턴스 생성 성공")
        except ImportError as ie:
            logger.error("DataWriter 모듈 임포트 실패: %s", str(ie))
            raise ImportError(f"DataWriter 모듈을 임포트할 수 없습니다: {str(ie)}") from ie
        except Exception as e:
            logger.error("DataWriter 인스턴스 생성 중 오류 발생: %s", str(e))
            raise RuntimeError(f"DataWriter 인스턴스 생성 중 오류 발생: {str(e)}") from e
    
    return _data_writer


def _validate_url(url: str) -> bool:
    """
    URL의 기본적인 형식 유효성을 검증합니다.
    
    Args:
        url (str): 검증할 URL 문자열
        
    Returns:
        bool: URL이 유효한 경우 True, 그렇지 않으면 False 반환
    """
    if not url or not isinstance(url, str):
        return False
    
    if url == "Not Found":
        return False
    
    # 최소한의 URL 형식 검증 (scheme + netloc)
    try:
        result = urllib.parse.urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False


def _validate_date(date_str: str) -> bool:
    """
    날짜 문자열의 유효성을 검증합니다.
    
    Args:
        date_str (str): 검증할 날짜 문자열
        
    Returns:
        bool: 날짜가 유효한 경우 True, 그렇지 않으면 False 반환
    """
    if not date_str or not isinstance(date_str, str):
        return False
    
    if date_str == "Not Found":
        return False
    
    # 다양한 날짜 형식 지원 (YYYY-MM-DD, YYYY/MM/DD, DD-MM-YYYY, DD/MM/YYYY)
    date_patterns = [
        r'^\d{4}[-/\.]\d{1,2}[-/\.]\d{1,2}$',  # YYYY-MM-DD, YYYY/MM/DD
        r'^\d{1,2}[-/\.]\d{1,2}[-/\.]\d{4}$',  # DD-MM-YYYY, DD/MM/YYYY
        r'^\d{4}년\s*\d{1,2}월\s*\d{1,2}일$',   # YYYY년 MM월 DD일
        r'^\d{1,2}월\s*\d{1,2}일,\s*\d{4}$'    # MM월 DD일, YYYY
    ]
    
    return any(re.match(pattern, date_str) for pattern in date_patterns)


def _validate_number(value: str) -> bool:
    """
    숫자 또는 숫자 형식의 문자열의 유효성을 검증합니다.
    
    Args:
        value (str): 검증할 값
        
    Returns:
        bool: 값이 숫자 또는 숫자 형식의 문자열인 경우 True, 그렇지 않으면 False 반환
    """
    if not value or not isinstance(value, str):
        return False
    
    if value == "Not Found":
        return False
    
    # 숫자만 있는 경우
    if re.match(r'^\d+$', value):
        return True
    
    # "약 100개", "100개 이상", "100+" 등의 형식 지원
    if re.search(r'\d+', value):
        return True
    
    return False


def _validate_blog_data(blog_data_list: List[BlogData]) -> ValidationResult:
    """
    블로그 데이터 목록의 유효성을 검증합니다.
    
    이 함수는 수집된 블로그 데이터가 필수 필드를 포함하고 있는지,
    필드 값이 올바른 형식인지, 그리고 최소 수량 요구사항을 충족하는지 확인합니다.
    
    Args:
        blog_data_list (List[BlogData]): 검증할 블로그 데이터 목록.
            각 항목은 블로그 정보를 담고 있는 딕셔너리여야 합니다.
        
    Returns:
        ValidationResult: (오류 메시지 목록, 경고 메시지 목록)의 튜플.
            오류는 데이터를 저장하기 전에 반드시 해결해야 하는 중요한 문제입니다.
            경고는 데이터 품질에 영향을 주지만 저장은 가능한 경미한 문제입니다.
        
    Note:
        필수 필드는 "blog_id", "blog_name", "blog_url"입니다.
        URL은 유효한 형식이어야 합니다.
        날짜 필드는 날짜 형식에 맞아야 합니다.
        total_posts와 같은 수치 필드는 숫자 또는 숫자가 포함된 형식이어야 합니다.
        최소 블로그 수는 settings.MINIMUM_BLOGS_TO_COLLECT에 정의되어 있습니다.
    """
    errors: List[str] = []
    warnings: List[str] = []
    
    logger.debug("블로그 데이터 검증 시작: %d개 항목", len(blog_data_list) if blog_data_list else 0)
    
    if not blog_data_list:
        logger.warning("빈 블로그 데이터 목록이 제공됨")
        errors.append("블로그 데이터가 비어 있습니다.")
        return errors, warnings
    
    # 필수 필드 목록
    required_fields = ["blog_id", "blog_name", "blog_url"]
    
    # 날짜 형식 검증이 필요한 필드 목록
    date_fields = ["recent_post_date", "first_post_date", "blog_creation_date"]
    
    # 숫자 형식 검증이 필요한 필드 목록
    number_fields = ["total_posts"]
    
    # 각 블로그 항목 검증
    for i, blog in enumerate(blog_data_list):
        blog_index = i + 1
        
        # 1. 필수 필드 검증
        for field in required_fields:
            if field not in blog:
                logger.warning("블로그 #%d에 필수 필드 '%s'가 없음", blog_index, field)
                errors.append(f"블로그 #{blog_index}에 필수 필드 '{field}'가 없습니다.")
            elif not blog[field] or blog[field] == "Not Found":
                logger.warning("블로그 #%d의 필수 필드 '%s'가 비어 있거나 유효하지 않음: '%s'", 
                              blog_index, field, blog.get(field, ""))
                errors.append(f"블로그 #{blog_index}의 필수 필드 '{field}'가 비어 있거나 유효하지 않습니다.")
        
        # 필수 필드가 모두 있는 경우에만 추가 검증 진행
        if all(field in blog and blog[field] and blog[field] != "Not Found" for field in required_fields):
            # 2. URL 형식 검증
            if not _validate_url(blog["blog_url"]):
                logger.warning("블로그 #%d의 URL이 유효하지 않음: '%s'", blog_index, blog.get("blog_url", ""))
                errors.append(f"블로그 #{blog_index}의 URL '{blog.get('blog_url', '')}'이 유효하지 않습니다. 'http://' 또는 'https://'로 시작하는 올바른 URL 형식이어야 합니다.")
            
            # 3. 날짜 필드 검증
            for field in date_fields:
                if field in blog and blog[field] and blog[field] != "Not Found":
                    if not _validate_date(blog[field]):
                        logger.warning("블로그 #%d의 날짜 필드 '%s'가 유효하지 않음: '%s'", 
                                     blog_index, field, blog.get(field, ""))
                        warnings.append(f"블로그 #{blog_index}의 '{field}' 값 '{blog.get(field, '')}'이 표준 날짜 형식(YYYY-MM-DD)이 아닙니다.")
            
            # 4. 숫자 필드 검증
            for field in number_fields:
                if field in blog and blog[field] and blog[field] != "Not Found":
                    if not _validate_number(blog[field]):
                        logger.warning("블로그 #%d의 숫자 필드 '%s'가 유효하지 않음: '%s'", 
                                     blog_index, field, blog.get(field, ""))
                        warnings.append(f"블로그 #{blog_index}의 '{field}' 값 '{blog.get(field, '')}'이 숫자 형식이 아닙니다.")
            
            # 5. blog_name 길이 검증 (너무 짧거나 긴 경우)
            if "blog_name" in blog and blog["blog_name"]:
                name_length = len(blog["blog_name"])
                if name_length < 3:
                    warnings.append(f"블로그 #{blog_index}의 이름이 너무 짧습니다 ({name_length}자). 더 구체적인 이름이 권장됩니다.")
                elif name_length > 100:
                    warnings.append(f"블로그 #{blog_index}의 이름이 너무 깁니다 ({name_length}자). 간결한 이름이 권장됩니다.")
    
    # 6. 최소 블로그 수 확인
    if len(blog_data_list) < settings.MINIMUM_BLOGS_TO_COLLECT:
        logger.warning("수집된 블로그 수(%d)가 최소 요구 사항(%d)보다 적음",
                     len(blog_data_list), settings.MINIMUM_BLOGS_TO_COLLECT)
        errors.append(f"수집된 블로그 수({len(blog_data_list)})가 최소 요구 사항({settings.MINIMUM_BLOGS_TO_COLLECT})보다 적습니다.")
    
    # 7. 중복 검사 (blog_id 또는 blog_url 기준)
    blog_ids = [blog.get("blog_id") for blog in blog_data_list if "blog_id" in blog and blog["blog_id"]]
    blog_urls = [blog.get("blog_url") for blog in blog_data_list if "blog_url" in blog and blog["blog_url"]]
    
    duplicate_ids = set([bid for bid in blog_ids if blog_ids.count(bid) > 1])
    duplicate_urls = set([url for url in blog_urls if blog_urls.count(url) > 1])
    
    if duplicate_ids:
        logger.warning("중복된 blog_id 발견: %s", duplicate_ids)
        warnings.append(f"중복된 blog_id가 발견되었습니다: {', '.join(duplicate_ids)}. 각 블로그는 고유한 ID를 가져야 합니다.")
    
    if duplicate_urls:
        logger.warning("중복된 blog_url 발견: %s", duplicate_urls)
        warnings.append(f"중복된 blog_url이 발견되었습니다: {', '.join(duplicate_urls)}. 각 블로그는 고유한 URL을 가져야 합니다.")
    
    # 8. 유효한 데이터 비율 확인
    valid_data_count = sum(1 for blog in blog_data_list if 
                          all(field in blog and blog[field] and blog[field] != "Not Found" 
                              for field in required_fields))
    
    valid_data_ratio = valid_data_count / len(blog_data_list) if blog_data_list else 0
    if valid_data_ratio < 0.7 and valid_data_count >= 1:  # 최소 1개 이상의 유효 데이터가 있고, 70% 미만인 경우
        logger.warning("유효한 데이터 비율이 낮음: %.2f%%", valid_data_ratio * 100)
        warnings.append(f"유효한 데이터 비율이 낮습니다 ({valid_data_ratio:.0%}). 더 많은 완전한 블로그 데이터를 수집하는 것이 권장됩니다.")
    
    if errors:
        logger.info("블로그 데이터 검증 실패: %d개 오류, %d개 경고 발견", len(errors), len(warnings))
    else:
        if warnings:
            logger.info("블로그 데이터 검증 성공 (경고 있음): %d개 경고 발견", len(warnings))
        else:
            logger.info("블로그 데이터 검증 성공: 모든 항목이 유효함")
    
    return errors, warnings


@tool(args_schema=FinalizeBlogDataInput)
def finalize_blog_data_collection(
    collected_blogs_summary: List[BlogData],
    all_tasks_completed: bool,
    quality_score: Optional[float] = None,
    recommendations: Optional[List[str]] = None,
    data_writer: Optional[Any] = None
) -> ToolResponse:
    """
    수집된 모든 블로그 정보를 검토하고, 지정된 형식으로 최종 정리하여 저장합니다.
    
    이 도구는 모든 수집 작업이 완료된 후에 호출하여, 수집된 데이터를 검증하고 저장합니다.
    필요에 따라 수집된 데이터에 대한 품질 점수와 추가 권장 사항을 포함할 수 있습니다.
    
    Args:
        collected_blogs_summary (List[BlogData]): 지금까지 수집된 블로그들의 요약 정보 목록.
            각 블로그 정보는 딕셔너리 형태로, 최소한 blog_id, blog_name, blog_url 필드를 포함해야 합니다.
            
        all_tasks_completed (bool): 모든 요청된 블로그 정보 수집 작업이 완료되었는지 여부.
            False인 경우 데이터 저장을 진행하지 않고 오류를 반환합니다.
            
        quality_score (Optional[float], optional): 수집된 데이터의 전체 품질 점수 (1-10).
            데이터 품질에 대한 메타데이터로 저장됩니다. 기본값은 None입니다.
            
        recommendations (Optional[List[str]], optional): 추가 검색이나 개선을 위한 지능적 제안사항.
            데이터 개선을 위한 추천 사항을 리스트 형태로 제공합니다. 기본값은 None입니다.
            
        data_writer (Optional[Any], optional): 데이터 저장에 사용할 DataWriter 인스턴스.
            테스트 목적이나 의존성 주입 시 유용합니다. 기본값은 None이며, 
            이 경우 get_data_writer() 함수를 통해 인스턴스를 얻습니다.
        
    Returns:
        ToolResponse: 도구 실행 결과를 담은 딕셔너리.
            성공 시: {
                'status': 'success', 
                'data': {
                    'saved_file_path': '파일 경로', 
                    'summary_stats': {
                        'total_blogs': 10, 
                        'quality_score': 8.5,
                        'saved_file_name': 'filename.xlsx',
                        'saved_file_path': '/path/to/file.xlsx',
                        'recommendations': ['추천1', '추천2'] # recommendations가 제공된 경우
                    },
                    'message': '데이터 수집이 성공적으로 완료되었습니다. 총 10개의 블로그 정보가 저장되었습니다.'
                }
            }
            실패 시: {
                'status': 'error', 
                'error_message': '오류 메시지'
            }
    
    Raises:
        ValueError: 입력 매개변수의 형식이 올바르지 않은 경우
        TypeError: 입력 매개변수의 타입이 올바르지 않은 경우
        FileNotFoundError: 파일 경로가 존재하지 않는 경우
        PermissionError: 파일 접근 권한이 없는 경우
        ImportError: DataWriter 모듈을 임포트할 수 없는 경우
        Exception: 기타 예상치 못한 오류가 발생한 경우
    
    Example:
        >>> blogs = [
        ...     {
        ...         "blog_id": "example_blog_1",
        ...         "blog_name": "기술 블로그 1",
        ...         "blog_url": "https://example.com/blog1",
        ...         "recent_post_date": "2023-05-15"
        ...     }
        ... ]
        >>> result = finalize_blog_data_collection(
        ...     collected_blogs_summary=blogs,
        ...     all_tasks_completed=True,
        ...     quality_score=8.5,
        ...     recommendations=["추가 검색 고려"]
        ... )
        >>> result["status"]
        'success'
    """
    logger.info("데이터 수집 완료 도구 실행 시작")
    
    try:
        # 입력 검증 - 타입 체크
        if not isinstance(collected_blogs_summary, list):
            logger.error("collected_blogs_summary 형식 오류: 리스트가 아님 (실제 타입: %s)", 
                        type(collected_blogs_summary).__name__)
            return format_tool_response(
                status="error",
                error_message="수집된 블로그 데이터는 리스트 형식이어야 합니다. 다른 형식이 제공되었습니다."
            )
            
        if not isinstance(all_tasks_completed, bool):
            logger.error("all_tasks_completed 형식 오류: 불리언이 아님 (실제 타입: %s)", 
                        type(all_tasks_completed).__name__)
            return format_tool_response(
                status="error",
                error_message="작업 완료 상태는 불리언(True/False) 형식이어야 합니다. 다른 형식이 제공되었습니다."
            )
        
        # quality_score 타입 검증 (제공된 경우)
        if quality_score is not None and not isinstance(quality_score, (int, float)):
            logger.error("quality_score 형식 오류: 숫자가 아님 (실제 타입: %s)", 
                        type(quality_score).__name__)
            return format_tool_response(
                status="error",
                error_message="품질 점수는 숫자 형식이어야 합니다. 다른 형식이 제공되었습니다."
            )
        
        # recommendations 타입 검증 (제공된 경우)
        if recommendations is not None and not isinstance(recommendations, list):
            logger.error("recommendations 형식 오류: 리스트가 아님 (실제 타입: %s)", 
                        type(recommendations).__name__)
            return format_tool_response(
                status="error",
                error_message="추천 사항은 리스트 형식이어야 합니다. 다른 형식이 제공되었습니다."
            )
        
        # 모든 작업이 완료되었는지 확인
        if not all_tasks_completed:
            logger.warning("모든 작업이 완료되지 않은 상태에서 데이터 수집 완료 요청됨")
            return format_tool_response(
                status="error",
                error_message="모든 데이터 수집 작업이 아직 완료되지 않았습니다. 모든 작업이 완료된 후 다시 시도해 주세요."
            )
        
        # 블로그 데이터 유효성 검증
        logger.info("블로그 데이터 유효성 검증 시작 (총 %d개 항목)", len(collected_blogs_summary))
        errors, warnings = _validate_blog_data(collected_blogs_summary)
        
        if errors:
            error_msg = "데이터 검증 실패. 다음 문제를 해결해 주세요:\n" + "\n".join(errors)
            
            # 경고가 있는 경우 함께 표시
            if warnings:
                error_msg += "\n\n추가 경고사항 (저장에 영향을 주지 않음):\n" + "\n".join(warnings)
                
            logger.error("블로그 데이터 검증 실패: %d개 오류 발견", len(errors))
            return format_tool_response(
                status="error",
                error_message=error_msg
            )
        
        # 추가 메타데이터 보강
        logger.debug("블로그 데이터 메타데이터 보강 시작")
        enriched_count = 0
        for blog in collected_blogs_summary:
            # 소스 키워드 추가 (없는 경우)
            if "source_keyword" not in blog:
                blog["source_keyword"] = "unknown"
                enriched_count += 1
                
            # 데이터 검증 로직 추가
            for field in settings.DATA_FIELDS_TO_EXTRACT:
                if field not in blog or not blog[field]:
                    blog[field] = "Not Found"
                    enriched_count += 1
        logger.debug("블로그 데이터 메타데이터 보강 완료: %d개 필드 추가/수정됨", enriched_count)
        
        # 데이터 저장
        saved_file_path = None
        try:
            # data_writer 파라미터가 제공되었으면 그것을 사용, 아니면 get_data_writer()로 얻기
            logger.info("데이터 저장 시작")
            writer = get_data_writer(data_writer)
            saved_file_path = writer.save_data(collected_blogs_summary)
            
            if not saved_file_path:
                logger.error("데이터 저장 실패: save_data가 유효한 파일 경로를 반환하지 않음")
                return format_tool_response(
                    status="error",
                    error_message="데이터 저장 중 오류가 발생했습니다. 파일 경로를 얻을 수 없습니다."
                )
            
            logger.info("데이터 저장 성공: %s", saved_file_path)
        except ImportError as ie:
            # DataWriter를 임포트할 수 없는 경우
            logger.error("DataWriter 모듈 임포트 오류: %s", str(ie))
            return format_tool_response(
                status="error",
                error_message=f"데이터 저장 모듈을 초기화할 수 없습니다. 필요한 모듈이 설치되어 있는지 확인해 주세요. 세부 오류: {str(ie)}"
            )
        except FileNotFoundError as fnf:
            # 파일 경로가 존재하지 않는 경우
            logger.error("파일 경로 오류: %s, 경로: %s", str(fnf), fnf.filename)
            return format_tool_response(
                status="error",
                error_message=f"데이터를 저장할 경로가 존재하지 않습니다. 저장 경로를 확인해 주세요: {fnf.filename}"
            )
        except PermissionError as pe:
            # 파일 접근 권한이 없는 경우
            logger.error("파일 접근 권한 오류: %s", str(pe))
            return format_tool_response(
                status="error",
                error_message="데이터를 저장할 파일에 접근 권한이 없습니다. 파일 권한을 확인해 주세요."
            )
        except OSError as ose:
            # 파일 시스템 관련 오류
            logger.error("파일 시스템 오류: %s", str(ose))
            return format_tool_response(
                status="error",
                error_message=f"파일 시스템 오류로 데이터를 저장할 수 없습니다: {str(ose)}"
            )
        except Exception as e:
            # 기타 예상치 못한 오류
            logger.error("데이터 저장 중 예상치 못한 오류 발생: %s\n%s", 
                        str(e), traceback.format_exc())
            return format_tool_response(
                status="error",
                error_message=f"데이터 저장 중 예상치 못한 오류가 발생했습니다: {str(e)}"
            )
        
        # 요약 통계 생성
        logger.debug("요약 통계 생성 시작")
        summary_stats: Dict[str, Any] = {
            "total_blogs": len(collected_blogs_summary),
            "quality_score": quality_score if quality_score is not None else "Not Provided",
            "saved_file_name": os.path.basename(saved_file_path),
            "saved_file_path": saved_file_path,
        }
        
        # 경고가 있으면 요약 통계에 포함
        if warnings:
            summary_stats["warnings"] = warnings
            summary_stats["warnings_count"] = len(warnings)
        
        # 추천 사항 포함 (있는 경우)
        if recommendations:
            summary_stats["recommendations"] = recommendations
            logger.debug("추천 사항 포함됨: %d개", len(recommendations))
        
        success_message = f"데이터 수집이 성공적으로 완료되었습니다. 총 {len(collected_blogs_summary)}개의 블로그 정보가 저장되었습니다."
        
        # 경고가 있는 경우 메시지에 추가
        if warnings:
            success_message += f" ({len(warnings)}개의 경고가 있지만 저장에는 영향을 주지 않습니다.)"
        
        logger.info(success_message)
        
        # 로그에 요약 통계 기록 (디버깅용)
        logger.debug("요약 통계: %s", json.dumps(summary_stats, ensure_ascii=False, indent=2))
        
        return format_tool_response(
            status="success",
            data={
                "summary_stats": summary_stats,
                "message": success_message,
                "saved_file_path": saved_file_path
            }
        )
    
    except ValueError as ve:
        # 값 오류 (유효하지 않은 입력값)
        logger.error("값 오류: %s", str(ve))
        return format_tool_response(
            status="error",
            error_message=f"입력값이 유효하지 않습니다: {str(ve)}"
        )
    except TypeError as te:
        # 타입 오류 (잘못된 인자 타입)
        logger.error("타입 오류: %s", str(te))
        return format_tool_response(
            status="error",
            error_message=f"입력 타입이 올바르지 않습니다: {str(te)}"
        )
    except Exception as e:
        # 기타 예외 처리
        logger.error("데이터 수집 완료 중 예상치 못한 오류 발생: %s\n%s", 
                    str(e), traceback.format_exc())
        
        # 디버깅 정보를 로그에 기록
        logger.debug("오류 발생 시점 컨텍스트 - collected_blogs_summary 길이: %d, all_tasks_completed: %s",
                    len(collected_blogs_summary) if isinstance(collected_blogs_summary, list) else -1,
                    all_tasks_completed)
        
        return format_tool_response(
            status="error",
            error_message=f"데이터 수집 완료 중 오류가 발생했습니다: {str(e)}"
        )


# 직접 실행 시 테스트
if __name__ == "__main__":
    # 로깅 설정 (콘솔 출력용)
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 테스트용 데이터로 도구 테스트
    logger.info("테스트 실행 시작")
    test_blogs: List[BlogData] = [
        {
            "blog_id": "example_blog_1",
            "blog_name": "기술 블로그 1",
            "blog_url": "https://example.com/blog1",
            "recent_post_date": "2023-05-15",
            "first_post_date": "2020-01-10",
            "total_posts": "156",
            "blog_creation_date": "2019-12-25",
            "average_visitors": "약 1,200명/월",
            "llm_summary": "인공지능과 머신러닝에 관한 기술 블로그입니다."
        },
        {
            "blog_id": "example_blog_2",
            "blog_name": "기술 블로그 2",
            "blog_url": "https://example.com/blog2",
            "recent_post_date": "2023-06-20",
            "first_post_date": "2021-03-05",
            "total_posts": "87",
            "blog_creation_date": "2021-02-28",
            "average_visitors": "약 800명/월",
            "llm_summary": "웹 개발과 프론트엔드 기술에 관한 블로그입니다."
        }
    ]
    
    test_result = finalize_blog_data_collection(
        collected_blogs_summary=test_blogs,
        all_tasks_completed=True,
        quality_score=8.5,
        recommendations=["추가 프로그래밍 블로그 검색 고려", "검색어 범위 확장 추천"]
    )
    
    logger.info("테스트 결과: %s", json.dumps(test_result, ensure_ascii=False, indent=2)) 