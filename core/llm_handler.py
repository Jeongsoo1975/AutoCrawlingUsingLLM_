# core/llm_handler_fixed.py
import ollama
from config import settings
import json
import logging
import uuid
from utils.error_handler import (
    LLMConnectionError, handle_async_errors, 
    ErrorRecovery, log_async_function_call
)

logger = logging.getLogger(__name__)


class LLMHandler:
    def __init__(self):
        self.model_name = settings.LLM_MODEL_NAME
        self.client = ollama.Client(host=settings.OLLAMA_HOST)
        try:
            self.client.list()
            logger.info(
                f"LLMHandler: Successfully connected to Ollama host: {settings.OLLAMA_HOST} with model: {self.model_name}")
        except Exception as e:
            logger.error(f"LLMHandler: Failed to connect to Ollama. Error: {e}")
            raise LLMConnectionError(f"Failed to connect to Ollama: {e}")

    @ErrorRecovery.retry_with_backoff(max_retries=2, backoff_factor=1.0)
    @log_async_function_call
    async def chat_completion(self, messages: list):
        """간단한 채팅 완성 메서드 (도구 호출 없음)"""
        try:
            response = self.client.chat(
                model=self.model_name,
                messages=messages,
                stream=False,
                options={
                    "temperature": settings.LLM_TEMPERATURE,
                    "num_ctx": settings.LLM_NUM_CTX,
                }
            )
            
            message = response.get("message", {})
            content = message.get("content", "")
            
            if not content:
                logger.warning("LLM returned empty content")
                return "LLM 응답이 비어있습니다."
            
            return content
            
        except ollama.ResponseError as e:
            logger.error(f"Ollama ResponseError: {e}")
            raise LLMConnectionError(f"Ollama 서버 오류: {e}")
        except Exception as e:
            logger.error(f"LLM chat_completion 오류: {e}", exc_info=True)
            return None

    def chat_with_ollama_for_tools(self, messages_history: list, available_tools_spec: list):
        """오류 처리가 개선된 Ollama와 통신을 위한 메서드"""
        logger.debug(f"LLM <--- 전송 메시지 수: {len(messages_history)}, 사용 가능 도구 수: {len(available_tools_spec)}")
        
        # Ollama에 전달하기 전에 tool_calls의 arguments를 JSON 객체로 변환
        processed_messages = []
        for msg in messages_history:
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                processed_msg = msg.copy()
                processed_tool_calls = []
                for tool_call in msg["tool_calls"]:
                    processed_tool_call = tool_call.copy()
                    if "function" in processed_tool_call and "arguments" in processed_tool_call["function"]:
                        args_str = processed_tool_call["function"]["arguments"]
                        if isinstance(args_str, str):
                            try:
                                processed_tool_call["function"]["arguments"] = json.loads(args_str)
                            except json.JSONDecodeError:
                                logger.warning(f"Failed to parse tool arguments: {args_str}")
                                processed_tool_call["function"]["arguments"] = {}
                    processed_tool_calls.append(processed_tool_call)
                processed_msg["tool_calls"] = processed_tool_calls
                processed_messages.append(processed_msg)
            else:
                processed_messages.append(msg)
        
        try:
            # Gemma3-Tools에 최적화된 옵션 설정
            data = {
                "model": self.model_name,
                "messages": processed_messages,
                "stream": False,
                "options": {
                    "temperature": settings.LLM_TEMPERATURE,
                    "num_ctx": settings.LLM_NUM_CTX,
                    "num_predict": getattr(settings, 'LLM_MAX_TOKENS', 4096),
                    "top_p": getattr(settings, 'LLM_TOP_P', 0.9),
                    "repeat_penalty": getattr(settings, 'LLM_REPEAT_PENALTY', 1.1),
                    "seed": 42,  # 재현 가능한 결과를 위한 시드
                }
            }
            if available_tools_spec:
                data["tools"] = available_tools_spec

            response = self.client.chat(**data)

            raw_response_message = response.get("message", {})
            logger.debug(f"LLM ---> 수신 메시지: {raw_response_message}")

            # OpenAI SDK와 유사한 응답 객체로 변환 (tool_calls 포함)
            text_content = raw_response_message.get("content", "")
            ollama_tool_calls = raw_response_message.get("tool_calls")

            parsed_tool_calls = []
            if ollama_tool_calls:
                logger.info(f"LLM이 {len(ollama_tool_calls)}개의 도구 호출을 제안했습니다.")
                for tc in ollama_tool_calls:
                    function_info = tc.get("function", {})
                    func_name = function_info.get("name")
                    func_args_raw = function_info.get("arguments")

                    if func_name and func_args_raw is not None:
                        try:
                            # Ollama는 arguments를 이미 dict로 줄 수 있음. 문자열이면 파싱.
                            if isinstance(func_args_raw, str):
                                func_args_parsed = json.loads(func_args_raw)
                            elif isinstance(func_args_raw, dict):
                                func_args_parsed = func_args_raw
                            else:
                                func_args_parsed = {}
                        except json.JSONDecodeError as e:
                            logger.error(f"도구 '{func_name}' 인자 JSON 파싱 실패: {func_args_raw}. 오류: {e}")
                            func_args_parsed = {"error_parsing_args": func_args_raw}

                        parsed_tool_calls.append({
                            "id": f"call_{uuid.uuid4().hex[:8]}",
                            "type": "function",
                            "function": {
                                "name": func_name,
                                "arguments": json.dumps(func_args_parsed)
                            }
                        })

            # 어시스턴트 메시지 객체 구성 (OpenAI 호환 형식)
            assistant_message = {"role": "assistant", "content": text_content if text_content else None}
            if parsed_tool_calls:
                assistant_message["tool_calls"] = parsed_tool_calls

            return assistant_message

        except ollama.ResponseError as e:
            logger.error(f"Ollama ResponseError 발생: {e}")
            return {"role": "assistant", "content": f"오류: Ollama 서버 응답 오류 ({e})"}
        except json.JSONDecodeError as e:
            logger.error(f"JSON 파싱 오류: {e}", exc_info=True)
            return {"role": "assistant", "content": f"오류: 응답 데이터 파싱 실패 ({e})"}
        except Exception as e:
            logger.error(f"Ollama API 통신 중 오류 발생: {e}", exc_info=True)
            return {"role": "assistant", "content": f"오류: LLM 통신 중 문제가 발생했습니다. ({type(e).__name__})"}
