import subprocess
import sys

def install_modules():
    """필요한 Python 모듈을 설치합니다."""
    required_modules = [
        'selenium',
        'webdriver-manager',
        'streamlit',
        'pandas',
        'openpyxl',
        'requests',
        'beautifulsoup4',
    ]
    
    print("필요한 모듈 설치 중...")
    
    for module in required_modules:
        try:
            print(f"\n{module} 설치 중...")
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', module])
            print(f"{module} 설치 완료!")
        except subprocess.CalledProcessError as e:
            print(f"오류: {module} 설치 실패! - {e}")
            print("설치를 계속합니다...")
    
    print("\n모든 모듈 설치 프로세스 완료!")

if __name__ == "__main__":
    install_modules() 