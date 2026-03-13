# Discord 読み上げBot with VOICEVOX

VOICEVOX Engineを使用してDiscordのテキストチャンネルのメッセージを読み上げるBotです。

## プロジェクト構造

```
erii_TalkBot/
├── src/                    # ソースコード
│   ├── __init__.py        # パッケージ初期化
│   ├── bot.py             # メインのBotファイル
│   └── voicevox_client.py # VOICEVOX Engine連携モジュール
├── docker/                 # Docker関連ファイル
│   ├── Dockerfile         # Botのコンテナ定義
│   ├── docker-compose.yml # サービス構成
│   └── .dockerignore      # Docker除外設定
├── config/                 # 設定ファイル
│   └── config.json        # Bot設定
├── .env.example           # 環境変数サンプル
├── .gitignore             # Git除外設定
├── requirements.txt       # Python依存パッケージ
└── README.md              # このファイル
```

## 機能

- ✅ スラッシュコマンド対応
- ✅ VOICEVOXによる高品質な音声合成
- ✅ ユーザーごとに異なる音声キャラクター設定可能
- ✅ 読み上げ速度の調整
- ✅ 複数の話者（キャラクター）から選択可能

## 必要な環境

### Dockerを使う場合（推奨）
- Docker
- Docker Compose
- Discord Bot Token

### 直接起動する場合
- Python 3.9以上
- Discord Bot Token
- VOICEVOX Engine（ローカルで起動）
- FFmpeg（音声再生に必要）

## セットアップ

### 1. VOICEVOX Engineのインストール

[VOICEVOX公式サイト](https://voicevox.hiroshiba.jp/)からVOICEVOX Engineをダウンロードして起動してください。

デフォルトでは `http://127.0.0.1:50021` で起動します。

### 2. FFmpegのインストール

#### Windows
1. [FFmpeg公式サイト](https://ffmpeg.org/download.html)からダウンロード
2. zipを解凍し、`bin`フォルダのパスを環境変数に追加

#### Mac
```bash
brew install ffmpeg
```

#### Linux
```bash
sudo apt install ffmpeg
```

### 3. Discord Botの作成

1. [Discord Developer Portal](https://discord.com/developers/applications)にアクセス
2. 「New Application」をクリックしてアプリケーションを作成
3. 「Bot」タブで「Add Bot」をクリック
4. 「TOKEN」をコピーして保存
5. 「Privileged Gateway Intents」で以下を有効化：
   - MESSAGE CONTENT INTENT
   - SERVER MEMBERS INTENT
6. 「OAuth2」→「URL Generator」で以下を選択：
   - SCOPES: `bot`, `applications.commands`
   - BOT PERMISSIONS: 
     - Send Messages
     - Connect
     - Speak
     - Use Voice Activity
7. 生成されたURLでBotをサーバーに招待

### 4. プロジェクトのセットアップ

```bash
# リポジトリのクローン
git clone <repository_url>
cd erii_TalkBot

# 仮想環境の作成（推奨）
python -m venv venv

# 仮想環境の有効化
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

# 依存パッケージのインストール
pip install -r requirements.txt
```

### 5. 環境変数の設定

`.env.example`をコピーして`.env`ファイルを作成し、設定を記入してください。

```bash
# Windowsの場合
copy .env.example .env

# Mac/Linuxの場合
cp .env.example .env
```

`.env`ファイルを編集：
```env
DISCORD_TOKEN=あなたのDiscord Bot Token
VOICEVOX_URL=http://127.0.0.1:50021
```

## 使い方

### Dockerを使う場合（推奨）

Dockerを使えばVOICEVOX EngineとBotを一緒に簡単に起動できます。

```bash
# .envファイルを作成（DISCORD_TOKENを設定）
copy .env.example .env  # Windowsの場合
# または
cp .env.example .env    # Mac/Linuxの場合

# Docker Composeで起動（dockerフォルダから実行）
cd docker
docker-compose up -d

# ログの確認
docker-compose logs -f discord-bot

# 停止
docker-compose down
cd ..
```

起動時に以下のメッセージが表示されればOKです：
```
✓ VOICEVOX Engineに接続しました
✓ スラッシュコマンドを同期しました
✓ BotName としてログインしました
```

### 直接起動する場合

```bash
# 方法1: run.pyを使用（推奨）
python run.py

# 方法2: 直接指定
python src/bot.py

# 方法3: モジュールとして実行
python -m src.bot
```

### 2. コマンド一覧

| コマンド | 説明 |
|---------|------|
| `/join` | Botがボイスチャンネルに参加し、読み上げを開始 |
| `/leave` | Botがボイスチャンネルから退出 |
| `/voice <speaker_id>` | 自分の読み上げ音声を変更（話者IDを指定） |
| `/speakers` | 利用可能な話者（キャラクター）一覧を表示 |
| `/speed <速度>` | 読み上げ速度を設定（0.5〜2.0） |

### 3. 使用例

1. ボイスチャンネルに接続
2. テキストチャンネルで `/join` を実行
3. Botが同じボイスチャンネルに参加
4. そのテキストチャンネルに書き込まれたメッセージが自動で読み上げられます
5. `/speakers` で好きなキャラクターを探す
6. `/voice 3` のように話者IDを指定して自分の声を変更
7. `/speed 1.2` で少し速く読み上げるように設定可能

## Docker関連のコマンド

```bash
# dockerフォルダに移動
cd docker

# コンテナの起動
docker-compose up -d

# ログの確認
docker-compose logs -f

# Botのみのログ
docker-compose logs -f discord-bot

# VOICEVOX Engineのみのログ
docker-compose logs -f voicevox

# コンテナの再起動
docker-compose restart

# コンテナの停止
docker-compose down

# イメージの再ビルド
docker-compose build --no-cache

# コンテナの状態確認
docker-compose ps

# プロジェクトルートに戻る
cd ..
```

## トラブルシューティング

### Docker使用時

#### コンテナが起動しない
```bash
# ログを確認
docker-compose logs

# コンテナを再ビルド
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

#### VOICEVOX Engineが起動しない
- メモリが不足していないか確認（最低4GB推奨）
- Docker Desktopのリソース設定を確認

### 直接起動時

#### VOICEVOX Engineに接続できない

- VOICEVOX Engineが起動しているか確認
- `.env`ファイルの`VOICEVOX_URL`が正しいか確認
- ファイアウォールで50021ポートがブロックされていないか確認

### 音声が再生されない

- FFmpegがインストールされているか確認
- FFmpegのパスが環境変数に追加されているか確認
- コマンドプロンプト/ターミナルで `ffmpeg -version` を実行して確認

### Botがボイスチャンネルに参加できない

- Bot招待時に「Connect」と「Speak」権限を付与したか確認
- サーバーの権限設定を確認

## ライセンス

MIT License

## クレジット

- 音声合成: [VOICEVOX](https://voicevox.hiroshiba.jp/)
- Discord API: [discord.py](https://github.com/Rapptz/discord.py)
