# tools/tool_definitions.py

TOOLS_SPEC = [
    {
        "type": "function",
        "function": {
            "name": "search_web_for_blogs",
            "description": "주어진 키워드로 웹을 검색하여 관련 블로그 게시물의 URL 목록을 찾습니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "블로그 검색을 위한 키워드"}
                },
                "required": ["keyword"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "finalize_blog_data_collection",
            "description": "수집된 모든 블로그 정보를 검토하고, 지정된 형식으로 최종 정리하여 사용자에게 제공할 준비가 되었음을 알립니다. 모든 필수 정보가 수집되었는지 확인합니다. 모든 작업이 완료되었을 때만 호출해야 합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "collected_blogs_summary": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "지금까지 수집된 블로그들의 요약 정보 목록"
                    },
                     "all_tasks_completed": {"type": "boolean", "description": "모든 요청된 블로그 정보 수집 작업이 완료되었는지 여부"},
                     "quality_score": {"type": "number", "description": "수집된 데이터의 전체 품질 점수 (1-10)"},
                     "recommendations": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "추가 검색이나 개선을 위한 지능적 제안사항"
                     }
                },
                "required": ["collected_blogs_summary", "all_tasks_completed"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_webpage_content_and_interact",
            "description": "주어진 URL의 웹사이트를 방문하여 페이지 내용을 가져오거나 페이지와 상호작용합니다. 이 도구는 최종 정보 추출이 아닌, 웹페이지 접근 및 원시 데이터 수집 단계에 사용됩니다. 추출된 내용은 extract_blog_fields_from_text 도구로 전달하여 분석해야 합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "분석하거나 상호작용할 웹사이트 URL"},
                    "fields_to_extract": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "추출할 정보 필드 목록 (예: ['blog_name', 'recent_post_date', 'main_content_summary', 'average_visitors_hint'])"
                    },
                    "action_details": {
                        "type": "object",
                        "properties": {
                             "action_type": {"type": "string", "enum": ["click", "type", "extract_specific_text"]},
                             "selector": {"type": "string", "description": "CSS 선택자"},
                             "input_text": {"type": "string", "description": "'type' 액션 시 입력할 텍스트"},
                        },
                        "description": "페이지와 상호작용하기 위한 세부 정보 (선택 사항)"
                    }
                },
                "required": ["url", "fields_to_extract"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "extract_blog_fields_from_text",
            "description": "웹페이지 내용에서 특정 필드의 정보를 추출합니다. 이 도구는 get_webpage_content_and_interact 도구로 얻은 페이지 텍스트를 분석하여 구조화된 정보를 JSON 형식으로 추출합니다. 결과는 반드시 JSON 형식이어야 하며, 모든 필드는 settings.DATA_FIELDS_TO_EXTRACT에 정의된 필드명을 따라야 합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text_content": {"type": "string", "description": "분석할 웹페이지의 텍스트 내용"},
                    "original_url": {"type": "string", "description": "분석 중인 웹페이지의 원본 URL"}
                },
                "required": ["text_content", "original_url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "finalize_blog_data_collection",
            "description": "수집된 모든 블로그 정보를 검토하고, 지정된 형식으로 최종 정리하여 사용자에게 제공할 준비가 되었음을 알립니다. 모든 필수 정보가 수집되었는지 확인합니다. 모든 작업이 완료되었을 때만 호출해야 합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "collected_blogs_summary": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "지금까지 수집된 블로그들의 요약 정보 목록"
                    },
                     "all_tasks_completed": {"type": "boolean", "description": "모든 요청된 블로그 정보 수집 작업이 완료되었는지 여부"}
                },
                "required": ["collected_blogs_summary", "all_tasks_completed"]
            }
        }
    }
]