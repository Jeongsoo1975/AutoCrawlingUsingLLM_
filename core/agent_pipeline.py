import json
import logging
import asyncio
import traceback
from typing import List, Dict, Any, Optional, Callable

from core.browser_controller import BrowserController
from core.web_searcher import WebSearcher
from core.data_extractor import DataExtractor
from core.ollama_handler import OllamaHandler
import settings

logger = logging.getLogger(__name__)

def get_browser_instance():
    """싱글턴 브라우저 컨트롤러 인스턴스를 반환합니다."""
    if not hasattr(get_browser_instance, "_instance") or get_browser_instance._instance is None:
        get_browser_instance._instance = BrowserController()
    return get_browser_instance._instance

async def extract_web_content(url: str, task_description: str) -> dict:
    """
    웹페이지의 내용을 추출합니다.
    
    Args:
        url: 웹페이지 URL
        task_description: 추출 작업에 대한 설명
        
    Returns:
        추출된 내용과 메타데이터를 포함하는 딕셔너리
    """
    logger.info(f"Extracting content from {url}")
    try:
        browser = get_browser_instance()
        result = await browser.browse_website(
            url=url,
            action="extract_text",  # 명시적으로 텍스트 추출 액션 지정
            close_browser=False  # 브라우저를 계속 재사용
        )
        
        # 브라우징 결과가 성공적인지 확인
        if result.get("status") != "success":
            error_msg = result.get("error_message", "Unknown error")
            logger.error(f"Failed to extract content: {error_msg}")
            return {
                "success": False, 
                "error": f"브라우징 실패: {error_msg}", 
                "content": None,
                "url": url,
                "title": result.get("page_title", "")
            }
        
        # 텍스트 내용이 있는지 확인
        content = result.get("data", {}).get("text_content", "")
        if not content.strip():
            logger.warning(f"No text content extracted from {url}")
            # 일반 콘텐츠 추출 시도
            result = await browser.browse_website(
                url=url,
                action=None,  # 기본 get_content 액션 사용
                close_browser=False
            )
            content = result.get("data", {}).get("text_content", "")
            
        # 여전히 내용이 없으면 실패로 처리
        if not content.strip():
            logger.error(f"Failed to extract any content from {url}")
            return {
                "success": False, 
                "error": "추출된 내용이 없습니다", 
                "content": None,
                "url": url,
                "title": result.get("page_title", "")
            }
            
        # 성공적으로 내용을 추출한 경우
        return {
            "success": True,
            "content": content,
            "url": result.get("final_url", url),
            "title": result.get("page_title", ""),
            "extracted_with": result.get("data", {}).get("used_selector", "default")
        }
            
    except Exception as e:
        logger.exception(f"Error extracting content from {url}: {e}")
        return {
            "success": False,
            "error": f"추출 오류: {str(e)}",
            "content": None,
            "url": url,
            "title": ""
        }

class AgentPipeline:
    def __init__(self, streamlit_status_callback=None):
        self.web_searcher = WebSearcher()
        self.browser_controller = get_browser_instance()
        self.data_extractor = DataExtractor()
        self.llm_handler = OllamaHandler()
        # 상태 업데이트를 위한 콜백 함수
        self._status_callback = streamlit_status_callback

    def _update_status(self, message: str):
        """상태 메시지를 업데이트합니다. Streamlit UI나 로그에 표시됩니다."""
        logger.info(message)
        if self._status_callback:
            self._status_callback(message)

    async def _execute_tool_call(self, tool_name: str, tool_args: dict, collected_data_for_all_blogs: list):
        """LLM이 요청한 도구를 실행합니다."""
        self._update_status(f"🛠️ 도구 실행 중: {tool_name} (인자: {tool_args})")

        if tool_name == "search_web_for_blogs":
            keyword = tool_args.get("keyword")
            if not keyword: 
                return json.dumps({
                    "status": "error",
                    "message": "search_web_for_blogs 도구에 'keyword' 인자가 필요합니다."
                })
                
            search_results = self.web_searcher.search_links(keyword)  # 동기 함수
            urls = [res["url"] for res in search_results if res.get("url")]
            
            return json.dumps({
                "status": "success",
                "found_urls": urls,
                "summary": f"{len(urls)}개의 잠재적 블로그 URL을 찾았습니다."
            })

        elif tool_name == "get_webpage_content_and_interact":
            url = tool_args.get("url")
            fields_to_extract = tool_args.get("fields_to_extract", settings.DATA_FIELDS_TO_EXTRACT)  # 기본 필드 사용
            action_details = tool_args.get("action_details")  # 선택 사항

            if not url:
                return json.dumps({
                    "status": "error",
                    "message": "get_webpage_content_and_interact 도구에 'url' 인자가 필요합니다."
                })

            # LLM이 요청한 필드 + 기본 정보를 추출하도록 구성
            self._update_status(f"🌐 웹사이트 방문 및 원시 데이터 수집 시도: {url}")

            # BrowserController는 이제 표준화된 딕셔너리를 반환함
            action_type = None
            selector = None
            input_text = None
            
            if action_details:
                action_type = action_details.get("action_type")
                selector = action_details.get("selector")
                input_text = action_details.get("input_text")

            raw_result = await self.browser_controller.browse_website(
                url=url,
                action=action_type,
                selector=selector,
                input_text=input_text,
                # close_browser=False # 루프 내에서는 브라우저 유지
            )
            
            if raw_result["status"] == "success":
                self._update_status(f"📄 '{url}' 에서 웹페이지 내용 수신 완료.")
                
                # 추출된 텍스트 또는 액션 결과 포함
                result = {
                    "status": "success",
                    "url": url,
                    "final_url": raw_result["final_url"],
                    "page_title": raw_result["page_title"],
                    "action_performed": raw_result["action_performed"],
                    "requested_fields": fields_to_extract,
                }
                
                # 텍스트 내용이 있으면 포함
                if "text_content" in raw_result["data"]:
                    result["text_content"] = raw_result["data"]["text_content"]
                # 메시지가 있으면 포함
                elif "message" in raw_result["data"]:
                    result["message"] = raw_result["data"]["message"]
                
                return json.dumps(result)
            else:
                self._update_status(f"⚠️ '{url}' 접근 중 오류 발생: {raw_result['error_message']}")
                return json.dumps({
                    "status": "error",
                    "url": url,
                    "message": f"웹사이트 접근 실패: {raw_result['error_message']}"
                })

        elif tool_name == "extract_blog_fields_from_text":
            text_content = tool_args.get("text_content")
            original_url = tool_args.get("original_url")
            
            if not text_content or not original_url:
                return json.dumps({
                    "status": "error",
                    "message": "extract_blog_fields_from_text 도구에 'text_content'와 'original_url' 인자가 필요합니다."
                })

            self._update_status(f"✍️ '{original_url}'의 텍스트에서 정보 추출 시도 (LLM 호출)...")
            
            # LLM에게 특정 필드 추출을 위한 명확한 프롬프트 구성
            extraction_system_prompt = (
                f"You are an expert data extractor. From the following text content, "
                f"which was obtained from the URL '{original_url}', "
                f"extract these specific fields: {', '.join(settings.DATA_FIELDS_TO_EXTRACT)}. "
                f"Return your findings as a single, well-formed JSON object where keys are the field names. "
                f"If a field's value cannot be found in the text, use the string 'Not Found' as its value. "
                f"For dates, try to use YYYY-MM-DD format if possible, otherwise keep the original format. "
                f"For 'average_visitors', if specific numbers are not present, record any textual hints found (e.g., 'thousands of readers monthly')."
            )
            extraction_user_prompt = text_content

            extraction_messages = [
                {"role": "system", "content": extraction_system_prompt},
                {"role": "user", "content": extraction_user_prompt}
            ]
            
            # LLM 호출 (JSON 형식 응답 요청)
            llm_response = self.llm_handler.chat_with_ollama_for_tools(
                 extraction_messages,
                 [] # 도구 없이 텍스트 생성만 요청
            )
            extracted_json_string = llm_response.get("content", "{}")
            logger.debug(f"LLM extraction response for {original_url}: {extracted_json_string}")

            try:
                # LLM이 반환한 JSON 문자열 파싱 시도
                # JSON 문자열이 실제 JSON 객체를 포함하지만 다른 텍스트와 함께 있을 수 있음
                # 가장 바깥쪽 중괄호({})만 추출하여 파싱 시도
                import re
                
                # JSON 객체 추출 시도
                json_pattern = r'(\{[\s\S]*\})'
                json_match = re.search(json_pattern, extracted_json_string)
                
                if json_match:
                    json_str_cleaned = json_match.group(1)
                    try:
                        extracted_info_dict = json.loads(json_str_cleaned)
                    except json.JSONDecodeError:
                        # 중괄호 안의 내용을 추출했지만 여전히 파싱할 수 없는 경우
                        logger.warning(f"정규식으로 추출한 JSON도 파싱 실패: {json_str_cleaned}")
                        # 원본 문자열로 다시 시도
                        extracted_info_dict = json.loads(extracted_json_string)
                else:
                    # 정규식으로 JSON 객체를 찾지 못한 경우 원본 문자열로 시도
                    extracted_info_dict = json.loads(extracted_json_string)
                
                # DataExtractor를 사용하여 최종 데이터 구조화 및 리스트에 추가
                structured_blog_info = self.data_extractor.structure_blog_info(extracted_info_dict, original_url)
                collected_data_for_all_blogs.append(structured_blog_info) # 이 부분이 중요: 구조화된 데이터 저장
                
                self._update_status(f"✅ 정보 추출 및 저장 완료: {original_url} -> {structured_blog_info.get('blog_name', 'Unknown')}")
                
                return json.dumps({
                    "status": "success",
                    "message": f"'{original_url}'에서 '{structured_blog_info.get('blog_name', 'Unknown')}' 정보를 성공적으로 추출했습니다.",
                    "extracted_fields": structured_blog_info
                })
            except Exception as e:
                logger.error(f"JSON 파싱 또는 데이터 구조화 오류: {str(e)}", exc_info=True)
                self._update_status(f"⚠️ JSON 파싱 오류: {str(e)}")
                return json.dumps({
                    "status": "error",
                    "message": f"추출된 정보를 JSON으로 파싱할 수 없습니다: {str(e)}",
                    "raw_text": extracted_json_string[:200] + "..." if len(extracted_json_string) > 200 else extracted_json_string
                })
        else:
            logger.warning(f"지원하지 않는 도구: {tool_name}")
            return json.dumps({
                "status": "error",
                "message": f"알 수 없는 도구: {tool_name}"
            })

    async def run_agent_for_keywords(self, initial_keywords: list):
        self._update_status("에이전트 파이프라인 시작...")
        
        # 수집된 모든 블로그 데이터를 저장할 리스트
        collected_data_for_all_blogs = []
        
        # 시스템 프롬프트 구성
        system_prompt = f"""You are an expert blog researcher assistant who specializes in finding and extracting information from blogs.
Your task is to search for blogs related to given keywords, visit their websites, and extract specific information.

Follow this systematic process:
1. Search for blogs related to the given keywords using the search_web_for_blogs tool.
2. For each promising blog URL found:
   a. Visit the website using get_webpage_content_and_interact
   b. Extract the text content from the page
   c. Use the extract_blog_fields_from_text tool to analyze the text and extract these specific fields:
      {', '.join(settings.DATA_FIELDS_TO_EXTRACT)}

Important guidelines:
- Focus on blogs that clearly belong to individual bloggers or small businesses, not large corporate/news sites.
- Visit at least 3-5 different blogs to gather diverse information.
- If a page doesn't clearly contain blog information, move on to another URL.
- Ensure all extracted data is stored properly by confirming the success status of tool responses.
- If some fields cannot be found for a blog, it's okay to proceed with partial information.

You have access to these tools:
- search_web_for_blogs: Find relevant blog URLs based on keywords
- get_webpage_content_and_interact: Visit websites and extract their content
- extract_blog_fields_from_text: Analyze text to extract specific blog information fields

After completing the research, provide a summary of how many blog details you successfully collected and any challenges encountered.
"""

        messages_history = [{"role": "system", "content": system_prompt}]

        # 초기 사용자 메시지 (키워드 전달)
        user_query = f"다음 키워드에 대한 블로그 정보를 수집해주세요: {', '.join(initial_keywords)}. 각 블로그에서 {', '.join(settings.DATA_FIELDS_TO_EXTRACT)} 정보를 추출해야 합니다."
        messages_history.append({"role": "user", "content": user_query})

        max_turns = settings.AGENT_MAX_TURNS  # 예: 10-15회, 설정 파일에 추가 필요

        try:
            try:
                await self.browser_controller._ensure_browser()  # 파이프라인 시작 시 브라우저 한번 켬
                self._update_status("🌐 브라우저 초기화 완료.")
            except RuntimeError as e_browser:
                self._update_status(f"⚠️ 브라우저 초기화 실패: {e_browser}")
                # 목표: 시스템이 브라우저 문제에도 불구하고 계속 작동하도록
                # 여기서는 일단 계속 진행 (나중에 각 작업에서 브라우저 재초기화 시도)
            
            # 에이전트 루프 시작
            turn = 0
            agent_complete = False
            
            while not agent_complete and turn < max_turns:
                turn += 1
                self._update_status(f"🔄 에이전트 턴 #{turn}/{max_turns} 실행 중...")
                
                # LLM 호출
                tools_for_llm = settings.get_tools_for_ollama()
                
                try:
                    llm_response = self.llm_handler.chat_with_ollama_for_tools(messages_history, tools_for_llm)
                except Exception as e_llm:
                    logger.error(f"LLM 호출 오류: {e_llm}", exc_info=True)
                    self._update_status(f"❌ LLM 호출 실패: {e_llm}")
                    # 에러 메시지를 출력하고 다음 턴으로 진행
                    messages_history.append({
                        "role": "assistant",
                        "content": f"죄송합니다, 오류가 발생했습니다: {e_llm}. 다시 시도하겠습니다."
                    })
                    continue
                
                # 도구 사용 요청을 확인
                if "tool_calls" in llm_response and llm_response["tool_calls"]:
                    tool_calls = llm_response["tool_calls"]
                    self._update_status(f"🧰 LLM이 도구 사용 요청: {len(tool_calls)}개")
                    
                    # LLM의 생각/계획을 메시지 히스토리에 추가
                    if "content" in llm_response and llm_response["content"]:
                        messages_history.append({
                            "role": "assistant", 
                            "content": llm_response["content"],
                            "tool_calls": [
                                {
                                    "id": tc["id"],
                                    "type": "function",
                                    "function": {"name": tc["function"]["name"], "arguments": tc["function"]["arguments"]}
                                }
                                for tc in tool_calls
                            ]
                        })
                    
                    # 모든 도구 호출 처리
                    for tool_call in tool_calls:
                        try:
                            # 도구 이름과 인자 추출
                            tool_name = tool_call["function"]["name"]
                            tool_args_str = tool_call["function"]["arguments"]
                            
                            try:
                                # JSON 문자열을 파이썬 딕셔너리로 변환
                                tool_args = json.loads(tool_args_str) if tool_args_str else {}
                            except json.JSONDecodeError:
                                logger.warning(f"도구 인자 파싱 실패: {tool_args_str}")
                                tool_args = {"error": "Invalid JSON arguments", "raw_args": tool_args_str}
                            
                            # 도구 실행
                            tool_result = await self._execute_tool_call(
                                tool_name, tool_args, collected_data_for_all_blogs
                            )
                            
                            # 도구 결과를 메시지 히스토리에 추가
                            messages_history.append({
                                "role": "tool",
                                "tool_call_id": tool_call["id"],
                                "name": tool_name,
                                "content": tool_result
                            })
                            
                        except Exception as e_tool:
                            logger.error(f"도구 호출 처리 중 오류: {e_tool}", exc_info=True)
                            self._update_status(f"⚠️ 도구 호출 오류: {e_tool}")
                            
                            # 오류 메시지를 메시지 히스토리에 추가
                            messages_history.append({
                                "role": "tool",
                                "tool_call_id": tool_call["id"],
                                "name": tool_call["function"]["name"],
                                "content": json.dumps({
                                    "status": "error",
                                    "message": f"도구 호출 중 오류: {str(e_tool)}"
                                })
                            })
                
                else:
                    # 최종 요약 응답 (작업 완료 표시)
                    if "content" in llm_response and llm_response["content"]:
                        messages_history.append({
                            "role": "assistant",
                            "content": llm_response["content"]
                        })
                        
                        # 특정 키워드로 완료 여부 판단 (예를 들어, "정보 수집 완료", "작업 끝" 등)
                        completion_signals = ["수집 완료", "작업 완료", "정보 수집을 마쳤습니다", 
                                             "모든 블로그", "successfully collected", "completed the research"]
                        if any(signal in llm_response["content"].lower() for signal in completion_signals):
                            agent_complete = True
                            self._update_status("🏁 에이전트가 작업 완료 신호를 보냈습니다.")
                
                # 수집된 데이터가 충분히 많으면 조기 종료 (예: 5개 이상의 블로그 정보)
                if len(collected_data_for_all_blogs) >= settings.MINIMUM_BLOGS_TO_COLLECT:
                    self._update_status(f"✅ 충분한 블로그 정보 수집됨 ({len(collected_data_for_all_blogs)}개)")
                    if not agent_complete:  # 아직 에이전트가 완료 신호를 보내지 않은 경우
                        messages_history.append({
                            "role": "user",
                            "content": "충분한 정보가 수집되었습니다. 작업을 마무리하고 수집한 내용을 요약해주세요."
                        })
                        # 한 번 더 LLM 호출하여 요약 얻기
                        try:
                            summary_response = self.llm_handler.chat_with_ollama_for_tools(
                                messages_history, []  # 도구 없이 텍스트 생성만 요청
                            )
                            if "content" in summary_response and summary_response["content"]:
                                messages_history.append({
                                    "role": "assistant",
                                    "content": summary_response["content"]
                                })
                        except Exception as e_summary:
                            logger.warning(f"요약 생성 중 오류: {e_summary}")
                        
                        agent_complete = True
            
            # 에이전트 루프 종료 후
            if agent_complete:
                self._update_status(f"🎉 에이전트 작업 완료! 수집된 블로그 정보: {len(collected_data_for_all_blogs)}개")
            else:
                self._update_status(f"⚠️ 최대 턴 수({max_turns}) 도달. 현재까지 수집된 블로그 정보: {len(collected_data_for_all_blogs)}개")
            
            # 최종 결과 반환
            final_structured_blog_data = collected_data_for_all_blogs
            
            # 대화 히스토리에서 마지막 어시스턴트 메시지 추출 (요약 용도)
            last_assistant_message = ""
            for msg in reversed(messages_history):
                if msg.get("role") == "assistant" and "content" in msg and msg["content"]:
                    last_assistant_message = msg["content"]
                    break

            # 추가된 부분: 데이터가 비었지만 LLM이 충분한 정보를 전달했는지 확인
            if not final_structured_blog_data:
                self._update_status("데이터가 비어 있습니다. 메시지 히스토리에서 유용한 정보를 검색합니다...")
                # 가능한 URL 목록 추출
                urls_found = set()
                for msg in messages_history:
                    if msg.get("role") == "tool" and msg.get("name") == "search_web_for_blogs":
                        try:
                            search_result = json.loads(msg.get("content", "{}"))
                            if search_result.get("found_urls"):
                                urls_found.update(search_result.get("found_urls", []))
                        except:
                            pass
                
                if urls_found:
                    self._update_status(f"{len(urls_found)}개의 URL이 검색되었지만 데이터 추출은 실패했습니다.")
                    # 단순 URL 정보라도 저장
                    for url in urls_found:
                        simple_data = {
                            "blog_name": "추출 실패",
                            "url": url,
                            "blog_id": "extraction-failed",
                            "recent_post_date": "Not extracted",
                            "total_posts": "Unknown"
                        }
                        final_structured_blog_data.append(simple_data)

        except Exception as e:
            logger.error(f"에이전트 실행 중 오류 발생: {e}", exc_info=True)
            self._update_status(f"❌ 에이전트 오류: {e}")
            
            # 오류 상세 정보 로깅
            import traceback
            self._update_status("오류 상세 정보 (디버깅용):")
            self._update_status(traceback.format_exc()[:1000])  # 너무 길지 않게 자름
            
            return {
                "success": False,
                "error": str(e),
                "data": collected_data_for_all_blogs if 'collected_data_for_all_blogs' in locals() else [],
                "message_history": messages_history if 'messages_history' in locals() else [],
                "summary": f"오류 발생: {str(e)}"
            }
        finally:
            # 브라우저 리소스 정리 시도
            try:
                await self.browser_controller.close_all_resources()
                self._update_status("🧹 브라우저 리소스 정리됨")
            except Exception as e_close:
                logger.error(f"브라우저 리소스 정리 중 오류: {e_close}")
        
        # 최종 결과 반환
        return {
            "success": True,
            "data": final_structured_blog_data,
            "message_history": messages_history,
            "summary": last_assistant_message if 'last_assistant_message' in locals() else "작업 완료"
        } 