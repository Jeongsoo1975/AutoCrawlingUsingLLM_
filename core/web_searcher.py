# core/web_searcher.py
from duckduckgo_search import DDGS
from config import settings
import logging
from utils.error_handler import WebSearchError, handle_errors, log_function_call

logger = logging.getLogger(__name__)

class WebSearcher:
    def __init__(self):
        # DDGS can be initialized without arguments for general use
        pass

    @handle_errors(error_type=Exception, default_return=[], log_traceback=True)
    @log_function_call
    def search_links(self, query):
        """
        웹 검색을 수행하고 title, url, snippet을 포함한 dict 리스트를 반환합니다.
        오류 처리가 개선된 버전입니다.
        """
        if not query or not query.strip():
            logger.warning("Empty query provided to search_links")
            return []
            
        logger.info(f"Performing web search for query: '{query}'")
        results = []
        
        try:
            with DDGS() as ddgs:
                ddgs_results = ddgs.text(
                    query,
                    region='wt-wt',  # World-wide
                    safesearch='moderate',
                    max_results=settings.SEARCH_MAX_RESULTS
                )
                
                if ddgs_results:
                    for r in ddgs_results:
                        # 각 결과에 대해 안전하게 처리
                        result_item = {
                            "title": r.get("title", "No title"),
                            "url": r.get("href", ""),
                            "snippet": r.get("body", "No snippet")
                        }
                        
                        # URL 검증
                        if result_item["url"] and result_item["url"].startswith(('http://', 'https://')):
                            results.append(result_item)
                        else:
                            logger.debug(f"Skipping invalid URL: {result_item['url']}")
                            
                else:
                    logger.warning(f"No search results returned for query: '{query}'")
                    
            logger.info(f"Found {len(results)} valid results for query '{query}'.")
            return results
            
        except Exception as e:
            logger.error(f"Web search failed for query '{query}': {e}", exc_info=True)
            # 오류 시 빈 리스트 반환 (데코레이터가 처리)
            raise WebSearchError(f"Search failed: {e}")

if __name__ == '__main__':
    # Test
    searcher = WebSearcher()
    test_query = "best python practices blog"
    links = searcher.search_links(test_query)
    if links:
        for link_info in links:
            print(f"Title: {link_info['title']}\nURL: {link_info['url']}\nSnippet: {link_info['snippet']}\n---")
    else:
        print("No results found.")