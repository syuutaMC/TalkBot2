---
name: discord-bot-test
description: Discord Bot（TalkBot2）のテストコード作成をサポート。テスト駆動開発（TDD）を実践し、モックを使用した単体・統合テストのベストプラクティスを提供
compatibility: Designed for GitHub Copilot CLI
metadata:
  author: TalkBot2 Project
  version: "1.0"
  original-source: https://github.com/syuutaMC
---

# Discord Bot Testing Skill

このスキルは、TalkBot2（Discord Bot）のテストコード作成をサポートし、**テスト駆動開発（TDD）**を実践するためのガイドラインを提供します。

## スキルの目的

高品質で保守性の高いDiscord Botを開発するため、以下を実現します：

- ✅ テストファースト原則の実践
- ✅ モックを活用した外部依存の分離
- ✅ 単体テストと統合テストの適切な使い分け
- ✅ 高いテストカバレッジの維持

---

## テスト作成の原則

### 1. テストファースト原則

**新機能を実装する前に、まずテストを書く**

```python
# ❌ 悪い例: テストなしで機能を実装
async def new_feature():
    # 実装...
    pass

# ✅ 良い例: テストを先に書く
@pytest.mark.asyncio
async def test_new_feature_success():
    # Arrange
    bot = create_mock_bot()
    
    # Act
    result = await bot.new_feature()
    
    # Assert
    assert result is not None
```

**適用場面**:
- 新機能追加時
- リファクタリング時（既存テストの更新）
- バグ修正時（バグを再現するテストを先に書く）

### 2. テストの種類と使い分け

**単体テスト（Unit Tests）**:
- 目的: 個別の関数・メソッドを検証
- 特徴: 外部依存はすべてモック化、高速実行
- 配置: `tests/test_*.py`

**統合テスト（Integration Tests）**:
- 目的: モジュール間の連携を検証
- 特徴: 実際の動作フローに近い、モックは最小限
- 配置: `tests/integration/test_*.py`

### 3. AAA (Arrange-Act-Assert) パターン

```python
@pytest.mark.asyncio
async def test_create_audio_with_custom_speaker():
    # Arrange (準備)
    client = VoicevoxClient()
    client.session = AsyncMock()
    mock_response = create_mock_audio_response(b"audio_data")
    client.session.post.return_value.__aenter__.return_value = mock_response
    
    # Act (実行)
    result = await client.create_audio("テスト", speaker_id=3, speed=1.2)
    
    # Assert (検証)
    assert result == b"audio_data"
    client.session.post.assert_called_once()
```

---

## Discord Bot特有のテストパターン

### 1. スラッシュコマンドのテスト

```python
import discord
from discord import app_commands
from unittest.mock import AsyncMock, MagicMock
import pytest

@pytest.mark.asyncio
async def test_slash_command_join_voice_channel():
    """ボイスチャンネル参加コマンドのテスト"""
    # Arrange
    bot = MagicMock(spec=VoiceBot)
    interaction = MagicMock(spec=discord.Interaction)
    
    # ユーザーがボイスチャンネルにいる状態をモック
    voice_channel = MagicMock(spec=discord.VoiceChannel)
    interaction.user.voice.channel = voice_channel
    interaction.response.send_message = AsyncMock()
    
    # Botがまだ接続していない状態
    interaction.guild.voice_client = None
    voice_channel.connect = AsyncMock()
    
    # Act
    await join_command(interaction, bot)
    
    # Assert
    voice_channel.connect.assert_called_once()
    interaction.response.send_message.assert_called_once()
    assert "参加しました" in str(interaction.response.send_message.call_args)


@pytest.mark.asyncio
async def test_slash_command_user_not_in_voice():
    """ユーザーがボイスチャンネルにいない場合のエラー処理"""
    # Arrange
    bot = MagicMock(spec=VoiceBot)
    interaction = MagicMock(spec=discord.Interaction)
    interaction.user.voice = None  # ボイスチャンネルにいない
    interaction.response.send_message = AsyncMock()
    
    # Act
    await join_command(interaction, bot)
    
    # Assert
    interaction.response.send_message.assert_called_once()
    call_args = str(interaction.response.send_message.call_args)
    assert "ボイスチャンネルに参加してください" in call_args or "エラー" in call_args
```

### 2. 音声再生のテスト

```python
@pytest.mark.asyncio
async def test_voice_playback_with_queue():
    """音声キューを使用した再生のテスト"""
    # Arrange
    bot = VoiceBot()
    guild_id = 12345
    bot.voice_queues[guild_id] = asyncio.Queue()
    
    voice_client = MagicMock(spec=discord.VoiceClient)
    voice_client.is_playing.return_value = False
    voice_client.play = MagicMock()
    
    # キューに音声データを追加
    audio_source = MagicMock(spec=discord.FFmpegPCMAudio)
    await bot.voice_queues[guild_id].put(audio_source)
    
    # Act
    await bot.process_voice_queue(guild_id, voice_client)
    
    # Assert
    voice_client.play.assert_called_once()
    assert bot.voice_queues[guild_id].empty()
```

### 3. メッセージ読み上げのテスト

```python
@pytest.mark.asyncio
async def test_on_message_text_to_speech():
    """メッセージを受信して読み上げる処理のテスト"""
    # Arrange
    bot = VoiceBot()
    bot.voicevox = AsyncMock(spec=VoicevoxClient)
    bot.voicevox.create_audio = AsyncMock(return_value=b"audio_data")
    
    message = MagicMock(spec=discord.Message)
    message.author.bot = False
    message.content = "こんにちは"
    message.guild.id = 12345
    message.author.id = 67890
    
    # ボイスクライアントをモック
    voice_client = MagicMock(spec=discord.VoiceClient)
    message.guild.voice_client = voice_client
    
    # Act
    await bot.on_message(message)
    
    # Assert
    bot.voicevox.create_audio.assert_called_once_with(
        "こんにちは",
        speaker_id=bot.user_speakers.get(67890, 1),
        speed=bot.user_speeds.get(67890, 1.0)
    )
```

---

## VOICEVOX連携のテストパターン

### 1. APIクライアントのモック

```python
import aiohttp
from unittest.mock import AsyncMock, patch
import pytest

@pytest.fixture
async def voicevox_client():
    """VOICEVOX Clientのフィクスチャ"""
    client = VoicevoxClient("http://localhost:50021")
    await client.initialize()
    yield client
    await client.close()


@pytest.mark.asyncio
async def test_get_speakers_success(voicevox_client):
    """話者一覧取得の成功ケース"""
    # Arrange
    expected_speakers = [
        {"name": "四国めたん", "speaker_uuid": "uuid1"},
        {"name": "ずんだもん", "speaker_uuid": "uuid2"}
    ]
    
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value=expected_speakers)
    
    voicevox_client.session.get = AsyncMock(
        return_value=AsyncMockContext(mock_response)
    )
    
    # Act
    speakers = await voicevox_client.get_speakers()
    
    # Assert
    assert len(speakers) == 2
    assert speakers[0]["name"] == "四国めたん"
    voicevox_client.session.get.assert_called_once_with(
        "http://localhost:50021/speakers"
    )


@pytest.mark.asyncio
async def test_create_audio_api_error(voicevox_client):
    """音声生成APIエラー時の処理"""
    # Arrange
    mock_response = AsyncMock()
    mock_response.status = 500
    
    voicevox_client.session.post = AsyncMock(
        return_value=AsyncMockContext(mock_response)
    )
    
    # Act
    result = await voicevox_client.create_audio("テスト", speaker_id=1)
    
    # Assert
    assert result is None  # エラー時はNoneを返す


@pytest.mark.asyncio
async def test_create_audio_timeout():
    """タイムアウト時の処理"""
    # Arrange
    client = VoicevoxClient()
    client.session = AsyncMock()
    client.session.post.side_effect = asyncio.TimeoutError()
    
    # Act
    result = await client.create_audio("テスト", speaker_id=1)
    
    # Assert
    assert result is None
```

### 2. AsyncMock用コンテキストマネージャー

```python
class AsyncMockContext:
    """aiohttpのレスポンスコンテキストマネージャーのモック"""
    def __init__(self, response):
        self.response = response
    
    async def __aenter__(self):
        return self.response
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
```

---

## 設定ファイルのテスト

```python
import json
import tempfile
from pathlib import Path

def test_load_config_file():
    """設定ファイル読み込みのテスト"""
    # Arrange
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        config_data = {
            "user_speakers": {"12345": 3, "67890": 5},
            "user_speeds": {"12345": 1.2}
        }
        config_path.write_text(json.dumps(config_data), encoding="utf-8")
        
        # Act
        bot = VoiceBot()
        bot.CONFIG_FILE = config_path
        bot._load_config()
        
        # Assert
        assert bot.user_speakers[12345] == 3
        assert bot.user_speeds[12345] == 1.2


def test_save_config_file():
    """設定ファイル保存のテスト"""
    # Arrange
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        
        bot = VoiceBot()
        bot.CONFIG_FILE = config_path
        bot.user_speakers = {12345: 3}
        bot.user_speeds = {12345: 1.5}
        
        # Act
        bot._save_config()
        
        # Assert
        assert config_path.exists()
        saved_data = json.loads(config_path.read_text(encoding="utf-8"))
        assert saved_data["user_speakers"]["12345"] == 3
        assert saved_data["user_speeds"]["12345"] == 1.5
```

---

## テスト実行環境の構築

### pytest設定 (`pytest.ini`)

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
asyncio_mode = auto
markers =
    asyncio: mark test as async
    slow: mark test as slow running
    integration: mark test as integration test
```

### 依存パッケージ (`requirements-dev.txt`)

```txt
pytest>=7.4.0
pytest-asyncio>=0.21.0
pytest-cov>=4.1.0
pytest-mock>=3.11.0
```

### テスト実行コマンド

```bash
# すべてのテストを実行
pytest

# カバレッジ付きで実行
pytest --cov=src --cov-report=html

# 特定のテストファイルのみ
pytest tests/test_bot.py

# 詳細出力
pytest -v

# 失敗したテストのみ再実行
pytest --lf
```

---

## テスト実行フロー（チェックリスト）

- [ ] テスト環境のセットアップ（pytest, pytest-asyncio等）
- [ ] 機能実装前にテストケースを設計
- [ ] モックオブジェクトの準備（Discord API, VOICEVOX API）
- [ ] AAA パターンでテストコードを実装
- [ ] テストを実行して失敗することを確認（Red）
- [ ] 機能コードを実装（Green）
- [ ] リファクタリング（Refactor）
- [ ] カバレッジを確認（80%以上を目標）
- [ ] エッジケース・異常系のテストを追加

---

## 重要なガイドライン

### ✅ 必ず守るべきルール

1. **テストコードとプロダクションコードはセット**
   - ✅ 新機能実装時は必ずテストも作成
   - ✅ バグ修正時は再現テストを先に書く
   - ✅ リファクタリング前にテストが通ることを確認

2. **外部依存は必ずモック化**
   - ✅ Discord API（interaction, message, voice_clientなど）
   - ✅ VOICEVOX API（create_audio, get_speakersなど）
   - ✅ ファイルシステム（設定ファイル読み書き）

3. **テストは独立して実行可能**
   - ✅ テストの実行順序に依存しない
   - ✅ 他のテストの結果に影響されない
   - ✅ データベースやファイルの状態をクリーンアップ

4. **命名規則を守る**
   ```python
   def test_<機能名>_<条件>_<期待結果>():
       pass
   
   # 例:
   def test_join_voice_channel_when_user_in_channel_succeeds():
       pass
   
   def test_create_audio_when_api_timeout_returns_none():
       pass
   ```

5. **適切なカバレッジを維持**
   - 全体: 80%以上
   - コアロジック（bot.py, voicevox_client.py）: 90%以上
   - 新規追加コード: 100%

### 📋 テストの分類基準

**単体テスト（Unit Tests）**:
- 個別の関数・メソッド
- すべての外部依存をモック
- 高速実行（ミリ秒単位）

**統合テスト（Integration Tests）**:
- 複数モジュールの連携
- 主要な依存はモック、内部連携は実コード
- やや時間がかかる（秒単位）

### 🎯 TalkBot2固有のベストプラクティス

1. **Discord Bot関連のテスト**:
   ```python
   # ✅ 良い例: 明確な状態設定
   interaction = MagicMock(spec=discord.Interaction)
   interaction.user.voice.channel = MagicMock(spec=discord.VoiceChannel)
   
   # ❌ 悪い例: 曖昧なモック
   interaction = MagicMock()
   interaction.user = MagicMock()
   ```

2. **VOICEVOX連携のテスト**:
   ```python
   # ✅ 良い例: コンテキストマネージャーを適切にモック
   mock_response = AsyncMock()
   mock_response.status = 200
   client.session.get.return_value = AsyncMockContext(mock_response)
   
   # ❌ 悪い例: コンテキストマネージャーを無視
   mock_response = AsyncMock()
   client.session.get.return_value = mock_response
   ```

3. **非同期処理のテスト**:
   ```python
   # ✅ 良い例: @pytest.mark.asyncioを使用
   @pytest.mark.asyncio
   async def test_async_function():
       result = await async_function()
       assert result is not None
   
   # ❌ 悪い例: 同期テストとして書く
   def test_async_function():
       result = async_function()  # awaitなし
       assert result is not None
   ```

---

## テスト環境の構築

### 依存パッケージ（`requirements-dev.txt`）

```txt
# テストフレームワーク
pytest>=7.4.0
pytest-asyncio>=0.21.0
pytest-cov>=4.1.0
pytest-mock>=3.11.0

# カバレッジレポート
coverage>=7.3.0
```

### pytest設定（`pytest.ini`）

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
asyncio_mode = auto

markers =
    asyncio: mark test as async
    slow: mark test as slow running
    integration: mark test as integration test
    unit: mark test as unit test
```

### テスト実行コマンド

```powershell
# すべてのテストを実行
pytest

# カバレッジ付きで実行
pytest --cov=src --cov-report=html --cov-report=term

# 特定のテストファイルのみ
pytest tests/test_bot.py

# 詳細出力
pytest -v

# 失敗したテストのみ再実行
pytest --lf

# マーカーでフィルタリング
pytest -m "not slow"
```

---

## Copilotへの指示

### 新機能実装時

**必ず以下を同時に生成**:
1. 機能コード（src/配下）
2. テストコード（tests/配下）
3. モックの適切な使用
4. 正常系・異常系・境界値のテストケース

**テンプレート**:
```python
# 1. テスト（先に書く）
@pytest.mark.asyncio
async def test_new_feature_success():
    """機能が正常に動作することを確認"""
    # Arrange
    ...
    # Act
    ...
    # Assert
    ...

# 2. 実装（テストが通るように）
async def new_feature():
    """新機能の実装"""
    ...
```

### リファクタリング時

1. 既存テストを実行して現在の動作を確認
2. リファクタリング実施
3. テストが全て通ることを確認
4. 必要に応じてテストも更新

### コードレビュー時のチェックポイント

- [ ] すべての新機能にテストが存在する
- [ ] テストが通る（CI/CDで確認）
- [ ] モックが適切に使用されている
- [ ] エッジケースがカバーされている
- [ ] テスト名が命名規則に従っている
- [ ] カバレッジが基準を満たしている
- [ ] テストコードに複雑なロジックがない

---

## カバレッジ目標

| カテゴリ | 目標カバレッジ | 対象ファイル |
|---------|------------|-----------|
| **コアロジック** | 90%以上 | `bot.py`, `voicevox_client.py` |
| **ユーティリティ** | 80%以上 | その他の`src/`配下 |
| **全体** | 80%以上 | プロジェクト全体 |
| **新規追加コード** | 100% | 新しく追加した機能 |

---

## よくあるパターンと解決策

### パターン1: Discord Interaction のモック

```python
# 問題: interactionの属性が複雑でモックが難しい
# 解決策: specを使用して型を明示

interaction = MagicMock(spec=discord.Interaction)
interaction.guild = MagicMock(spec=discord.Guild)
interaction.guild.id = 12345
interaction.user = MagicMock(spec=discord.Member)
interaction.user.voice.channel = MagicMock(spec=discord.VoiceChannel)
interaction.response.send_message = AsyncMock()
```

### パターン2: aiohttpレスポンスのモック

```python
# 問題: aiohttpはコンテキストマネージャーを使用
# 解決策: AsyncMockContext クラスを作成

class AsyncMockContext:
    def __init__(self, response):
        self.response = response
    
    async def __aenter__(self):
        return self.response
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

# 使用例
mock_response = AsyncMock()
mock_response.status = 200
mock_response.json = AsyncMock(return_value=[...])
client.session.get.return_value = AsyncMockContext(mock_response)
```

### パターン3: 音声ファイルの生成テスト

```python
# 問題: 実際の音声ファイル生成は時間がかかる
# 解決策: tempfileとモックを組み合わせる

import tempfile
from pathlib import Path

def test_save_audio_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        audio_path = Path(tmpdir) / "test.wav"
        # テスト実行
        save_audio(b"audio_data", audio_path)
        # 検証
        assert audio_path.exists()
        assert audio_path.read_bytes() == b"audio_data"
```

---

## エラー対応

### テストが失敗した場合

```powershell
# 詳細なエラー情報を表示
pytest -vv

# 最後に失敗したテストのみ再実行
pytest --lf

# ステップごとにデバッグ
pytest --pdb

# 特定のテストのみ実行
pytest tests/test_bot.py::test_specific_function
```

### モックが期待通りに動作しない場合

```python
# モックの呼び出し履歴を確認
mock_object.method.assert_called()
print(mock_object.method.call_args)
print(mock_object.method.call_args_list)

# モックがどのように呼ばれたか詳細に確認
import pprint
pprint.pprint(mock_object.method.call_args_list)
```

---

## まとめ

このスキルを活用することで、TalkBot2プロジェクトは以下を実現します：

✅ **高品質なコードベース**
   - バグの早期発見と修正
   - 安定した動作の保証

✅ **安心してリファクタリング可能**
   - 既存機能を壊さない保証
   - コード改善の容易性

✅ **新規開発者のオンボーディング容易化**
   - テストコードがドキュメントの役割
   - 期待動作の明確化

✅ **継続的な品質向上**
   - カバレッジによる可視化
   - CI/CDとの統合

**すべての変更は、テストとともに。**
