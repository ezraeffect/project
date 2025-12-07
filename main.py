"""
WTVB01-485 Vibration Sensor Monitoring Application
메인 애플리케이션 진입점
"""

import sys
import os

# 현재 디렉토리를 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gui_visualization import main


if __name__ == '__main__':
    main()
