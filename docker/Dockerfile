FROM python:3.11-slim

# FFmpegのインストール
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 作業ディレクトリの設定
WORKDIR /app

# 依存パッケージのインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションファイルのコピー
COPY src/ ./src/
COPY run.py ./
COPY config/config.json ./config.json

# 環境変数の設定
ENV PYTHONUNBUFFERED=1

# Botの起動（プロジェクトルートから実行）
CMD ["python", "-u", "run.py"]
