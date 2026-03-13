"""
Discord 読み上げBot 起動スクリプト
プロジェクトルートから簡単に起動できるようにするためのラッパー
"""
import sys
from pathlib import Path

# srcディレクトリをパスに追加
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Botを起動
from src.bot import main

if __name__ == "__main__":
    main()
