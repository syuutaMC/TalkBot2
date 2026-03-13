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
COPY config/config.json ./config.json

# Botの起動
CMD ["python", "-u", "src/bot.py"]
