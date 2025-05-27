# core/browser_controller.py
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading
import time

logger = logging.getLogger(__name__)


class BrowserController:
    def __init__(self):
        self.driver = None
        self._browser_instance_user_count = 0
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1)
        logger.info("BrowserController (Selenium) initialized.")
        
    async def _ensure_browser(self):
        """브라우저 인스턴스가 준비되었는지 확인하고, 없으면 시작합니다."""
        with self._lock:
            self._browser_instance_user_count += 1
            if self.driver is None:
                logger.info("Launching new Selenium Chrome browser instance...")
                try:
                    # 비동기 코드에서 드라이버 초기화를 별도 스레드에서 실행
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(self._executor, self._init_selenium_driver)
                    logger.info("Selenium Chrome browser launched successfully.")
                except Exception as e:
                    logger.error(f"Selenium browser launch failed: {e}")
                    self._browser_instance_user_count -= 1
                    raise RuntimeError(f"브라우저를 시작할 수 없습니다: {str(e)}")
            else:
                logger.info("Reusing existing Selenium browser instance.")
                
    def _init_selenium_driver(self):
        """Selenium WebDriver를 초기화합니다."""
        try:
            # Edge 브라우저 시도 (Windows에 기본 설치됨)
            try:
                from selenium.webdriver.edge.service import Service as EdgeService
                from selenium.webdriver.edge.options import Options as EdgeOptions
                from webdriver_manager.microsoft import EdgeChromiumDriverManager
                
                options = EdgeOptions()
                # GPU 및 WebGL 관련 오류 해결을 위한 옵션들
                options.add_argument("--headless")  # 헤드리스 모드
                options.add_argument("--no-sandbox")
                options.add_argument("--disable-dev-shm-usage")
                options.add_argument("--disable-gpu")  # GPU 비활성화
                options.add_argument("--disable-software-rasterizer")  # 소프트웨어 래스터라이저 비활성화
                options.add_argument("--disable-webgl")  # WebGL 비활성화
                options.add_argument("--disable-webgl2")  # WebGL2 비활성화
                options.add_argument("--disable-3d-apis")  # 3D API 비활성화
                options.add_argument("--disable-accelerated-2d-canvas")  # 하드웨어 가속 2D 캔버스 비활성화
                options.add_argument("--disable-accelerated-video-decode")  # 하드웨어 가속 비디오 디코딩 비활성화
                options.add_argument("--use-gl=swiftshader")  # SwiftShader 사용 (소프트웨어 렌더링)
                options.add_argument("--enable-unsafe-swiftshader")  # 안전하지 않은 SwiftShader 허용
                options.add_argument("--disable-background-timer-throttling")  # 백그라운드 타이머 스로틀링 비활성화
                options.add_argument("--disable-renderer-backgrounding")  # 렌더러 백그라운딩 비활성화
                options.add_argument("--disable-backgrounding-occluded-windows")  # 가려진 윈도우 백그라운딩 비활성화
                options.add_argument("--window-size=1920,1080")
                options.add_argument("--log-level=3")  # 로그 레벨 최소화 (ERROR만)
                options.add_argument("--silent")  # 추가 로그 억제
                options.add_argument("--disable-logging")  # 로깅 비활성화
                options.add_argument("--disable-gpu-sandbox")  # GPU 샌드박스 비활성화
                options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
                
                # 최신 Edge WebDriver를 자동으로 설치
                self.driver = webdriver.Edge(service=EdgeService(EdgeChromiumDriverManager().install()), options=options)
                self.driver.set_page_load_timeout(30)  # 페이지 로드 타임아웃 설정
                logger.info("Edge WebDriver initialized successfully.")
                return True
            except Exception as edge_error:
                logger.warning(f"Edge WebDriver initialization failed: {edge_error}")
                
                # Chrome 브라우저 대체 시도
                options = Options()
                # GPU 및 WebGL 관련 오류 해결을 위한 옵션들
                options.add_argument("--headless")  # 헤드리스 모드
                options.add_argument("--no-sandbox")
                options.add_argument("--disable-dev-shm-usage")
                options.add_argument("--disable-gpu")  # GPU 비활성화
                options.add_argument("--disable-software-rasterizer")  # 소프트웨어 래스터라이저 비활성화
                options.add_argument("--disable-webgl")  # WebGL 비활성화
                options.add_argument("--disable-webgl2")  # WebGL2 비활성화
                options.add_argument("--disable-3d-apis")  # 3D API 비활성화
                options.add_argument("--disable-accelerated-2d-canvas")  # 하드웨어 가속 2D 캔버스 비활성화
                options.add_argument("--disable-accelerated-video-decode")  # 하드웨어 가속 비디오 디코딩 비활성화
                options.add_argument("--use-gl=swiftshader")  # SwiftShader 사용 (소프트웨어 렌더링)
                options.add_argument("--enable-unsafe-swiftshader")  # 안전하지 않은 SwiftShader 허용
                options.add_argument("--disable-background-timer-throttling")  # 백그라운드 타이머 스로틀링 비활성화
                options.add_argument("--disable-renderer-backgrounding")  # 렌더러 백그라운딩 비활성화
                options.add_argument("--disable-backgrounding-occluded-windows")  # 가려진 윈도우 백그라운딩 비활성화
                options.add_argument("--window-size=1920,1080")
                options.add_argument("--log-level=3")  # 로그 레벨 최소화 (ERROR만)
                options.add_argument("--silent")  # 추가 로그 억제
                options.add_argument("--disable-logging")  # 로깅 비활성화
                options.add_argument("--disable-gpu-sandbox")  # GPU 샌드박스 비활성화
                options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
                
                # 최신 ChromeDriver를 자동으로 설치
                self.driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
                self.driver.set_page_load_timeout(30)  # 페이지 로드 타임아웃 설정
                logger.info("Chrome WebDriver initialized successfully.")
                return True
                
        except Exception as e:
            logger.error(f"Selenium driver initialization error: {e}")
            raise RuntimeError(f"Selenium WebDriver 초기화 실패: {e}")

    async def _maybe_close_browser(self, force_close: bool = False):
        """브라우저 사용 카운트를 줄이고, 더 이상 사용되지 않으면 닫습니다."""
        with self._lock:
            self._browser_instance_user_count -= 1
            if force_close or (self._browser_instance_user_count <= 0 and self.driver):
                logger.info("Closing Selenium browser instance...")
                try:
                    # 비동기 코드에서 드라이버 종료를 별도 스레드에서 실행
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, self._close_selenium_driver)
                    self.driver = None
                    logger.info("Selenium browser closed successfully.")
                except Exception as e:
                    logger.error(f"Error closing browser: {e}")
            elif self._browser_instance_user_count < 0:
                self._browser_instance_user_count = 0
                
    def _close_selenium_driver(self):
        """Selenium WebDriver를 종료합니다."""
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                logger.error(f"Error quitting Selenium driver: {e}")

    async def browse_website(self, url: str, action: str = None, selector: str = None,
                            input_text: str = None, timeout: int = 30000,
                            close_browser: bool = False, new_page: bool = False) -> dict:
        """
        웹사이트를 방문하고 지정된 액션을 수행합니다.
        반환값은 항상 일관된 JSON 형식의 딕셔너리입니다.
        """
        logger.info(f"browse_website called with url='{url}', action='{action}', selector='{selector}', close_browser='{close_browser}'")
        
        # 결과 딕셔너리 초기화 - 항상 일관된 형식 유지
        result = {
            "status": "error",
            "final_url": url,
            "page_title": "",
            "action_performed": action if action else "get_content",
            "data": {},
            "error_message": ""
        }
        
        try:
            # 브라우저 확인
            await self._ensure_browser()
            
            # 동기 Selenium 코드를 별도 스레드에서 실행
            loop = asyncio.get_event_loop()
            browser_action_args = {
                "url": url, 
                "action": action, 
                "selector": selector, 
                "input_text": input_text, 
                "timeout_ms": timeout
            }
            result = await loop.run_in_executor(
                self._executor, 
                lambda: self._sync_browse_website(**browser_action_args)
            )
            return result
            
        except Exception as e:
            logger.error(f"Selenium browser operation failed: {str(e)}", exc_info=True)
            result["status"] = "error"
            result["error_message"] = f"{type(e).__name__} - {str(e)}"
            return result
        finally:
            await self._maybe_close_browser(force_close=close_browser)

    def _sync_browse_website(self, url, action=None, selector=None, input_text=None, timeout_ms=30000):
        """Selenium으로 웹사이트를 방문하고 액션을 수행합니다."""
        timeout_sec = timeout_ms / 1000  # 밀리초를 초로 변환
        result = {
            "status": "error",
            "final_url": url,
            "page_title": "",
            "action_performed": action if action else "get_content",
            "data": {},
            "error_message": ""
        }
        
        try:
            # 모바일 네이버 블로그 URL을 데스크탑 버전으로 변환
            original_url = url
            if "m.blog.naver.com" in url:
                url = url.replace("m.blog.naver.com", "blog.naver.com")
                logger.info(f"모바일 URL을 데스크탑 버전으로 변환: {original_url} -> {url}")
            
            # URL로 이동
            self.driver.get(url)
            
            # 페이지 로드 대기 (body 요소가 로드될 때까지)
            WebDriverWait(self.driver, timeout_sec).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # 네이버 블로그의 경우 동적 콘텐츠 로딩을 위한 추가 대기
            if "blog.naver.com" in url:
                logger.debug("네이버 블로그 감지됨. 동적 콘텐츠 로딩 대기 중...")
                
                # 개선된 대기 시스템: 기본 7초 대기 + 조건부 추가 대기
                import time
                start_time = time.time()
                time.sleep(7)  # 기본 대기 시간 증가 (3초 -> 7초)
                logger.debug(f"기본 7초 대기 완료. 동적 컨텐츠 로딩 상태 확인 중...")
                
                # 동적 컨텐츠 로딩 완료를 위한 조건부 대기
                try:
                    # 조건 1: JavaScript 실행 완료 대기
                    WebDriverWait(self.driver, 5).until(
                        lambda driver: driver.execute_script("return document.readyState") == "complete"
                    )
                    logger.debug("JavaScript readyState 완료 확인")
                    
                    # 조건 2: 주요 컨텐츠 요소의 내용 존재 확인
                    content_loaded = self._wait_for_naver_content_loading()
                    if content_loaded:
                        elapsed_time = time.time() - start_time
                        logger.info(f"네이버 블로그 동적 컨텐츠 로딩 완료: {elapsed_time:.1f}초 소요")
                    else:
                        logger.warning("동적 컨텐츠 로딩 상태를 확인할 수 없음")
                        
                except TimeoutException:
                    logger.warning("동적 컨텐츠 로딩 완료 대기 시간 초과")
                    
                total_elapsed = time.time() - start_time
                logger.debug(f"네이버 블로그 대기 총 소요 시간: {total_elapsed:.1f}초")
            
            # 기본 정보 설정
            result["status"] = "success"
            result["page_title"] = self.driver.title
            result["final_url"] = self.driver.current_url
            
            logger.info(f"Successfully navigated to: {url} (Title: {self.driver.title})")
            
            if action == "extract_text":
                target_selector = selector
                if not selector:
                    logger.debug("No selector provided for extract_text, trying common content selectors.")
                    
                    # 네이버 블로그 특화 셀렉터들을 우선 시도
                    if "blog.naver.com" in url:
                        naver_selectors = [
                            ".se-main-container",  # 스마트에디터 메인 컨테이너
                            ".se_component",  # 스마트에디터 컴포넌트
                            "#postViewArea",  # 포스트 뷰 영역
                            ".post_ct",  # 포스트 컨텐츠
                            ".blogview_content",  # 블로그 뷰 컨텐츠
                            "[data-module='content']",  # 데이터 속성
                            ".contents_inner",  # 내부 컨텐츠
                            ".se-text-paragraph"  # 텍스트 문단
                        ]
                        for sel in naver_selectors:
                            try:
                                elements = self.driver.find_elements(By.CSS_SELECTOR, sel)
                                if elements and elements[0].text.strip():
                                    target_selector = sel
                                    logger.debug(f"Using Naver blog selector: {target_selector}")
                                    break
                            except Exception:
                                continue
                    
                    # 일반적인 셀렉터들 시도
                    if not target_selector:
                        common_selectors = ["article", "main", "[role='main']", ".content", ".post-body", ".entry-content", "body"]
                        for sel in common_selectors:
                            try:
                                elements = self.driver.find_elements(By.CSS_SELECTOR, sel)
                                if elements and elements[0].text.strip():
                                    target_selector = sel
                                    logger.debug(f"Using common selector: {target_selector}")
                                    break
                            except Exception:
                                continue

                if target_selector:
                    try:
                        # 요소를 찾을 때까지 대기
                        element = WebDriverWait(self.driver, timeout_sec/2).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, target_selector))
                        )
                        element_text = element.text
                        
                        # 텍스트 길이 및 내용 검증
                        if len(element_text.strip()) < 50:  # 너무 짧은 텍스트인 경우
                            logger.warning(f"추출된 텍스트가 너무 짧습니다 ({len(element_text)} 문자). 다른 셀렉터 시도...")
                            
                            # 네이버 블로그의 경우 여러 요소를 합쳐서 시도
                            if "blog.naver.com" in url:
                                all_text_elements = self.driver.find_elements(By.CSS_SELECTOR, ".se-text-paragraph, .se_component, p")
                                combined_text = "\n".join([elem.text for elem in all_text_elements if elem.text.strip()])
                                if len(combined_text.strip()) > len(element_text.strip()):
                                    element_text = combined_text
                                    logger.info(f"네이버 블로그 다중 요소 텍스트 추출 성공: {len(element_text)} 문자")
                        
                        # 텍스트 길이 제한
                        max_len = 6000  # 증가된 최대 길이
                        if len(element_text) > max_len:
                            element_text = element_text[:max_len] + f"... (content truncated at {max_len} chars)"
                        
                        result["data"]["text_content"] = element_text
                        result["data"]["used_selector"] = target_selector
                        result["data"]["text_length"] = len(element_text)
                        
                        logger.info(f"텍스트 추출 성공: {len(element_text)} 문자 (셀렉터: {target_selector})")
                        
                        # 내용 검증을 위한 추가 로깅
                        if len(element_text.strip()) > 0:
                            logger.debug(f"추출된 텍스트 샘플 (처음 200자): {element_text[:200]}...")
                        else:
                            logger.warning("추출된 텍스트가 비어있습니다!")
                            
                    except TimeoutException:
                        result["status"] = "error"
                        result["error_message"] = f"Timeout waiting for element with selector: {target_selector}"
                        logger.warning(f"Timeout waiting for element with selector: {target_selector}")
                else:
                    result["status"] = "error"
                    result["error_message"] = "Could not find a suitable element to extract text from."
                    logger.warning("No suitable selector found to extract text.")

            elif action == "click":
                if not selector:
                    result["status"] = "error"
                    result["error_message"] = "selector is required for click action"
                    logger.warning("Click action attempted without a selector.")
                    return result
                
                logger.debug(f"Attempting to click selector: {selector}")
                try:
                    # 요소를 찾을 때까지 대기
                    element = WebDriverWait(self.driver, timeout_sec/2).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                    element.click()
                    
                    # 페이지 변화를 대기
                    time.sleep(1)  # 안정성을 위한 짧은 대기
                    
                    # 페이지 정보 업데이트
                    new_page_title = self.driver.title
                    result["page_title"] = new_page_title
                    result["final_url"] = self.driver.current_url
                    result["data"]["message"] = f"Clicked element with selector '{selector}'"
                    logger.info(f"Clicked selector '{selector}'. New page title: {new_page_title}")
                except TimeoutException:
                    result["status"] = "error"
                    result["error_message"] = f"Timeout waiting for clickable element with selector: {selector}"
                    logger.warning(f"Timeout waiting for clickable element with selector: {selector}")
                except Exception as e:
                    result["status"] = "error"
                    result["error_message"] = f"Error clicking element with selector '{selector}': {str(e)}"
                    logger.error(f"Error clicking element: {e}")

            elif action == "type":
                if not selector:
                    result["status"] = "error"
                    result["error_message"] = "selector is required for type action"
                    logger.warning("Type action attempted without a selector.")
                    return result
                    
                if input_text is None:
                    result["status"] = "error"
                    result["error_message"] = "input_text is required for type action"
                    logger.warning("Type action attempted without input_text.")
                    return result
                    
                logger.debug(f"Attempting to type into selector: {selector}")
                try:
                    # 요소를 찾을 때까지 대기
                    element = WebDriverWait(self.driver, timeout_sec/2).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    element.clear()  # 기존 텍스트 제거
                    element.send_keys(input_text)
                    result["data"]["message"] = f"Typed '{input_text}' into element with selector '{selector}'"
                    logger.info(f"Typed '{input_text}' into selector '{selector}'.")
                except TimeoutException:
                    result["status"] = "error"
                    result["error_message"] = f"Timeout waiting for element with selector: {selector}"
                    logger.warning(f"Timeout waiting for element with selector: {selector}")
                except Exception as e:
                    result["status"] = "error"
                    result["error_message"] = f"Error typing into element with selector '{selector}': {str(e)}"
                    logger.error(f"Error typing into element: {e}")
            
            else:  # 액션이 지정되지 않았을 때는 기본적으로 페이지 전체 텍스트를 가져옴
                # 네이버 블로그 특화 처리
                if "blog.naver.com" in url:
                    logger.debug("네이버 블로그 기본 컨텐츠 추출 시도")
                    
                    # 먼저 메인 프레임에서 컨텐츠 추출 시도
                    body_text = self._extract_naver_blog_content()
                    
                    # 메인 프레임에서 충분한 컨텐츠를 얻지 못한 경우 iframe 확인
                    if len(body_text.strip()) < 50:
                        logger.debug("메인 프레임에서 충분한 컨텐츠를 찾지 못함. iframe 확인 중...")
                        iframe_content = self._try_extract_from_iframes()
                        if iframe_content and len(iframe_content.strip()) > len(body_text.strip()):
                            body_text = iframe_content
                            logger.info(f"iframe에서 컨텐츠 추출 성공: {len(body_text)} 문자")
                else:
                    # 일반 웹사이트의 경우
                    body_text = self.driver.find_element(By.TAG_NAME, "body").text
                
                # 텍스트 길이 제한 및 내용 검증
                max_len = 6000
                if len(body_text) > max_len:
                    body_text = body_text[:max_len] + f"... (content truncated at {max_len} chars)"
                
                result["data"]["text_content"] = body_text
                result["data"]["text_length"] = len(body_text)
                result["action_performed"] = "get_content"
                
                logger.info(f"기본 컨텐츠 추출 완료: {len(body_text)} 문자")
                
                # 컨텐츠 품질 검증
                if len(body_text.strip()) < 100:
                    logger.warning(f"추출된 컨텐츠가 너무 짧습니다: {len(body_text)} 문자")
                    logger.debug(f"컨텐츠 샘플: {body_text[:200]}...")
                else:
                    logger.debug(f"컨텐츠 샘플 (처음 200자): {body_text[:200]}...")

            return result

        except Exception as e:
            logger.error(f"Selenium action '{action}' on URL '{url}' failed: {str(e)}", exc_info=True)
            result["status"] = "error"
            result["error_message"] = f"{type(e).__name__} - {str(e)}"
            return result

    async def close_all_resources(self):
        """모든 브라우저 리소스를 강제로 닫습니다. 애플리케이션 종료 시 호출될 수 있습니다."""
        logger.info("Force closing all browser resources.")
        await self._maybe_close_browser(force_close=True)
        if self._executor:
            self._executor.shutdown(wait=False)
            
    def _extract_naver_blog_content(self):
        """네이버 블로그에서 메인 프레임의 컨텐츠를 추출합니다."""
        # 개선된 네이버 블로그 셀렉터 우선순위 (.se-main-container > #postViewArea > .se_component)
        primary_selectors = [
            ".se-main-container",  # 최우선: 스마트에디터 메인 컨테이너
            "#postViewArea",       # 2순위: 포스트 뷰 영역 
            ".se_component"         # 3순위: 스마트에디터 컴포넌트
        ]
        
        # 추가 폴백 셀렉터들
        fallback_selectors = [
            ".post_ct",             # 전통 포스트 컨텐츠
            ".blogview_content",    # 블로그 뷰 컨텐츠
            "[data-module='content']", # 데이터 모듈 속성
            ".contents_inner"       # 내부 컨텐츠
        ]
        
        body_text = ""
        used_selector = None
        
        # 1단계: 주요 셀렉터로 충분한 컨텐츠 찾기
        for selector in primary_selectors:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    content = elements[0].text.strip()
                    if len(content) >= 50:  # 50자 이상의 충분한 컨텐츠
                        if len(content) > len(body_text):
                            body_text = content
                            used_selector = selector
                            logger.info(f"주요 셀렉터로 충분한 컨텐츠 발견 ({selector}): {len(content)} 문자")
            except Exception as e:
                logger.debug(f"주요 셀렉터 {selector} 시도 실패: {e}")
        
        # 충분한 컨텐츠를 찾았으면 바로 반환
        if len(body_text.strip()) >= 50:
            logger.debug(f"주요 셀렉터로 충분한 컨텐츠 추출 완료: {used_selector}")
            return body_text
        
    def _extract_multiple_elements(self):
        """다중 요소를 병합하여 컨텐츠를 추출합니다."""
        try:
            # 다양한 텍스트 요소 셀렉터들 (우선순위 순)
            text_selectors = [
                ".se-text-paragraph",   # 스마트에디터 텍스트 문단
                ".se-text",             # 스마트에디터 텍스트
                "p",                   # 일반 문단
                "div[class*='text']",  # 텍스트 클래스 포함 div
                "div[class*='content']", # 컨텐츠 클래스 포함 div
                ".post-text",          # 포스트 텍스트
                "span[class*='text']", # 텍스트 스팬
                "article p",           # 아티클 내 문단
            ]
            
            combined_texts = []
            total_chars = 0
            
            for selector in text_selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        text = element.text.strip()
                        if text and len(text) > 5:  # 5자 이상의 의미있는 텍스트
                            # 중복 제거: 이미 추가된 텍스트와 유사도 검사
                            is_duplicate = False
                            for existing_text in combined_texts:
                                if text in existing_text or existing_text in text:
                                    is_duplicate = True
                                    break
                            
                            if not is_duplicate:
                                combined_texts.append(text)
                                total_chars += len(text)
                                
                                # 충분한 컨텐츠를 모았으면 조기 종료
                                if total_chars > 500:
                                    logger.debug(f"충분한 컨텐츠 모음 ({total_chars}자), 수집 종료")
                                    break
                                    
                except Exception as e:
                    logger.debug(f"다중 요소 셀렉터 {selector} 시도 실패: {e}")
                    continue
                
                # 충분한 컨텐츠를 모았으면 루프 종료
                if total_chars > 500:
                    break
            
            # 병합된 텍스트 생성
            if combined_texts:
                result = "\n".join(combined_texts)
                logger.info(f"다중 요소 병합 완료: {len(combined_texts)}개 요소, {len(result)}자")
                return result
            else:
                logger.debug("다중 요소에서 유효한 컨텐츠를 찾지 못함")
                return ""
                
        except Exception as e:
            logger.warning(f"다중 요소 병합 과정에서 오류: {e}")
            return ""
            
        # 2단계: 폴백 셀렉터로 추가 시도
        logger.debug("주요 셀렉터에서 충분한 컨텐츠를 찾지 못함. 폴백 셀렉터 시도 중...")
        for selector in fallback_selectors:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    content = elements[0].text.strip()
                    if len(content) > len(body_text):
                        body_text = content
                        used_selector = selector
                        logger.debug(f"폴백 셀렉터로 컨텐츠 발견 ({selector}): {len(content)} 문자")
            except Exception as e:
                logger.debug(f"폴백 셀렉터 {selector} 시도 실패: {e}")
        
        # 3단계: 다중 요소 병합 시도 (개선된 로직)
        if len(body_text.strip()) < 50:
            logger.debug("기본 셀렉터로 충분한 컨텐츠를 찾지 못함. 다중 요소 병합 시도...")
            combined_content = self._extract_multiple_elements()
            if len(combined_content.strip()) > len(body_text.strip()):
                body_text = combined_content
                used_selector = "multiple_elements"
                logger.info(f"다중 요소 병합으로 컨텐츠 추출: {len(body_text)} 문자")
        
        # 4단계: 최종 폴백 (body 태그)
        if len(body_text.strip()) < 50:
            try:
                body_text = self.driver.find_element(By.TAG_NAME, "body").text
                used_selector = "body"
                logger.debug(f"body 태그로 최종 폴백: {len(body_text)} 문자")
            except Exception as e:
                logger.warning(f"body 태그 추출 실패: {e}")
                body_text = ""
        
        # 최종 결과 로깅
        if len(body_text.strip()) >= 50:
            logger.info(f"컨텐츠 추출 성공: {len(body_text)} 문자 (selector: {used_selector})")
        else:
            logger.warning(f"컨텐츠 추출 부족: {len(body_text)} 문자 (selector: {used_selector})")
                
        return body_text
        
    def _try_extract_from_iframes(self):
        """iframe들을 순회하며 컨텐츠 추출을 시도합니다."""
        try:
            # 현재 컨텍스트 저장
            original_context = True
            best_content = ""
            iframe_count = 0
            
            # 모든 iframe 요소 찾기
            iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
            logger.debug(f"발견된 iframe 개수: {len(iframes)}개")
            
            for i, iframe in enumerate(iframes):
                try:
                    iframe_count += 1
                    logger.debug(f"iframe {iframe_count}/{len(iframes)} 처리 중...")
                    
                    # iframe으로 전환
                    self.driver.switch_to.frame(iframe)
                    
                    # iframe 내부에서 컨텐츠 추출 시도
                    iframe_content = self._extract_naver_blog_content()
                    
                    # 더 좋은 컨텐츠를 발견한 경우 업데이트
                    if len(iframe_content.strip()) > len(best_content.strip()):
                        best_content = iframe_content
                        logger.info(f"iframe {iframe_count}에서 더 나은 컨텐츠 발견: {len(best_content)} 문자")
                    
                    # 충분한 컨텐츠를 찾으면 조기 종료
                    if len(best_content.strip()) > 200:
                        logger.info(f"iframe {iframe_count}에서 충분한 컨텐츠 발견, 검색 종료")
                        break
                        
                except Exception as e:
                    logger.debug(f"iframe {iframe_count} 처리 중 오류: {e}")
                finally:
                    # 항상 기본 컨텍스트로 복원
                    try:
                        self.driver.switch_to.default_content()
                    except Exception as e:
                        logger.warning(f"기본 컨텍스트 복원 실패: {e}")
            
            if best_content:
                logger.info(f"iframe 검색 완료. 최고 컨텐츠 길이: {len(best_content)} 문자")
            else:
                logger.debug("iframe에서 유효한 컨텐츠를 찾지 못함")
                
            return best_content
            
        except Exception as e:
            logger.error(f"iframe 추출 과정에서 오류 발생: {e}")
            # 오류 발생시에도 기본 컨텍스트로 복원 시도
            try:
                self.driver.switch_to.default_content()
            except:
                pass
            return ""
    
    def _wait_for_naver_content_loading(self):
        """네이버 블로그의 동적 컨텐츠 로딩 완료를 확인합니다."""
        try:
            # 주요 네이버 블로그 셀렉터들을 확인하여 컨텐츠 로딩 상태 검사
            content_selectors = [
                ".se-main-container",
                "#postViewArea", 
                ".se_component",
                ".post_ct",
                ".se-text-paragraph"
            ]
            
            for selector in content_selectors:
                try:
                    # 각 셀렉터에대해 요소 존재 및 텍스트 길이 확인
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        element_text = elements[0].text.strip()
                        if len(element_text) > 10:  # 10자 이상의 의미있는 컨텐츠를 발견
                            logger.debug(f"컨텐츠 로딩 확인: {selector}에서 {len(element_text)}자 발견")
                            return True
                except Exception as e:
                    logger.debug(f"셀렉터 {selector} 확인 중 오류: {e}")
                    continue
            
            # 모든 셀렉터에서 충분한 컨텐츠를 찾지 못한 경우
            logger.debug("주요 셀렉터에서 충분한 컨텐츠를 찾지 못함")
            return False
            
        except Exception as e:
            logger.warning(f"컨텐츠 로딩 상태 확인 중 오류: {e}")
            return False
