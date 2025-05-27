# AutoCrawlingUsingLLM Development Guidelines

## Project Overview

**Purpose**: AI-powered web crawling system for blog data collection and analysis
**Tech Stack**: Python, Selenium, Ollama LLM, asyncio, BeautifulSoup
**Core Function**: Autonomous web search → content extraction → LLM analysis → structured data export

## Architecture Rules

### Module Responsibilities
- **core/**: Never create new core modules without updating dependencies in pipelines/
- **pipelines/agent_pipeline.py**: Main orchestration - modify here for workflow changes
- **tools/tool_definitions.py**: LLM tool schemas - update when adding new agent capabilities
- **utils/**: Helper functions only - never include business logic
- **config/**: Configuration loading - use environment variables for sensitive data

### Critical Dependencies
- When modifying `core/browser_controller.py`, always test with `pipelines/agent_pipeline.py`
- When updating `tools/tool_definitions.py`, verify compatibility in `core/llm_handler.py`
- When changing logging in any core module, update the logger configuration in main entry point

## Coding Standards

### Async/Await Usage
- **ALWAYS** use `async/await` for browser operations and LLM calls
- **NEVER** mix synchronous blocking calls in async functions
- Use `asyncio.get_event_loop().run_in_executor()` for blocking Selenium operations

### Logging Requirements
- Use `logger = logging.getLogger(__name__)` in every module
- Log levels: INFO for successful operations, WARNING for recoverable issues, ERROR for failures
- Include relevant context: URLs, text lengths, processing times
- **Example**: `logger.info(f"Extracted {len(content)} characters from {url}")`

### Error Handling
- Wrap all network operations in try-except blocks
- Always include original exception in error messages: `f"{type(e).__name__} - {str(e)}"`
- Return structured error responses, never None or empty strings

## Browser Control Rules

### Selenium Instance Management  
- **CRITICAL**: Use singleton pattern for browser instances in `BrowserController`
- Call `await self._ensure_browser()` before any browser operation
- **NEVER** create multiple browser instances simultaneously
- Always use `await self._maybe_close_browser()` in finally blocks

### Dynamic Content Handling
- Wait minimum 5 seconds for JavaScript-heavy sites (네이버 블로그)
- Use `WebDriverWait` with `EC.presence_of_element_located()` before content extraction
- Check `document.readyState === 'complete'` for JavaScript completion
- **Example**: 
```python
WebDriverWait(self.driver, 10).until(
    lambda driver: driver.execute_script("return document.readyState") == "complete"
)
```

### Content Extraction
- Try multiple selectors in order of specificity
- For 네이버 블로그: `.se-main-container` → `#postViewArea` → `.se_component`
- Always validate extracted content length > 50 characters before accepting
- Log which selector was successful for debugging

## LLM Integration Rules

### Tool Calling Format
- Follow exact JSON schema defined in `tools/tool_definitions.py`
- **NEVER** modify tool call format without updating the schema
- Always include required parameters, use null for optional ones
- **Example**:
```json
{
  "name": "extract_blog_fields_from_text",
  "parameters": {
    "text_content": "actual_content_here",
    "original_url": "https://example.com"
  }
}
```

### Response Processing
- Parse LLM responses with fallback for malformed JSON
- Check for both `tool_calls` array and markdown JSON blocks
- Log raw LLM responses for debugging before parsing
- Handle partial responses gracefully

## Data Processing Rules

### Content Extraction
- Maximum content length: 6000 characters (truncate with "... (content truncated)" message)
- Minimum acceptable content: 50 characters
- Always strip whitespace and validate non-empty content
- Use UTF-8 encoding for all text processing

### Data Structuring
- Use `core/data_extractor.py` for consistent blog data formatting
- Required fields: `blog_id`, `blog_name`, `blog_url`, `recent_post_date`, `llm_summary`
- Generate unique `blog_id` using format: `{domain}_{sanitized_blog_name}`
- **NEVER** create dummy data for missing fields - use "알 수 없음" or null

### Output Management
- Save all results to `outputs/` directory with timestamp
- Use CSV format for structured data, JSON for raw responses
- Include metadata: processing time, success count, error count
- **Naming**: `agent_blog_data_YYYYMMDD_HHMMSS.csv`

## 네이버 블로그 Specific Rules

### URL Handling
- **ALWAYS** convert mobile URLs: `m.blog.naver.com` → `blog.naver.com`
- Log URL conversion for tracking
- Handle both old and new 네이버 블로그 formats

### Content Extraction Strategy
1. Wait 5+ seconds after page load
2. Try iframe switching: `driver.switch_to.frame()` if main content empty
3. Use multiple selector fallback chain
4. Combine multiple text elements if individual ones are too short
5. **Last resort**: Extract from body tag

### Common Issues
- Empty content → Increase wait time and try iframe switching
- Malformed HTML → Use BeautifulSoup for parsing assistance
- JavaScript errors → Add `--disable-javascript` option for testing

## File Modification Rules

### Multi-File Changes
- When modifying browser logic in `core/browser_controller.py`:
  - Update corresponding tests
  - Check compatibility with `pipelines/agent_pipeline.py`
  - Verify tool definitions in `tools/tool_definitions.py`

- When adding new agent capabilities:
  - Add tool definition to `tools/tool_definitions.py`
  - Implement handler in `pipelines/agent_pipeline.py`
  - Update LLM prompt if needed

### Testing Requirements
- **MANDATORY**: Test any browser-related changes with actual websites
- Run with both successful and failing URLs
- Verify CSV output format and content quality
- Test error handling scenarios

### Version Control
- Commit functional changes separately from formatting changes
- Use descriptive commit messages: `feat:`, `fix:`, `chore:`
- **NEVER** commit temporary files, test outputs, or debug scripts

## Prohibited Actions

### Data Generation
- **NEVER** create dummy data, sample data, or placeholder content
- **NEVER** invent URLs, blog names, or content that doesn't exist
- **NEVER** use fake dates or fabricated statistics
- When data is missing, explicitly state "알 수 없음" or return null

### Code Practices
- **NEVER** use hardcoded waits without condition checking
- **NEVER** ignore exceptions or use empty except blocks
- **NEVER** create new browser instances without proper cleanup
- **NEVER** modify core business logic without updating dependent modules

### LLM Integration
- **NEVER** modify JSON schemas without testing with actual LLM
- **NEVER** assume LLM response format - always validate and parse safely
- **NEVER** ignore tool calling errors - always provide fallback behavior

### Browser Operations
- **NEVER** run browser operations in synchronous context
- **NEVER** leave browser instances running without cleanup
- **NEVER** assume page content is immediately available after navigation

## Decision Making Guidelines

### Content Quality Assessment
- Content < 50 chars → Try alternative extraction methods
- Content > 6000 chars → Truncate with clear indication
- Empty or whitespace-only → Log warning and continue to next URL

### Error Recovery
- Network timeout → Retry once with increased timeout
- JavaScript error → Try with JS disabled
- Malformed response → Parse what's available, log errors
- Complete failure → Save partial results and continue

### Performance Optimization
- Reuse browser instances when possible
- Implement timeout limits for all operations
- Log processing times for performance monitoring
- Use async operations for I/O bound tasks

## Examples

### ✅ Correct Implementation
```python
async def extract_content(self, url: str) -> dict:
    try:
        await self._ensure_browser()
        result = await self._sync_browse_website(url)
        if result["status"] == "success":
            logger.info(f"Successfully extracted {len(result['data']['text_content'])} chars")
        return result
    except Exception as e:
        logger.error(f"Content extraction failed for {url}: {e}")
        return {"status": "error", "error_message": str(e)}
    finally:
        await self._maybe_close_browser()
```

### ❌ Incorrect Implementation
```python
def extract_content(self, url: str) -> dict:  # Missing async
    driver = webdriver.Chrome()  # Creating new instance
    driver.get(url)
    content = driver.find_element(By.TAG_NAME, "body").text  # No error handling
    return content  # Wrong return format, no cleanup
```

---

**Last Updated**: 2025-05-27  
**Version**: 1.0  
**AI Agent Target**: Coding tasks for web crawling and LLM integration