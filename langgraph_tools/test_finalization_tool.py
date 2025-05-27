"""
데이터 수집 완료 도구에 대한 단위 테스트.

이 테스트는 LangChain @tool로 구현된 finalize_blog_data_collection 도구를 검증합니다.
"""

import unittest
from unittest.mock import patch, MagicMock
import os
import sys

from langgraph_tools.finalization_tool import (
    finalize_blog_data_collection, 
    _validate_blog_data, 
    get_data_writer,
    _validate_url,
    _validate_date,
    _validate_number
)


class TestFinalizationTool(unittest.TestCase):
    """데이터 수집 완료 도구 테스트 클래스."""
    
    def test_validate_blog_data(self):
        """블로그 데이터 검증 함수를 테스트합니다."""
        
        # 유효한 데이터
        valid_data = [
            {
                "blog_id": "example_blog_1",
                "blog_name": "기술 블로그 1",
                "blog_url": "https://example.com/blog1",
                "recent_post_date": "2023-05-15"
            },
            {
                "blog_id": "example_blog_2",
                "blog_name": "기술 블로그 2",
                "blog_url": "https://example.com/blog2",
                "recent_post_date": "2023-06-20"
            }
        ]
        
        # 최소 5개 블로그가 필요하다고 가정 (설정에 따라 달라짐)
        with patch('langgraph_tools.finalization_tool.settings') as mock_settings:
            mock_settings.MINIMUM_BLOGS_TO_COLLECT = 1
            errors, warnings = _validate_blog_data(valid_data)
            self.assertEqual(len(errors), 0)  # 오류가 없어야 함
            
            mock_settings.MINIMUM_BLOGS_TO_COLLECT = 3
            errors, warnings = _validate_blog_data(valid_data)
            self.assertEqual(len(errors), 1)  # 블로그 수가 부족하다는 오류 발생
        
        # 누락된 필드가 있는 데이터
        invalid_data = [
            {
                "blog_id": "example_blog_1",
                "blog_name": "",  # 빈 필드
                "blog_url": "https://example.com/blog1"
            },
            {
                "blog_id": "example_blog_2",
                # blog_name 누락
                "blog_url": "Not Found",  # 유효하지 않은 값
                "recent_post_date": "2023-06-20"
            }
        ]
        
        with patch('langgraph_tools.finalization_tool.settings') as mock_settings:
            mock_settings.MINIMUM_BLOGS_TO_COLLECT = 1
            errors, warnings = _validate_blog_data(invalid_data)
            self.assertGreater(len(errors), 0)  # 오류가 있어야 함
    
    def test_url_validation(self):
        """URL 검증 함수를 테스트합니다."""
        # 유효한 URL
        valid_urls = [
            "https://example.com",
            "http://example.com/blog",
            "https://blog.example.co.kr/posts/1234",
            "http://127.0.0.1:8080"
        ]
        for url in valid_urls:
            self.assertTrue(_validate_url(url), f"URL '{url}'은 유효해야 합니다.")
        
        # 유효하지 않은 URL
        invalid_urls = [
            "",
            None,
            "Not Found",
            "example.com",  # 스키마 없음
            "https://",     # 호스트 없음
            "http:/example.com",  # 잘못된 형식
            "ftp://example.com"   # 지원되지 않는 스키마
        ]
        for url in invalid_urls:
            self.assertFalse(_validate_url(url), f"URL '{url}'은 유효하지 않아야 합니다.")
    
    def test_date_validation(self):
        """날짜 검증 함수를 테스트합니다."""
        # 유효한 날짜
        valid_dates = [
            "2023-05-15",
            "2023/05/15",
            "15-05-2023",
            "15/05/2023",
            "2023년 5월 15일",
            "5월 15일, 2023"
        ]
        for date in valid_dates:
            self.assertTrue(_validate_date(date), f"날짜 '{date}'는 유효해야 합니다.")
        
        # 유효하지 않은 날짜
        invalid_dates = [
            "",
            None,
            "Not Found",
            "2023-13-45",  # 존재하지 않는 월/일
            "오늘",        # 구체적인 날짜 아님
            "어제 업데이트됨",
            "약 1주일 전"
        ]
        for date in invalid_dates:
            self.assertFalse(_validate_date(date), f"날짜 '{date}'는 유효하지 않아야 합니다.")
    
    def test_number_validation(self):
        """숫자 필드 검증 함수를 테스트합니다."""
        # 유효한 숫자 값
        valid_numbers = [
            "123",
            "1000",
            "약 100개",
            "100개 이상",
            "100+",
            "100-200",
            "대략 100명"
        ]
        for num in valid_numbers:
            self.assertTrue(_validate_number(num), f"숫자 값 '{num}'은 유효해야 합니다.")
        
        # 유효하지 않은 숫자 값
        invalid_numbers = [
            "",
            None,
            "Not Found",
            "많음",
            "여러 개",
            "비공개"
        ]
        for num in invalid_numbers:
            self.assertFalse(_validate_number(num), f"숫자 값 '{num}'은 유효하지 않아야 합니다.")
    
    def test_validate_blog_data_with_warnings(self):
        """경고를 발생시키는 데이터 검증을 테스트합니다."""
        # 경고를 발생시키는 데이터 (필수 필드는 있지만 형식이 맞지 않음)
        warning_data = [
            {
                "blog_id": "example_blog_1",
                "blog_name": "기술 블로그 1",
                "blog_url": "https://example.com/blog1",
                "recent_post_date": "어제 업데이트됨",  # 잘못된 날짜 형식
                "total_posts": "많음"  # 잘못된 숫자 형식
            },
            {
                "blog_id": "example_blog_2",
                "blog_name": "기술 블로그 2",
                "blog_url": "https://example.com/blog2",
                "recent_post_date": "2023-06-20",
                "blog_creation_date": "설립된지 3년됨"  # 잘못된 날짜 형식
            }
        ]
        
        with patch('langgraph_tools.finalization_tool.settings') as mock_settings:
            mock_settings.MINIMUM_BLOGS_TO_COLLECT = 1
            errors, warnings = _validate_blog_data(warning_data)
            self.assertEqual(len(errors), 0)  # 필수 필드는 모두 있으므로 오류 없음
            self.assertGreater(len(warnings), 0)  # 형식이 맞지 않아 경고 발생
    
    def test_validate_blog_data_with_duplicates(self):
        """중복 데이터 검증을 테스트합니다."""
        # 중복된 blog_id와 URL이 있는 데이터
        duplicate_data = [
            {
                "blog_id": "duplicate_id",
                "blog_name": "블로그 1",
                "blog_url": "https://example.com/blog"
            },
            {
                "blog_id": "duplicate_id",  # 중복 ID
                "blog_name": "블로그 2",
                "blog_url": "https://example.com/different"
            },
            {
                "blog_id": "unique_id",
                "blog_name": "블로그 3",
                "blog_url": "https://example.com/blog"  # 중복 URL
            }
        ]
        
        with patch('langgraph_tools.finalization_tool.settings') as mock_settings:
            mock_settings.MINIMUM_BLOGS_TO_COLLECT = 1
            errors, warnings = _validate_blog_data(duplicate_data)
            self.assertEqual(len(errors), 0)  # 필수 필드는 모두 있으므로 오류 없음
            
            # 중복에 대한 경고가 있어야 함
            duplicate_warnings = [w for w in warnings if "중복" in w]
            self.assertGreater(len(duplicate_warnings), 0)
    
    def test_finalize_blog_data_success(self):
        """데이터 수집 완료 성공 케이스를 테스트합니다."""
        # 모의 DataWriter 설정
        mock_writer = MagicMock()
        
        # save_data 메서드가 성공 응답을 반환하도록 설정
        mock_writer.save_data.return_value = "output/scraped_data_20240101_123456.xlsx"
        
        # 테스트 데이터
        test_blogs = [
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
        
        # 설정 모의 객체와 get_data_writer 패치
        with patch('langgraph_tools.finalization_tool.settings') as mock_settings, \
             patch('langgraph_tools.finalization_tool.get_data_writer', return_value=mock_writer):
            
            mock_settings.MINIMUM_BLOGS_TO_COLLECT = 1
            mock_settings.DATA_FIELDS_TO_EXTRACT = [
                "blog_id", "blog_name", "blog_url", "recent_post_date", "first_post_date",
                "total_posts", "blog_creation_date", "average_visitors", "llm_summary"
            ]
            
            # 테스트 실행 - invoke 메서드 사용
            result = finalize_blog_data_collection.invoke({
                "collected_blogs_summary": test_blogs,
                "all_tasks_completed": True,
                "quality_score": 8.5,
                "recommendations": ["추가 프로그래밍 블로그 검색 고려"]
            })
            
            # 결과 검증
            self.assertEqual(result["status"], "success")
            self.assertIn("summary_stats", result["data"])
            self.assertEqual(result["data"]["summary_stats"]["total_blogs"], 2)
            self.assertEqual(result["data"]["summary_stats"]["quality_score"], 8.5)
            self.assertIn("saved_file_path", result["data"])
            
            # DataWriter.save_data 호출 검증
            mock_writer.save_data.assert_called_once()
            call_args = mock_writer.save_data.call_args[0]
            self.assertEqual(len(call_args[0]), 2)  # 블로그 데이터 리스트
    
    def test_finalize_blog_data_with_warnings(self):
        """경고가 있는 데이터 수집 완료를 테스트합니다."""
        # 모의 DataWriter 설정
        mock_writer = MagicMock()
        mock_writer.save_data.return_value = "output/scraped_data_20240101_123456.xlsx"
        
        # 경고를 발생시키는 테스트 데이터
        test_blogs = [
            {
                "blog_id": "example_blog_1",
                "blog_name": "기술 블로그 1",
                "blog_url": "https://example.com/blog1",
                "recent_post_date": "어제 업데이트됨",  # 잘못된 날짜 형식
                "total_posts": "많음"  # 잘못된 숫자 형식
            }
        ]
        
        # 설정 모의 객체와 get_data_writer 패치
        with patch('langgraph_tools.finalization_tool.settings') as mock_settings, \
             patch('langgraph_tools.finalization_tool.get_data_writer', return_value=mock_writer):
            
            mock_settings.MINIMUM_BLOGS_TO_COLLECT = 1
            mock_settings.DATA_FIELDS_TO_EXTRACT = ["blog_id", "blog_name", "blog_url", "recent_post_date", "total_posts"]
            
            # 테스트 실행 - invoke 메서드 사용
            result = finalize_blog_data_collection.invoke({
                "collected_blogs_summary": test_blogs,
                "all_tasks_completed": True
            })
            
            # 결과 검증
            self.assertEqual(result["status"], "success")  # 경고가 있어도 성공해야 함
            self.assertIn("warnings", result["data"]["summary_stats"])  # 경고가 포함되어야 함
            self.assertGreater(result["data"]["summary_stats"]["warnings_count"], 0)
            
            # DataWriter.save_data 호출 검증
            mock_writer.save_data.assert_called_once()
    
    def test_finalize_blog_data_with_recommendations(self):
        """추천 사항이 포함된 데이터 수집 완료를 테스트합니다."""
        # 모의 DataWriter 설정
        mock_writer = MagicMock()
        mock_writer.save_data.return_value = "output/scraped_data_20240101_123456.xlsx"
        
        # 테스트 데이터 (최소한의 유효한 데이터)
        test_blogs = [
            {
                "blog_id": "example_blog_1",
                "blog_name": "기술 블로그 1",
                "blog_url": "https://example.com/blog1"
            }
        ]
        
        # 추천 사항 설정
        recommendations = [
            "추가 프로그래밍 블로그 검색 고려",
            "검색어 범위 확장 추천",
            "데이터 품질 향상을 위한 제안"
        ]
        
        # 설정 모의 객체와 get_data_writer 패치
        with patch('langgraph_tools.finalization_tool.settings') as mock_settings, \
             patch('langgraph_tools.finalization_tool.get_data_writer', return_value=mock_writer):
            
            mock_settings.MINIMUM_BLOGS_TO_COLLECT = 1
            mock_settings.DATA_FIELDS_TO_EXTRACT = ["blog_id", "blog_name", "blog_url"]
            
            # 테스트 실행 - invoke 메서드 사용
            result = finalize_blog_data_collection.invoke({
                "collected_blogs_summary": test_blogs,
                "all_tasks_completed": True,
                "quality_score": 7.5,
                "recommendations": recommendations
            })
            
            # 결과 검증
            self.assertEqual(result["status"], "success")
            self.assertIn("recommendations", result["data"]["summary_stats"])
            self.assertEqual(len(result["data"]["summary_stats"]["recommendations"]), 3)
            
            # DataWriter.save_data 호출 검증
            mock_writer.save_data.assert_called_once()
    
    def test_finalize_blog_data_invalid_inputs(self):
        """
        유효하지 않은 입력 케이스를 테스트합니다.
        
        LangChain @tool 데코레이터는 자동으로 입력 검증을 수행하므로, 
        여기서는 내부 함수 _validate_blog_data를 직접 테스트하고
        작업 미완료 케이스만 도구 호출로 테스트합니다.
        """
        # 모의 DataWriter 설정
        mock_writer = MagicMock()
        
        # 설정 모의 객체와 get_data_writer 패치
        with patch('langgraph_tools.finalization_tool.settings') as mock_settings, \
             patch('langgraph_tools.finalization_tool.get_data_writer', return_value=mock_writer):
            
            mock_settings.MINIMUM_BLOGS_TO_COLLECT = 1
            mock_settings.DATA_FIELDS_TO_EXTRACT = ["blog_id", "blog_name", "blog_url"]
            
            # 테스트 1: _validate_blog_data 함수로 빈 리스트 검증
            empty_list_errors, warnings = _validate_blog_data([])
            self.assertGreater(len(empty_list_errors), 0)
            self.assertIn("블로그 데이터가 비어 있습니다", empty_list_errors[0])
            
            # 테스트 2: _validate_blog_data 함수로 누락된 필드 검증
            invalid_data = [
                {"blog_id": "1", "blog_url": "https://example.com"}, # blog_name 누락
                {"blog_name": "", "blog_id": "2", "blog_url": "https://example.com/2"} # 빈 이름
            ]
            invalid_data_errors, warnings = _validate_blog_data(invalid_data)
            self.assertGreater(len(invalid_data_errors), 0)
            
            # 테스트 3: 작업 미완료 - invoke 메서드 사용
            result = finalize_blog_data_collection.invoke({
                "collected_blogs_summary": [{"blog_id": "1", "blog_name": "테스트", "blog_url": "https://example.com"}],
                "all_tasks_completed": False
            })
            self.assertEqual(result["status"], "error")
            self.assertIn("모든 작업이 완료되지 않았습니다", result["error_message"])
    
    def test_finalize_blog_data_save_error(self):
        """데이터 저장 실패 케이스를 테스트합니다."""
        # 모의 DataWriter 설정
        mock_writer = MagicMock()
        
        # save_data 메서드가 None을 반환하도록 설정 (저장 실패)
        mock_writer.save_data.return_value = None
        
        # 테스트 데이터
        test_blogs = [
            {
                "blog_id": "example_blog_1",
                "blog_name": "기술 블로그 1",
                "blog_url": "https://example.com/blog1"
            }
        ]
        
        # 설정 모의 객체와 get_data_writer 패치
        with patch('langgraph_tools.finalization_tool.settings') as mock_settings, \
             patch('langgraph_tools.finalization_tool.get_data_writer', return_value=mock_writer):
            
            mock_settings.MINIMUM_BLOGS_TO_COLLECT = 1
            mock_settings.DATA_FIELDS_TO_EXTRACT = ["blog_id", "blog_name", "blog_url"]
            
            # 테스트 실행 - invoke 메서드 사용
            result = finalize_blog_data_collection.invoke({
                "collected_blogs_summary": test_blogs,
                "all_tasks_completed": True
            })
            
            # 결과 검증
            mock_writer.save_data.assert_called_once()  # save_data가 호출되었는지 확인
            self.assertEqual(result["status"], "error")
            self.assertIn("데이터 저장 중 오류가 발생했습니다", result["error_message"])
    
    def test_finalize_blog_data_import_error(self):
        """DataWriter 임포트 오류를 테스트합니다."""
        # 테스트 데이터
        test_blogs = [
            {
                "blog_id": "example_blog_1",
                "blog_name": "기술 블로그 1",
                "blog_url": "https://example.com/blog1"
            }
        ]
        
        # get_data_writer가 ImportError를 발생시키도록 패치
        with patch('langgraph_tools.finalization_tool.settings') as mock_settings, \
             patch('langgraph_tools.finalization_tool.get_data_writer', side_effect=ImportError("모듈을 찾을 수 없습니다")):
            
            mock_settings.MINIMUM_BLOGS_TO_COLLECT = 1
            mock_settings.DATA_FIELDS_TO_EXTRACT = ["blog_id", "blog_name", "blog_url"]
            
            # 테스트 실행 - invoke 메서드 사용
            result = finalize_blog_data_collection.invoke({
                "collected_blogs_summary": test_blogs,
                "all_tasks_completed": True
            })
            
            # 결과 검증
            self.assertEqual(result["status"], "error")
            self.assertIn("데이터 저장 모듈을 초기화할 수 없습니다", result["error_message"])


if __name__ == "__main__":
    print("====== 테스트 시작 ======")
    test_result = unittest.main(verbosity=2, exit=False)
    print(f"테스트 결과: {'성공' if test_result.result.wasSuccessful() else '실패'}")
    print("====== 테스트 종료 ======")
    sys.exit(not test_result.result.wasSuccessful()) 