# pipelines/agent_pipeline.py
import asyncio
import json
import logging
import re
import traceback
from typing import List, Dict, Any, Optional, Callable  # Optional, Callable 추가
from config import settings
from core.llm_handler import LLMHandler
from core.web_searcher import WebSearcher
from core.browser_controller import BrowserController
from core.data_extractor import DataExtractor
# DataWriter 사용을 가정하고 수정 (만약 ExcelWriter가 맞다면 이 부분과 클래스 내 self.data_writer 수정 필요)
from utils.excel_writer import DataWriter
from tools.tool_definitions import TOOLS_SPEC
# utils.improved_system_prompt에서 프롬프트 로더 가져오기
from utils.improved_system_prompt import get_improved_system_prompt, get_extraction_prompt

logger = logging.getLogger(__name__)


def get_browser_instance():
    """싱글턴 브라우저 컨트롤러 인스턴스를 반환합니다."""
    if not hasattr(get_browser_instance, "_instance") or get_browser_instance._instance is None:
        get_browser_instance._instance = BrowserController()
    return get_browser_instance._instance


class AgentPipeline:
    def __init__(self, streamlit_status_callback=None):
        self.llm_handler = LLMHandler()
        self.web_searcher = WebSearcher()
        self.browser_controller = get_browser_instance()
        self.data_extractor = DataExtractor()
        self.data_writer = DataWriter()  # ExcelWriter 대신 DataWriter 사용
        self.streamlit_status_callback = streamlit_status_callback

    def _update_status(self, message):
        """Streamlit UI에 상태 메시지를 업데이트합니다 (콜백이 제공된 경우)."""
        logger.info(f"Agent Status: {message}")
        if self.streamlit_status_callback:
            self.streamlit_status_callback(message)

    async def _execute_tool_call(self, tool_name: str, tool_args: dict, collected_data_for_all_blogs: list, messages_history=None):
        """LLM이 요청한 도구를 실행합니다."""
        self._update_status(f"[TOOL] 도구 실행 중: {tool_name} (인자: {tool_args})")

        if tool_name == "search_web_for_blogs":
            keyword = tool_args.get("keyword")
            if not keyword:
                return json.dumps({
                    "status": "error",
                    "message": "search_web_for_blogs 도구에 'keyword' 인자가 필요합니다."
                })

            search_results = self.web_searcher.search_links(keyword)
            urls = [res["url"] for res in search_results if res.get("url")]

            return json.dumps({
                "status": "success",
                "found_urls": urls,
                "summary": f"{len(urls)}개의 잠재적 블로그 URL을 찾았습니다."
            })

        elif tool_name == "get_webpage_content_and_interact":
            url = tool_args.get("url")
            # settings.DATA_FIELDS_TO_EXTRACT를 기본값으로 사용
            fields_to_extract = tool_args.get("fields_to_extract", settings.DATA_FIELDS_TO_EXTRACT)
            action_details = tool_args.get("action_details")

            if not url:
                return json.dumps({
                    "status": "error",
                    "message": "get_webpage_content_and_interact 도구에 'url' 인자가 필요합니다."
                })

            # URL 유효성 검사 (간단한 형태로 통일)
            if not url.startswith(('http://', 'https://')):
                logger.warning(f"Invalid URL format detected: {url}")
                return json.dumps({
                    "status": "error",
                    "url": url,
                    "message": f"Invalid URL format: {url}. URL must start with http:// or https://"
                })

            self._update_status(f"[WEB] 웹사이트 방문 및 원시 데이터 수집 시도: {url}")

            action_type = None
            selector = None
            input_text = None

            if action_details:  # action_details가 None이 아닐 경우에만 내부 값 접근
                action_type = action_details.get("action_type")
                selector = action_details.get("selector")
                input_text = action_details.get("input_text")

            raw_result = await self.browser_controller.browse_website(
                url=url,
                action=action_type,
                selector=selector,
                input_text=input_text
                # close_browser=False # 루프 내에서는 브라우저 유지 (AgentPipeline에서 관리)
            )

            if raw_result["status"] == "success":
                # 추출된 텍스트 콘텐츠 품질 검증
                text_content = raw_result.get("data", {}).get("text_content", "")
                text_length = len(text_content.strip()) if text_content else 0
                
                # 컨텐츠 품질 검증 및 경고
                content_quality_warning = ""
                if text_length == 0:
                    content_quality_warning = "⚠️ 빈 컨텐츠가 추출되었습니다."
                    logger.warning(f"Empty content extracted from {url}")
                elif text_length < 100:
                    content_quality_warning = f"⚠️ 매우 짧은 컨텐츠가 추출되었습니다 ({text_length} 문자)."
                    logger.warning(f"Very short content extracted from {url}: {text_length} characters")
                elif text_length < 300:
                    content_quality_warning = f"⚠️ 짧은 컨텐츠가 추출되었습니다 ({text_length} 문자)."
                    logger.info(f"Short content extracted from {url}: {text_length} characters")
                else:
                    logger.info(f"Good content extracted from {url}: {text_length} characters")
                    # 🚀 강제 도구 호출: LLM이 extract_blog_fields_from_text를 호출하지 않는 문제 해결
                    self._update_status("🚀 좋은 컨텐츠 감지! extract_blog_fields_from_text 도구 강제 호출...")
                    
                    try:
                        # extract_blog_fields_from_text 도구 직접 호출
                        extract_result = await self._execute_tool_call(
                            "extract_blog_fields_from_text",
                            {
                                "text_content": text_content[:5000],  # 처음 5000자만 사용
                                "original_url": url
                            },
                            collected_data_for_all_blogs,
                            messages_history
                        )
                        
                        if extract_result:
                            extract_result_obj = json.loads(extract_result)
                            if extract_result_obj.get('status') == 'success':
                                self._update_status("✅ 강제 도구 호출로 블로그 데이터 추출 성공!")
                                logger.info(f"[FORCE EXTRACT] Successfully extracted blog data: {extract_result_obj.get('extracted_blog_name', 'Unknown')}")
                            else:
                                self._update_status("⚠️ 강제 도구 호출 실패")
                                logger.warning(f"[FORCE EXTRACT] Failed: {extract_result_obj.get('message', 'Unknown error')}")
                        
                    except Exception as e:
                        self._update_status(f"❌ 강제 도구 호출 중 오류: {e}")
                        logger.error(f"[FORCE EXTRACT] Error during forced tool call: {e}", exc_info=True)
                
                self._update_status(f"[PAGE] '{url}' 에서 웹페이지 내용 수신 완료. 텍스트 길이: {text_length} 문자")
                if content_quality_warning:
                    self._update_status(content_quality_warning)

                result = {
                    "status": "success",
                    "url": url,  # 요청된 URL
                    "final_url": raw_result["final_url"],  # 실제 도달한 URL
                    "page_title": raw_result["page_title"],
                    "action_performed": raw_result["action_performed"],
                    "requested_fields": fields_to_extract,  # LLM이 요청한 필드 정보 포함
                    "content_quality": {
                        "text_length": text_length,
                        "quality_status": "good" if text_length >= 300 else "short" if text_length >= 100 else "very_short" if text_length > 0 else "empty",
                        "warning": content_quality_warning,
                        "used_selector": raw_result.get("data", {}).get("used_selector", "unknown")
                    }
                }
                
                # browse_website 결과의 data 필드에서 text_content 또는 message 가져오기
                if "text_content" in raw_result.get("data", {}):
                    result["text_content"] = raw_result["data"]["text_content"]
                    
                    # 빈 컨텐츠나 매우 짧은 컨텐츠인 경우 LLM에게 추가 정보 제공
                    if text_length < 100:
                        result["content_extraction_note"] = f"추출된 컨텐츠가 매우 짧습니다 ({text_length} 문자). 이 URL에서 다른 셀렉터를 시도하거나 다른 URL을 찾아보는 것을 고려하세요. 페이지 제목: '{raw_result.get('page_title', 'Unknown')}'"
                        
                        # 네이버 블로그의 경우 추가 가이드라인 제공
                        if "blog.naver.com" in url:
                            result["naver_blog_note"] = "네이버 블로그에서 컨텐츠 추출이 어려울 수 있습니다. 모바일 버전이 아닌 데스크탑 버전 URL을 사용하고 있는지 확인하세요. 또는 다른 블로그 플랫폼을 시도해보세요."
                            
                elif "message" in raw_result.get("data", {}):  # 예: 클릭 성공 메시지 등
                    result["message"] = raw_result["data"]["message"]

                return json.dumps(result)
            else:
                self._update_status(f"⚠️ '{url}' 접근 중 오류 발생: {raw_result.get('error_message', '알 수 없는 오류')}")
                return json.dumps({
                    "status": "error",
                    "url": url,
                    "message": f"웹사이트 접근 실패: {raw_result.get('error_message', '알 수 없는 오류')}"
                })

        elif tool_name == "extract_blog_fields_from_text":
            text_content = tool_args.get("text_content")
            original_url = tool_args.get("original_url") or tool_args.get("url")  # url도 허용
            source_keyword = tool_args.get("source_keyword", "unknown_keyword")  # 검색 키워드 추가
            
            # messages_history가 제공된 경우 키워드 복구 시도
            if source_keyword == "unknown_keyword" and messages_history:
                # 1. search_web_for_blogs 도구 호출에서 키워드 찾기
                for msg in reversed(messages_history):
                    if msg.get("role") == "assistant" and msg.get("tool_calls"):
                        for tool_call in msg.get("tool_calls", []):
                            if tool_call.get("function", {}).get("name") == "search_web_for_blogs":
                                try:
                                    args_str = tool_call.get("function", {}).get("arguments", "{}")
                                    # arguments가 이미 dict인 경우 그대로 사용
                                    if isinstance(args_str, dict):
                                        args = args_str
                                    else:
                                        args = json.loads(args_str)
                                    if args.get("keyword"):
                                        source_keyword = args["keyword"]
                                        logger.info(f"[KEYWORD RECOVERY] Found keyword from search tool: {source_keyword}")
                                        break
                                except (json.JSONDecodeError, TypeError):
                                    pass
                        if source_keyword != "unknown_keyword":
                            break
                
                # 2. 첫 번째 사용자 메시지에서 키워드 추출
                if source_keyword == "unknown_keyword":
                    for msg in messages_history[:3]:  # 초기 메시지 확인
                        if msg.get("role") == "user":
                            content_text = msg.get("content", "")
                            # 다양한 패턴으로 키워드 추출
                            patterns = [
                                r'키워드[:\s]*([^\s,에대한까지]+)',
                                r'다음 키워드[:\s]*([^\s,에대한까지]+)',
                                r'["\']([a-zA-Z가-힣]+)["\']',
                                r'([a-zA-Z]+)에? ?대한',
                                r'([a-zA-Z가-힣]+)\s*정보'
                            ]
                            for pattern in patterns:
                                keyword_match = re.search(pattern, content_text, re.IGNORECASE)
                                if keyword_match:
                                    candidate = keyword_match.group(1).lower().strip()
                                    if len(candidate) > 1 and candidate not in ['키워드', '정보', '대한']:
                                        source_keyword = candidate
                                        logger.info(f"[KEYWORD RECOVERY] Extracted keyword from user message: {source_keyword}")
                                        break
                            if source_keyword != "unknown_keyword":
                                break

            # 텍스트 컨텐츠 품질 및 유효성 검증
            if not text_content:  # text_content는 필수
                return json.dumps({
                    "status": "error",
                    "message": "extract_blog_fields_from_text 도구에 'text_content' 인자가 필요합니다."
                })
            if not original_url:  # original_url 또는 url도 필수
                return json.dumps({
                    "status": "error",
                    "message": "extract_blog_fields_from_text 도구에 'original_url' 또는 'url' 인자가 필요합니다."
                })
            
            # 텍스트 컨텐츠 길이 및 품질 검증
            text_content_stripped = text_content.strip()
            text_length = len(text_content_stripped)
            
            if text_length == 0:
                logger.warning(f"Empty text content provided for extraction from {original_url}")
                return json.dumps({
                    "status": "error",
                    "message": f"Empty text content provided for {original_url}. Cannot extract blog information from empty text.",
                    "suggestion": "Try browsing the URL again with different selectors or check if the page loaded correctly."
                })
            
            if text_length < 50:
                logger.warning(f"Very short text content provided for extraction from {original_url}: {text_length} characters")
                return json.dumps({
                    "status": "error", 
                    "message": f"Text content too short for reliable extraction from {original_url} ({text_length} characters).",
                    "text_preview": text_content_stripped[:100],
                    "suggestion": "The extracted text is too short to contain meaningful blog information. Try using different CSS selectors or browse a different URL."
                })

            self._update_status(f"✍️ '{original_url}'의 텍스트에서 정보 추출 시도 (LLM 호출)... 텍스트 길이: {text_length} 문자")
            logger.info(f"[EXTRACTION START] URL: {original_url}, Keyword: {source_keyword}, Text Length: {text_length}")
            logger.debug(f"[EXTRACTION DEBUG] Text content length: {len(text_content)} characters")
            logger.debug(f"[EXTRACTION DEBUG] Text preview (first 300 chars): {text_content[:300]}...")

            # 개선된 LLM 프롬프트 사용 (get_extraction_prompt 직접 사용)
            extraction_system_prompt = get_extraction_prompt()
            
            # 텍스트 길이에 따른 경고 메시지 추가
            content_quality_note = ""
            if text_length < 200:
                content_quality_note = f"\n\n⚠️ CONTENT WARNING: The provided text is quite short ({text_length} characters). This may indicate:\n1. Poor content extraction due to dynamic loading\n2. Incorrect CSS selectors used for content extraction\n3. Access restrictions, login required, or content behind paywall\n4. The page may not contain the expected blog content\n5. Mobile/responsive version with limited content display\n\nPlease extract what information you can, but note any limitations in your response. If blog information cannot be reliably extracted due to insufficient content, indicate this clearly."
            elif text_length < 500:
                content_quality_note = f"\n\n⚠️ Note: The provided text is relatively short ({text_length} characters). Extract available information but be aware of potential content limitations."
            
            extraction_user_prompt = f"Extract information from this text from URL '{original_url}':{content_quality_note}\n\nSource keyword: {source_keyword}\nText length: {text_length} characters\nURL: {original_url}\n\nText content:\n{text_content}"

            extraction_messages = [
                {"role": "system", "content": extraction_system_prompt},
                {"role": "user", "content": extraction_user_prompt}
            ]

            logger.debug(f"[EXTRACTION DEBUG] System prompt length: {len(extraction_system_prompt)} characters")
            logger.debug(f"[EXTRACTION DEBUG] User prompt length: {len(extraction_user_prompt)} characters")

            llm_response = self.llm_handler.chat_with_ollama_for_tools(
                extraction_messages,
                []  # 도구 없이 텍스트 생성만 요청
            )
            extracted_json_string = llm_response.get("content", "{}")
            logger.info(f"[EXTRACTION LLM] Raw LLM response for {original_url}: {extracted_json_string}")
            logger.debug(f"[EXTRACTION LLM] Response length: {len(extracted_json_string)} characters")

            try:
                # 개선된 JSON 파싱 로직 사용
                def robust_json_parse(json_string):
                    # 1단계: 표준 JSON 파싱
                    try:
                        return json.loads(json_string)
                    except json.JSONDecodeError:
                        pass
                    # 2단계: single quotes를 double quotes로 변환
                    try:
                        json_compatible = json_string.replace("'", '"')
                        return json.loads(json_compatible)
                    except json.JSONDecodeError:
                        pass
                    # 3단계: ast.literal_eval 사용
                    try:
                        import ast
                        return ast.literal_eval(json_string)
                    except (ValueError, SyntaxError):
                        pass
                    # 4단계: 정규식으로 JSON 추출 후 재시도
                    json_pattern = r'(\{[\s\S]*\})'
                    json_match = re.search(json_pattern, json_string)
                    if json_match:
                        json_str_cleaned = json_match.group(1).replace("'", '"')
                        try:
                            return json.loads(json_str_cleaned)
                        except json.JSONDecodeError:
                            pass
                    return None

                # 먼저 마크다운 코드 블록 처리
                match_markdown_json = re.search(r'```json\s*(\{[\s\S]*?\})\s*```', extracted_json_string, re.DOTALL)
                if match_markdown_json:
                    json_str_to_parse = match_markdown_json.group(1)
                else:
                    json_str_to_parse = extracted_json_string

                extracted_info_dict = robust_json_parse(json_str_to_parse)
                
                if extracted_info_dict is None:
                    # 최후의 수단: 원본 문자열로 재시도
                    extracted_info_dict = robust_json_parse(extracted_json_string)
                    if extracted_info_dict is None:
                        raise json.JSONDecodeError("모든 파싱 방법 실패", extracted_json_string, 0)
                
                logger.debug(f"성공적으로 파싱된 데이터: {extracted_info_dict}")
                logger.debug(f"[EXTRACTION PARSING] Parsed data type: {type(extracted_info_dict)}, keys: {list(extracted_info_dict.keys()) if isinstance(extracted_info_dict, dict) else 'Not a dict'}")

                logger.info(f"[EXTRACTION MAPPING] Starting structure_blog_info for {original_url}")
                structured_blog_info = self.data_extractor.structure_blog_info(extracted_info_dict, original_url)
                logger.info(f"[EXTRACTION MAPPING] Structured result: {structured_blog_info}")
                
                # source_keyword 정보도 추가
                if 'source_keyword' not in structured_blog_info or not structured_blog_info['source_keyword']:
                    structured_blog_info['source_keyword'] = source_keyword
                    logger.debug(f"[EXTRACTION MAPPING] Added source_keyword: {source_keyword}")
                    
                collected_data_for_all_blogs.append(structured_blog_info)
                logger.info(f"[EXTRACTION SUCCESS] Data added to collection. Total blogs: {len(collected_data_for_all_blogs)}")

                self._update_status(
                    f"✅ 정보 추출 및 저장 완료: {original_url} -> {structured_blog_info.get('blog_name', 'Unknown')}")
                logger.info(f"[EXTRACTION COMPLETE] Final structured data for {original_url}: {structured_blog_info}")
                return json.dumps({
                    "status": "success",
                    "message": f"Successfully extracted and structured data for {original_url}.",
                    "extracted_blog_name": structured_blog_info.get("blog_name", "Unknown"),
                    "extraction_summary": {
                        "blog_name": structured_blog_info.get("blog_name", "Unknown"),
                        "blog_id": structured_blog_info.get("blog_id", "Unknown"),
                        "recent_post_date": structured_blog_info.get("recent_post_date", "Not Found"),
                        "total_posts": structured_blog_info.get("total_posts", "Not Found"),
                        "source_keyword": structured_blog_info.get("source_keyword", "unknown_keyword")
                    }
                })
            except json.JSONDecodeError as e:
                logger.error(f"LLM 정보 추출 결과 JSON 파싱 실패 ({original_url}): {extracted_json_string}. 오류: {e}")
                return json.dumps({
                    "status": "error",
                    "message": f"Failed to parse JSON from LLM's extraction for {original_url}.",
                    "raw_llm_output": extracted_json_string[:500] + ("..." if len(extracted_json_string) > 500 else "")
                })
            except Exception as e_struct:  # DataExtractor.structure_blog_info 등에서 발생할 수 있는 예외
                logger.error(f"DataExtractor 처리 중 오류 ({original_url}): {e_struct}", exc_info=True)
                return json.dumps({
                    "status": "error",
                    "message": f"Error structuring extracted data for {original_url}: {str(e_struct)}",
                    "raw_llm_output": extracted_json_string[:500] + ("..." if len(extracted_json_string) > 500 else "")
                })

        elif tool_name == "analyze_blog_quality":
            blog_url = tool_args.get("blog_url")
            content_sample = tool_args.get("content_sample", "")
            evaluation_criteria = tool_args.get("evaluation_criteria", ["authority", "freshness", "depth", "relevance"])
            
            if not blog_url:
                return json.dumps({
                    "status": "error",
                    "message": "analyze_blog_quality 도구에 'blog_url' 인자가 필요합니다."
                })
            
            # Gemma3-Tools의 고급 분석 능력을 활용한 블로그 품질 평가
            quality_analysis_prompt = f"""
            Analyze the quality of this blog based on the following criteria: {', '.join(evaluation_criteria)}
            
            Blog URL: {blog_url}
            Content Sample: {content_sample[:1000]}...
            
            Provide a detailed quality assessment including:
            1. Authority score (1-10)
            2. Content freshness (1-10)
            3. Content depth (1-10)
            4. Topic relevance (1-10)
            5. Overall quality score (1-10)
            6. Specific strengths and weaknesses
            7. Recommendation (extract/skip)
            
            Return as JSON format.
            """
            
            quality_messages = [{"role": "user", "content": quality_analysis_prompt}]
            quality_response = self.llm_handler.chat_with_ollama_for_tools(quality_messages, [])
            quality_result = quality_response.get("content", "{}")
            
            try:
                quality_data = json.loads(quality_result)
                return json.dumps({
                    "status": "success",
                    "blog_url": blog_url,
                    "quality_analysis": quality_data,
                    "recommendation": quality_data.get("recommendation", "extract")
                })
            except json.JSONDecodeError:
                return json.dumps({
                    "status": "success",
                    "blog_url": blog_url,
                    "quality_analysis": {"raw_analysis": quality_result},
                    "recommendation": "extract"  # 기본값
                })
                
        elif tool_name == "smart_search_refinement":
            original_keyword = tool_args.get("original_keyword")
            search_results_quality = tool_args.get("search_results_quality")
            target_blog_types = tool_args.get("target_blog_types", [])
            
            if not original_keyword or not search_results_quality:
                return json.dumps({
                    "status": "error",
                    "message": "smart_search_refinement 도구에 'original_keyword'와 'search_results_quality' 인자가 필요합니다."
                })
            
            # Gemma3-Tools로 지능적 검색 전략 개선
            refinement_prompt = f"""
            Original keyword: {original_keyword}
            Search results quality: {search_results_quality}
            Target blog types: {', '.join(target_blog_types) if target_blog_types else 'Any'}
            
            Based on the search quality assessment, suggest improved search strategies:
            1. Alternative keywords or phrases
            2. More specific search terms
            3. Different search approaches
            4. Platform-specific searches (e.g., "site:medium.com {original_keyword}")
            
            Provide 3-5 concrete suggestions for better search results.
            Return as JSON with 'suggested_keywords' array and 'search_strategy' description.
            """
            
            refinement_messages = [{"role": "user", "content": refinement_prompt}]
            refinement_response = self.llm_handler.chat_with_ollama_for_tools(refinement_messages, [])
            refinement_result = refinement_response.get("content", "{}")
            
            try:
                refinement_data = json.loads(refinement_result)
                return json.dumps({
                    "status": "success",
                    "original_keyword": original_keyword,
                    "search_refinements": refinement_data
                })
            except json.JSONDecodeError:
                return json.dumps({
                    "status": "success", 
                    "original_keyword": original_keyword,
                    "search_refinements": {"raw_suggestions": refinement_result}
                })

        elif tool_name == "finalize_blog_data_collection":
            all_done = tool_args.get("all_tasks_completed", False)
            quality_score = tool_args.get("quality_score", 0)
            recommendations = tool_args.get("recommendations", [])
            
            self._update_status(f"🏁 데이터 수집 마무리 단계. 수집된 블로그 수: {len(collected_data_for_all_blogs)}, 품질 점수: {quality_score}/10")
            
            # Gemma3-Tools로 최종 데이터 품질 검증
            if collected_data_for_all_blogs:
                final_analysis_prompt = f"""
                Analyze the collected blog data quality and completeness:
                
                Total blogs collected: {len(collected_data_for_all_blogs)}
                Sample data: {collected_data_for_all_blogs[0] if collected_data_for_all_blogs else {}}
                
                Evaluate:
                1. Data completeness (% of fields filled)
                2. Data accuracy assessment 
                3. Blog diversity and quality
                4. Areas for improvement
                5. Overall collection success rate
                
                Return JSON with analysis results.
                """
                
                analysis_messages = [{"role": "user", "content": final_analysis_prompt}]
                final_analysis = self.llm_handler.chat_with_ollama_for_tools(analysis_messages, [])
                analysis_result = final_analysis.get("content", "{}")
                
                try:
                    analysis_data = json.loads(analysis_result)
                    computed_quality_score = analysis_data.get("overall_success_rate", quality_score)
                except json.JSONDecodeError:
                    computed_quality_score = quality_score
                    analysis_data = {"raw_analysis": analysis_result}
            else:
                computed_quality_score = 0
                analysis_data = {"message": "수집된 데이터가 없습니다."}

            return json.dumps({
                "status": "success",
                "final_blog_count": len(collected_data_for_all_blogs),
                "all_done_by_llm": all_done,
                "quality_score": computed_quality_score,
                "quality_analysis": analysis_data,
                "recommendations": recommendations,
                "message": f"모든 블로그 데이터가 성공적으로 저장되었습니다. 품질 점수: {computed_quality_score}/10" if collected_data_for_all_blogs else "수집된 블로그 데이터가 없습니다."
            })

        else:
            logger.warning(f"알 수 없는 도구 요청: {tool_name}")
            return json.dumps({
                "status": "error",
                "message": f"알 수 없는 도구 '{tool_name}' 입니다."
            })

    async def run_agent_for_keywords(self, initial_keywords: list):
        self._update_status("에이전트 파이프라인 시작...")
        final_structured_blog_data = []  # 최종 수집 데이터를 저장할 리스트

        # 개선된 시스템 프롬프트 사용 (get_improved_system_prompt 직접 사용)
        system_prompt = get_improved_system_prompt(settings.DATA_FIELDS_TO_EXTRACT)

        messages_history = [{"role": "system", "content": system_prompt}]

        user_query = f"다음 키워드에 대한 블로그 정보를 수집해주세요: {', '.join(initial_keywords)}. 각 블로그에서 {', '.join(settings.DATA_FIELDS_TO_EXTRACT)} 정보를 추출해야 합니다."
        messages_history.append({"role": "user", "content": user_query})

        max_turns = settings.AGENT_MAX_TURNS

        try:
            # 브라우저 초기화 시도
            try:
                await self.browser_controller._ensure_browser()
                self._update_status("🌐 브라우저 초기화 완료.")
            except RuntimeError as e_browser:  # Playwright 드라이버 미설치 등 Runtime 에러
                self._update_status(f"⚠️ 브라우저 초기화 오류: {str(e_browser)}")
                self._update_status("Playwright 브라우저 드라이버 자동 설치를 시도합니다...")
                try:
                    process = await asyncio.create_subprocess_exec(
                        "python", "-m", "playwright", "install", "--with-deps",  # '--with-deps'로 필요한 모든 브라우저 설치
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE
                    )
                    stdout, stderr = await process.communicate()
                    if process.returncode == 0:
                        self._update_status("Playwright 브라우저 설치 성공. 다시 초기화합니다...")
                        await self.browser_controller._ensure_browser()
                        self._update_status("🌐 브라우저 재초기화 완료.")
                    else:
                        error_message = stderr.decode(errors='ignore') if stderr else "알 수 없는 설치 오류"
                        self._update_status(f"⚠️ Playwright 브라우저 자동 설치 실패: {error_message}")
                        raise RuntimeError(f"Playwright 브라우저 설치 실패 후 초기화 불가: {error_message}")
                except Exception as e_install:
                    self._update_status(f"⚠️ Playwright 브라우저 설치 프로세스 중 오류: {str(e_install)}")
                    raise RuntimeError(f"Playwright 환경 설정 실패: {str(e_install)}")

            for turn_count in range(max_turns):
                self._update_status(f"에이전트 작업 {turn_count + 1}/{max_turns}번째 턴 진행 중...")

                if final_structured_blog_data:
                    self._update_status(f"현재까지 {len(final_structured_blog_data)}개의 블로그 데이터가 수집되었습니다.")
                else:
                    self._update_status(f"아직 수집된 블로그 데이터가 없습니다. 수집 시도 중...")

                assistant_response_message = self.llm_handler.chat_with_ollama_for_tools(
                    messages_history,
                    TOOLS_SPEC
                )
                messages_history.append(assistant_response_message)

                if assistant_response_message.get("content"):
                    content = assistant_response_message['content']
                    self._update_status(f"🤖 LLM 응답: {content[:200]}...")  # 너무 길면 잘라서 표시

                tool_calls = assistant_response_message.get("tool_calls")

                # LLM이 tool_calls 대신 content에 JSON 형태로 도구 호출을 반환하는 경우 처리
                if not tool_calls and assistant_response_message.get("content"):
                    content = assistant_response_message['content']
                    logger.info(f"tool_calls가 없습니다. content에서 JSON 형태 도구 호출 검색 중...")
                    logger.debug(f"LLM content (전체): {content}")

                    # 개선된 JSON 파싱 로직 사용
                    def robust_json_parse(json_string):
                        # 1단계: 표준 JSON 파싱
                        try:
                            return json.loads(json_string)
                        except json.JSONDecodeError:
                            pass
                        # 2단계: single quotes를 double quotes로 변환
                        try:
                            json_compatible = json_string.replace("'", '"')
                            return json.loads(json_compatible)
                        except json.JSONDecodeError:
                            pass
                        # 3단계: ast.literal_eval 사용
                        try:
                            import ast
                            return ast.literal_eval(json_string)
                        except (ValueError, SyntaxError):
                            pass
                        # 4단계: 정규식으로 JSON 추출 후 재시도
                        json_pattern = r'(\{[\s\S]*\})'
                        json_match = re.search(json_pattern, json_string)
                        if json_match:
                            json_str_cleaned = json_match.group(1).replace("'", '"')
                            try:
                                return json.loads(json_str_cleaned)
                            except json.JSONDecodeError:
                                pass
                        return None

                    parsed_tool_call_from_content = None
                    content_cleaned_for_json = content.strip()

                    # 1. 마크다운 JSON 블록 시도
                    markdown_match = re.search(r'```json\s*(\{[\s\S]*?\})\s*```', content_cleaned_for_json, re.DOTALL)
                    if markdown_match:
                        json_str_from_content = markdown_match.group(1)
                        logger.info(f"마크다운 JSON 블록에서 내용 추출: {json_str_from_content}")
                        parsed_tool_call_from_content = robust_json_parse(json_str_from_content)
                        if parsed_tool_call_from_content:
                            logger.info(f"마크다운 JSON 블록 파싱 성공: {parsed_tool_call_from_content}")
                        else:
                            logger.error(f"마크다운 JSON 블록 파싱 실패")

                    # 2. 마크다운이 없거나 실패 시, 전체 content가 JSON인지 시도
                    if not parsed_tool_call_from_content and \
                            content_cleaned_for_json.startswith('{'):
                        logger.info(f"전체 content가 JSON 형태일 가능성. 파싱 시도...")
                        parsed_tool_call_from_content = robust_json_parse(content_cleaned_for_json)
                        if parsed_tool_call_from_content:
                            logger.info(f"전체 content JSON 파싱 성공: {type(parsed_tool_call_from_content)}")
                        else:
                            logger.error(f"전체 content JSON 파싱 실패")

                    # 3. JSON이 너무 길어서 잘린 경우 정규식으로 extract_blog_fields_from_text 특별 처리
                    if not parsed_tool_call_from_content and 'extract_blog_fields_from_text' in content:
                        logger.info(f"extract_blog_fields_from_text 도구 감지. 특별 파싱 시도...")
                        # text_content 추출 (큰따옴표 안의 내용)
                        text_match = re.search(r'"text_content"\s*:\s*"([^"]*(?:\\.[^"]*)*)', content)
                        # original_url 추출 - 더 포괄적인 패턴으로 시도
                        url_match = re.search(r'"(?:original_)?url"\s*:\s*"([^"]+)"', content)
                        
                        # 메시지 히스토리에서 최근 웹페이지 URL 찾기
                        recent_url = None
                        for msg in reversed(messages_history):
                            if (msg.get("role") == "tool" and 
                                msg.get("name") == "get_webpage_content_and_interact"):
                                try:
                                    tool_result = json.loads(msg.get("content", "{}"))
                                    if tool_result.get("status") == "success":
                                        recent_url = tool_result.get("url") or tool_result.get("final_url")
                                        break
                                except json.JSONDecodeError:
                                    continue
                        
                        if text_match:
                            text_content = text_match.group(1)
                            # 이스케이프 문자 처리
                            text_content = text_content.replace('\\n', '\n').replace('\\"', '"')
                            # 너무 긴 텍스트는 잘라내기
                            if len(text_content) > 2000:
                                text_content = text_content[:2000] + "...[TRUNCATED]"
                            
                            # URL 우선순위: JSON에서 추출 > 메시지 히스토리 > 기본값
                            if url_match:
                                original_url = url_match.group(1)
                            elif recent_url:
                                original_url = recent_url
                                logger.info(f"메시지 히스토리에서 URL 복구: {original_url}")
                            else:
                                original_url = "unknown_url"
                            
                            parsed_tool_call_from_content = {
                                'name': 'extract_blog_fields_from_text',
                                'parameters': {
                                    'text_content': text_content,
                                    'original_url': original_url
                                }
                            }
                            logger.info(f"extract_blog_fields_from_text 특별 파싱 성공, URL: {original_url}")
                        else:
                            logger.warning(f"extract_blog_fields_from_text 도구는 감지되었으나 text_content 추출 실패")

                    if parsed_tool_call_from_content and \
                            'name' in parsed_tool_call_from_content and \
                            'parameters' in parsed_tool_call_from_content:
                        tool_name_from_content = parsed_tool_call_from_content['name']
                        tool_args_from_content = parsed_tool_call_from_content['parameters']

                        is_valid_tool = any(
                            tool_spec['function']['name'] == tool_name_from_content for tool_spec in TOOLS_SPEC)
                        if is_valid_tool:
                            fake_tool_call = {
                                "id": f"call_from_content_{abs(hash(json.dumps(tool_args_from_content)))}",
                                "type": "function",
                                "function": {
                                    "name": tool_name_from_content,
                                    "arguments": json.dumps(tool_args_from_content)
                                }
                            }
                            tool_calls = [fake_tool_call]  # 생성된 가상 tool_call로 대체
                            logger.info(f"✅ LLM content에서 도구 호출 감지 및 변환 성공: {tool_name_from_content}")
                            self._update_status(f"🔧 LLM content에서 도구 호출 감지: {tool_name_from_content}")
                        else:
                            logger.warning(f"LLM content에서 감지된 도구 '{tool_name_from_content}'가 TOOLS_SPEC에 정의되지 않았습니다.")
                    elif parsed_tool_call_from_content:
                        logger.warning(
                            f"content JSON 파싱은 성공했으나, 'name' 또는 'parameters' 필드가 누락: {parsed_tool_call_from_content}")

                if not tool_calls:  # 위 로직으로도 tool_calls를 만들지 못했다면 종료
                    self._update_status("LLM이 더 이상 도구를 사용하지 않거나 작업을 완료했습니다.")
                    break  # 다음 턴으로 넘어가지 않고 루프 종료

                for tool_call in tool_calls:
                    tool_id = tool_call["id"]
                    tool_function = tool_call["function"]
                    tool_name = tool_function["name"]

                    try:
                        # tool_function["arguments"]는 LLM에서 온 것이므로 문자열로 가정
                        if not isinstance(tool_function["arguments"], str):
                            logger.error(f"도구 '{tool_name}'의 인자가 문자열이 아닙니다: {type(tool_function['arguments'])}")
                            # 방어적으로 문자열로 변환 시도 (LLM이 객체를 직접 줄 경우 대비)
                            tool_args_str = json.dumps(tool_function["arguments"])
                        else:
                            tool_args_str = tool_function["arguments"]
                        tool_args = json.loads(tool_args_str)

                    except json.JSONDecodeError:
                        logger.error(f"도구 '{tool_name}' 인자 JSON 디코딩 실패: {tool_function['arguments']}")
                        tool_result_content = f"오류: 도구 '{tool_name}'의 인자 파싱 실패."
                        messages_history.append({"role": "tool", "tool_call_id": tool_id, "name": tool_name,
                                                 "content": tool_result_content})
                        continue  # 다음 tool_call로 넘어감

                    # 실제 도구 실행
                    tool_result = await self._execute_tool_call(tool_name, tool_args, final_structured_blog_data, messages_history)

                    messages_history.append({
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "name": tool_name,
                        "content": tool_result  # _execute_tool_call은 JSON 문자열을 반환
                    })
                    self._update_status(f"🛠️ 도구 '{tool_name}' 실행 결과 수신.")

                    try:
                        tool_result_obj = json.loads(tool_result)  # tool_result는 JSON 문자열
                    except (json.JSONDecodeError, TypeError):
                        logger.warning(f"도구 '{tool_name}' 결과를 JSON으로 파싱할 수 없습니다. 문자열 그대로 사용.")
                        tool_result_obj = {"status": "unknown", "message": tool_result}

                    # finalize_blog_data_collection 도구 호출 시 데이터 저장 및 종료 처리
                    if tool_name == "finalize_blog_data_collection" and \
                            tool_result_obj.get("status") == "success":
                        self._update_status("LLM이 모든 작업 완료를 확인했습니다. 파이프라인을 종료합니다.")

                        if not final_structured_blog_data and tool_result_obj.get("final_blog_count", 0) > 0:
                            logger.warning("LLM은 데이터가 있다고 보고했으나, 내부 리스트는 비어있습니다. 이전 단계 확인 필요.")

                        # final_structured_blog_data에 실제로 데이터가 있는지 확인 후 저장
                        if final_structured_blog_data:
                            self._update_status(f"✅ 총 {len(final_structured_blog_data)}개의 블로그 데이터를 저장합니다.")
                            output_filepath = self.data_writer.save_data(
                                final_structured_blog_data,
                                "agent_blog_data"  # 파일명 접두사
                            )
                            self._update_status(f"✅ 최종 데이터 저장 완료: {output_filepath}")
                            await self.browser_controller._maybe_close_browser(force_close=True)
                            return output_filepath  # 성공적으로 파일 저장 후 종료
                        else:
                            self._update_status("⚠️ 수집된 블로그 데이터가 없어 파일을 저장하지 않습니다.")
                            await self.browser_controller._maybe_close_browser(force_close=True)
                            return None  # 저장할 데이터가 없으므로 None 반환

            # 최대 턴 도달 시
            self._update_status(f"최대 작업 턴({max_turns})에 도달했습니다. 현재까지의 정보로 마무리합니다.")
            # 데이터 복구 로직은 final_structured_blog_data가 비어있을 때만 작동하도록 finally 블록 이후로 이동

        except RuntimeError as e_browser_runtime:  # 브라우저 초기화/설치 관련 에러
            logger.error(f"브라우저 관련 심각한 오류 발생: {e_browser_runtime}", exc_info=True)
            self._update_status(
                f"❌ 브라우저 오류: {e_browser_runtime}. Playwright가 올바르게 설치되었는지 확인하세요 (예: python -m playwright install).")
            return None  # 치명적 오류로 간주하고 None 반환
        except Exception as e:
            logger.error(f"에이전트 실행 중 예기치 않은 오류 발생: {e}", exc_info=True)
            self._update_status(f"❌ 에이전트 오류: {e}")
            self._update_status(f"오류 상세 정보 (디버깅용): {traceback.format_exc()[:1000]}")  # 너무 길지 않게 자름
            # 예외 발생 시에도 finally 블록은 실행됨

        finally:
            # 모든 작업(성공, 예외, 최대 턴 도달) 후 브라우저 확실히 닫기
            await self.browser_controller._maybe_close_browser(force_close=True)
            self._update_status("에이전트 파이프라인 종료.")

        # 루프 정상 종료(break) 또는 최대 턴 도달 시, 또는 예외 발생 후 finally를 거쳐 이 부분 실행
        # 데이터가 있는 경우, 부분 저장 시도
        if final_structured_blog_data:
            output_filepath = self.data_writer.save_data(final_structured_blog_data, "agent_blog_data_partial")
            self._update_status(f" 부분 데이터 저장 (파이프라인 종료): {output_filepath}")
            return output_filepath
        else:  # 데이터가 전혀 없는 경우 (finalize가 호출되지 않았거나, 호출되었어도 데이터가 없었거나, 중간에 오류)
            # 추가된 부분: 데이터가 비었지만 LLM이 이전에 URL을 찾았는지 확인
            if not final_structured_blog_data:  # 다시 한번 확인 (위에서 저장했을 수도 있으므로)
                self._update_status("최종 데이터가 비어 있습니다. 메시지 히스토리에서 URL 검색 시도...")
                urls_found_in_history = set()
                for msg in messages_history:
                    if msg.get("role") == "tool" and msg.get("name") == "search_web_for_blogs":
                        try:
                            search_tool_result_content = msg.get("content", "{}")
                            search_tool_result = json.loads(search_tool_result_content)
                            if search_tool_result.get("status") == "success" and search_tool_result.get("found_urls"):
                                urls_found_in_history.update(search_tool_result.get("found_urls", []))
                        except (json.JSONDecodeError, TypeError):
                            logger.warning(f"메시지 히스토리의 search_web_for_blogs 결과 파싱 실패: {msg.get('content')}")

                if urls_found_in_history:
                    self._update_status(
                        f"{len(urls_found_in_history)}개의 URL이 검색되었으나 완전한 데이터 추출은 실패했습니다. URL만이라도 저장합니다.")
                    for url_item in urls_found_in_history:
                        final_structured_blog_data.append({
                            "blog_name": "추출 실패 - URL만 확보",
                            "url": url_item,
                            "blog_id": "extraction-failed-url-only",
                            "post_title": "N/A",
                            "recent_post_date": "N/A",
                            "total_posts": "N/A"
                        })
                    if final_structured_blog_data:  # URL 정보라도 있다면 저장
                        output_filepath = self.data_writer.save_data(final_structured_blog_data,
                                                                     "agent_blog_data_urls_only")
                        self._update_status(f" URL 정보만 저장 완료: {output_filepath}")
                        return output_filepath

        return None  # 모든 경우에 해당하지 않으면 None 반환