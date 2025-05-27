# core/data_extractor.py
from config import settings  # DATA_FIELDS_TO_EXTRACT 사용
import logging
import re

logger = logging.getLogger(__name__)


class DataExtractor:
    def __init__(self):
        pass

    def _derive_blog_id(self, url, blog_name=None):
        # ... (이전 코드와 동일한 _derive_blog_id 함수) ...
        try:
            domain = re.sub(r'^https?://', '', url).split('/')[0]
            domain = domain.replace("www.", "")
            blog_id_part = domain.replace(".", "_").replace("-", "_")
            if blog_name:
                name_part = "".join(filter(str.isalnum, blog_name.lower().replace(" ", "_")))[:20]
                return f"{blog_id_part}_{name_part}"
            return blog_id_part
        except Exception:
            return "unknown_blog_id"

    def structure_blog_info(self, raw_info_from_llm_or_browse: dict, blog_url: str) -> dict:
        """
        LLM이나 브라우저에서 추출된 정보를 바탕으로 DATA_FIELDS_TO_EXTRACT 에 맞춰 구조화합니다.
        
        개선된 기능:
        - 유연한 필드명 매핑: LLM이 다양한 필드명으로 정보를 제공해도 올바른 필드로 매핑
        - 포괄적인 대체 필드명 지원: title → blog_name, url → blog_url 등
        - 상세한 매핑 로깅: 디버깅을 위한 매핑 과정 추적
        """
        logger.debug(f"구조화 시작: {blog_url}, 원본 정보: {raw_info_from_llm_or_browse}")
        
        # 유연한 필드 매핑 테이블 - LLM이 사용할 수 있는 다양한 필드명 패턴
        field_mapping_table = {
            "blog_name": ["blog_name", "title", "site_title", "website_name", "name", "blog_title"],
            "blog_url": ["blog_url", "url", "website_url", "site_url", "link"],
            "recent_post_date": ["recent_post_date", "latest_post_date", "last_post_date", "newest_post_date", "latest_post"],
            "first_post_date": ["first_post_date", "first_post_date_info", "earliest_post_date", "start_date", "first_post"],
            "total_posts": ["total_posts", "total_posts_info", "post_count", "article_count", "number_of_posts", "posts_count"],
            "blog_creation_date": ["blog_creation_date", "blog_creation_date_info", "created_date", "founding_date", "launch_date"],
            "average_visitors": ["average_visitors", "average_visitors_hint", "monthly_visitors", "visitor_count", "traffic", "page_views"],
            "llm_summary": ["llm_summary", "main_content_summary", "summary", "description", "about", "content_summary"]
        }
        
        # 기본 구조 초기화
        structured_data = {field: "Not Found" for field in settings.DATA_FIELDS_TO_EXTRACT}
        structured_data["blog_url"] = blog_url

        if not isinstance(raw_info_from_llm_or_browse, dict):
            logger.warning(f"잘못된 형식의 원본 정보 수신: {raw_info_from_llm_or_browse}")
            structured_data["blog_name"] = "Data Extraction Error"
            structured_data["blog_id"] = self._derive_blog_id(blog_url, "Data Extraction Error")
            return structured_data

        # 유연한 필드 매핑 수행
        mapping_results = {}  # 디버깅용 매핑 결과 추적
        
        for target_field, possible_source_fields in field_mapping_table.items():
            if target_field not in settings.DATA_FIELDS_TO_EXTRACT:
                continue  # 설정에 없는 필드는 건너뛰기
                
            found_value = None
            found_source = None
            
            # 가능한 소스 필드들을 순서대로 확인
            for source_field in possible_source_fields:
                if source_field in raw_info_from_llm_or_browse:
                    found_value = raw_info_from_llm_or_browse[source_field]
                    found_source = source_field
                    break
            
            if found_value is not None and found_value != "":
                # 특별 처리: total_posts는 문자열로 변환
                if target_field == "total_posts":
                    structured_data[target_field] = str(found_value)
                else:
                    structured_data[target_field] = found_value
                    
                mapping_results[target_field] = f"{found_source} → {found_value}"
                logger.debug(f"필드 매핑 성공: {target_field} = {found_source} → {found_value}")
            else:
                mapping_results[target_field] = "값 없음"
                logger.debug(f"필드 매핑 실패: {target_field} - 소스 필드들 {possible_source_fields}에서 값을 찾을 수 없음")

        # blog_id는 blog_name을 바탕으로 생성
        structured_data["blog_id"] = self._derive_blog_id(blog_url, structured_data.get("blog_name", "Unknown"))
        
        # 누락된 필드들을 "Not Found"로 설정
        for field in settings.DATA_FIELDS_TO_EXTRACT:
            if field not in structured_data or structured_data[field] is None or structured_data[field] == "":
                structured_data[field] = "Not Found"

        # 매핑 결과 요약 로깅
        successful_mappings = [k for k, v in mapping_results.items() if v != "값 없음"]
        failed_mappings = [k for k, v in mapping_results.items() if v == "값 없음"]
        
        logger.info(f"구조화 완료: {blog_url} -> {structured_data.get('blog_name')}")
        logger.debug(f"성공한 매핑 ({len(successful_mappings)}개): {', '.join(successful_mappings)}")
        if failed_mappings:
            logger.debug(f"실패한 매핑 ({len(failed_mappings)}개): {', '.join(failed_mappings)}")
        
        return structured_data