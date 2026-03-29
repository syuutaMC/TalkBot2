# Copilot Instructions - TalkBot2 Project

このファイルは、TalkBot2プロジェクト全体におけるコーディング規約と、GitHub Copilotの振る舞いを定義します。

## プロジェクト概要

TalkBot2は、VOICEVOX Engineを使用してDiscordのテキストチャンネルのメッセージを読み上げるBotです。

### 技術スタック
- **言語**: Python 3.9+
- **フレームワーク**: discord.py (音声対応)
- **音声合成**: VOICEVOX Engine
- **非同期処理**: asyncio, aiohttp
- **デプロイ**: Docker / Docker Compose

### プロジェクト構造

```
TalkBot2/
├── .github/              # Copilot設定・スキル定義
│   ├── copilot-instructions.md  # このファイル
│   └── skills/          # カスタムスキル
│       ├── async-error-handling/  # 非同期エラーハンドリング
│       ├── commit/                # コミットガイドライン
│       ├── discord-bot-dev/       # Discord Bot開発
│       └── discord-test/          # Discord Botテスト
├── src/                 # ソースコード
│   ├── __init__.py
│   ├── bot.py          # メインBot（コマンド・イベント・辞書・音声キュー）
│   ├── voicevox_client.py  # VOICEVOX連携
│   ├── metrics.py      # メトリクス管理（レイテンシ・エラー・コマンド使用回数）
│   ├── dashboard.py    # 監視ダッシュボード（aiohttp Webサーバー）
│   └── templates/      # ダッシュボードテンプレート
│       └── index.html
├── tests/              # テストコード
│   ├── __init__.py
│   ├── test_bot.py
│   └── test_voicevox_client.py
├── docker/             # Docker設定
│   ├── Dockerfile            # Bot用
│   ├── Dockerfile.dashboard  # ダッシュボード用
│   └── docker-compose.yml    # 3サービス構成（voicevox, bot, dashboard）
├── config/             # 設定ファイル（config.json, metrics.json）
├── run.py              # 起動スクリプト
└── requirements.txt    # 依存パッケージ
```

---

## コーディング規約

### 全般ルール

1. **Python標準スタイル**: PEP 8に従う
   - インデント: スペース4つ
   - 行の長さ: 最大120文字（ドキュメント文字列は適宜改行）
   - 命名規則:
     - クラス: `PascalCase`
     - 関数/変数: `snake_case`
     - 定数: `UPPER_SNAKE_CASE`
     - プライベート: `_leading_underscore`

2. **型ヒント**: すべての関数・メソッドに型ヒントを付ける
   ```python
   async def create_audio(self, text: str, speaker_id: int = 1, speed: float = 1.0) -> Optional[bytes]:
       pass
   ```

3. **ドキュメント文字列**: すべての関数・クラスにdocstringを記述
   ```python
   """
   関数の簡潔な説明
   
   Args:
       arg1 (type): 引数の説明
       arg2 (type): 引数の説明
   
   Returns:
       type: 戻り値の説明
   """
   ```

4. **非同期処理**: 
   - I/O処理は必ず非同期 (`async`/`await`)
   - 適切なエラーハンドリングとタイムアウト設定

5. **エラーハンドリング**:
   - 想定されるエラーは適切にキャッチして処理
   - ユーザーにわかりやすいエラーメッセージを返す
   - ログ出力を適切に行う

### Discord Bot固有のルール

1. **コマンド実装**:
   - スラッシュコマンド (`app_commands`) を優先
   - コマンドには必ず説明を付ける
   - `@app_commands.describe()` で引数の説明を明記

2. **Intents**: 必要最小限のIntentsのみ有効化
   ```python
   intents = discord.Intents.default()
   intents.message_content = True  # メッセージ読み上げに必要
   intents.guilds = True           # ギルド情報の取得に必要
   intents.voice_states = True     # ボイスチャンネル管理に必要
   ```

3. **権限チェック**: コマンド実行前に必要な権限をチェック

4. **音声処理**:
   - 音声キューを使用して順次再生
   - 適切なクリーンアップ処理（切断時など）

### VOICEVOX連携のルール

1. **セッション管理**: `aiohttp.ClientSession`を適切に初期化・クローズ
2. **エラーハンドリング**: Engine接続エラーを適切に処理
3. **レート制限**: 過度なAPI呼び出しを避ける

---

## テスト要件（最重要）

### 🔥 テストファースト原則

**すべての新機能追加・リファクタリングにおいて、テストコードを必ず併記してください。**

1. **新機能追加時**:
   - 機能コードとテストコードを同時に作成
   - テストが通ることを確認してからcommit

2. **リファクタリング時**:
   - 既存テストを更新または追加
   - 動作が変わらないことを確認

3. **バグ修正時**:
   - バグを再現するテストを先に書く
   - 修正後、テストが通ることを確認

### テストの種類

1. **単体テスト (Unit Tests)**:
   - 各関数・メソッドを個別にテスト
   - 外部依存をモック化
   - `tests/test_*.py` に配置

2. **統合テスト (Integration Tests)**:
   - モジュール間の連携をテスト
   - `unittest.mock` を使用してDiscord API、VOICEVOX APIをモック化

### テストツール

- **フレームワーク**: `pytest` または `unittest`
- **モック**: `unittest.mock` (AsyncMock for async functions)
- **カバレッジ**: `pytest-cov` で80%以上を目標

### テストのベストプラクティス

1. **テストケース命名**: `test_<機能>_<条件>_<期待結果>`
   ```python
   def test_create_audio_success_returns_bytes():
       pass
   
   def test_create_audio_with_invalid_speaker_returns_none():
       pass
   ```

2. **モック使用例**:
   ```python
   from unittest.mock import AsyncMock, patch, MagicMock
   import pytest

   @pytest.mark.asyncio
   async def test_voicevox_client_get_speakers():
       client = VoicevoxClient()
       client.session = AsyncMock()
       
       # モックレスポンス設定
       mock_response = AsyncMock()
       mock_response.status = 200
       mock_response.json = AsyncMock(return_value=[{"name": "Speaker1"}])
       client.session.get.return_value.__aenter__.return_value = mock_response
       
       # 実行とアサーション
       result = await client.get_speakers()
       assert len(result) == 1
       assert result[0]["name"] == "Speaker1"
   ```

3. **Discord Botのモック**:
   ```python
   @pytest.mark.asyncio
   async def test_join_command():
       # Botインスタンスをモック化
       bot = MagicMock(spec=VoiceBot)
       interaction = MagicMock(spec=discord.Interaction)
       interaction.user.voice.channel = MagicMock()
       
       # コマンドテスト
       await join(interaction)
       interaction.response.send_message.assert_called_once()
   ```

### Copilotへの指示

**新しいコードを書くとき**:
- 該当する機能のテストコードを同時に生成してください
- モックを適切に使用してください
- エッジケース（異常系）もテストしてください

**既存コードを修正するとき**:
- 影響を受けるテストを特定し、必要に応じて更新してください
- テストカバレッジが下がらないようにしてください

---

## 環境変数管理

1. **必須環境変数**:
   - `DISCORD_TOKEN`: Discord Botトークン
   - `VOICEVOX_URL`: VOICEVOX EngineのURL（デフォルト: `http://127.0.0.1:50021`）
   - `DISCORD_GUILD_ID`: テスト用ギルドID（オプション）

2. **`.env`ファイル**: 
   - 本番環境の秘密情報は`.env`に保存
   - `.env.example`にサンプルを用意
   - Gitには含めない（`.gitignore`に追加済み）

---

## Git運用

1. **ブランチ戦略**:
   - `main`: 本番環境コード
   - `develop`: 開発環境コード
   - `feature/*`: 新機能開発
   - `bugfix/*`: バグ修正

2. **コミットメッセージ**:
   ```
   <type>: <subject>
   
   <body>
   
   <footer>
   ```
   - type: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`
   - subject: 変更内容を簡潔に（日本語可）

3. **Pull Request**:
   - すべてのテストが通ることを確認
   - コードレビューを依頼

---

## Copilot動作設定

### コード生成時の優先事項

1. **テストコードを必ず生成**: 機能コードとセットで提案
2. **型安全性**: 型ヒントを必ず含める
3. **エラーハンドリング**: 例外処理を適切に実装
4. **ドキュメント**: docstringを自動生成
5. **非同期コード**: Discord/VOICEVOX APIは必ず`async/await`

### コード修正時の優先事項

1. **テストの更新**: 既存テストを破壊しない
2. **後方互換性**: 既存の設定ファイルと互換性を保つ
3. **パフォーマンス**: 不要な処理を追加しない
4. **ドキュメント・スキルの同期**: コード変更に応じて関連ドキュメントを更新する

### コード変更時のドキュメント・スキル同期ルール

**コード変更後、以下を必ず確認し、必要に応じて更新してください：**

1. **copilot-instructions.md の更新**:
   - 新しいファイル/モジュールを追加した場合 → 「プロジェクト構造」セクションに反映
   - 新しい環境変数を追加した場合 → 「環境変数管理」セクションと `.env.example` に反映
   - Intentsや依存関係の変更 → 該当セクションのコード例を更新
   - 更新履歴に変更内容を追記

2. **スキルの追加・更新**:
   - 新しい技術領域（例: データベース連携、外部API連携）を導入した場合 → 対応するスキルを `.github/skills/` に追加
   - 既存スキルの前提が変わった場合（例: テストフレームワーク変更） → スキル内容を更新
   - スキルを追加・削除した場合 → このファイルの「スキルの使用」セクションも更新

3. **更新が不要なケース**:
   - 既存機能のバグ修正のみの場合
   - コードフォーマットのみの変更

### 禁止事項

- ❌ テストなしでの新機能追加
- ❌ 型ヒントの省略
- ❌ ハードコードされた秘密情報
- ❌ 同期的なI/O処理（Discord/HTTP通信）
- ❌ グローバル変数の濫用

---

## スキルの使用

### `.github/skills/`に定義されたスキル

- **discord-test**: Discord Botのテスト作成ガイドライン
  - テスト作成時は必ずこのスキルを参照
  - モックの使用方法やベストプラクティスが含まれる
- **discord-bot-dev**: Discord Bot開発のベストプラクティス
  - スラッシュコマンド、音声処理、イベントハンドリングの実装ガイド
- **async-error-handling**: 非同期エラーハンドリングのベストプラクティス
  - Discord Bot、VOICEVOX連携などの非同期処理に適用
- **commit**: コミットメッセージのガイドライン
  - 明確で原子的なコミットメッセージの作成

### スキルの呼び出し方

コード生成時、Copilotは自動的にこれらのスキルを参照しますが、明示的に参照したい場合は：

```
@discord-test スラッシュコマンドのテストを生成してください
@discord-bot-dev 音声処理の実装を手伝ってください
```

---

## 参考リソース

- [discord.py ドキュメント](https://discordpy.readthedocs.io/)
- [VOICEVOX Engine API仕様](https://voicevox.github.io/voicevox_engine/api/)
- [pytest ドキュメント](https://docs.pytest.org/)
- [asyncio ドキュメント](https://docs.python.org/ja/3/library/asyncio.html)

---

**更新履歴**:
- 2026-03-29: プロジェクト構造を実態に合わせて更新（metrics, dashboard, 辞書機能等を反映）
- 2026-03-29: スキル構造を実態に合わせて修正
- 2026-03-26: 初版作成
