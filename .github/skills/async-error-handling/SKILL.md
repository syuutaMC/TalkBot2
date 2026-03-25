---
name: async-error-handling
description: Python asyncio/awaitにおけるエラーハンドリングとタイムアウト処理のベストプラクティス。Discord Bot、VOICEVOX連携などの非同期処理に適用
compatibility: Designed for GitHub Copilot CLI
metadata:
  author: TalkBot2 Project
  version: "1.0"
  original-source: https://github.com/syuutaMC
---

# Async Error Handling Skill

このスキルは、Python asyncio/awaitを使用した非同期処理におけるエラーハンドリングとベストプラクティスを提供します。

## スキルの対象

- **対象ファイル**: `src/**/*.py`, `tests/**/*.py`
- **対象タスク**: 非同期関数の実装、エラーハンドリング、タイムアウト処理、リトライロジック
- **前提知識**: Python 3.9+, asyncio, aiohttp, discord.py

---

## 非同期エラーハンドリングの原則

### 1. Try-Except-Finallyの適切な使用

非同期関数内でも、同期コードと同様にtry-except-finallyを使用できる。

**✅ 推奨パターン**:

```python
import asyncio
import aiohttp
from typing import Optional

async def fetch_data(url: str) -> Optional[dict]:
    """
    URLからデータを取得
    
    Args:
        url: データ取得元のURL
    
    Returns:
        取得したJSONデータ、失敗時はNone
    """
    session = None
    try:
        # セッション作成
        session = aiohttp.ClientSession()
        
        # タイムアウト設定
        timeout = aiohttp.ClientTimeout(total=10.0)
        
        # データ取得
        async with session.get(url, timeout=timeout) as response:
            response.raise_for_status()
            return await response.json()
    
    except aiohttp.ClientTimeout:
        print(f"⏱️ Timeout: {url}")
        return None
    
    except aiohttp.ClientError as e:
        print(f"❌ HTTP Error: {e}")
        return None
    
    except asyncio.TimeoutError:
        print(f"⏱️ Asyncio Timeout: {url}")
        return None
    
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return None
    
    finally:
        # リソースのクリーンアップ
        if session and not session.closed:
            await session.close()
```

**❌ 避けるべきパターン**:

```python
async def fetch_data_bad(url: str):
    # エラーハンドリングなし
    async with aiohttp.ClientSession() as session:
        response = await session.get(url)  # タイムアウトなし、エラー処理なし
        return await response.json()
```

---

### 2. タイムアウトの設定

すべての外部API呼び出しには必ずタイムアウトを設定する。

**✅ 推奨パターン**:

```python
import asyncio
import aiohttp

async def call_voicevox_api(text: str, speaker_id: int = 1) -> Optional[bytes]:
    """
    VOICEVOX APIで音声合成
    
    Args:
        text: 読み上げるテキスト
        speaker_id: 話者ID
    
    Returns:
        音声データ（WAV形式）、失敗時はNone
    """
    base_url = "http://127.0.0.1:50021"
    
    try:
        async with aiohttp.ClientSession() as session:
            # タイムアウト: 合計30秒
            timeout = aiohttp.ClientTimeout(total=30.0)
            
            # 1. クエリ作成（タイムアウト: 10秒）
            query_timeout = aiohttp.ClientTimeout(total=10.0)
            async with session.post(
                f"{base_url}/audio_query",
                params={"text": text, "speaker": speaker_id},
                timeout=query_timeout
            ) as response:
                response.raise_for_status()
                query = await response.json()
            
            # 2. 音声合成（タイムアウト: 20秒）
            synthesis_timeout = aiohttp.ClientTimeout(total=20.0)
            async with session.post(
                f"{base_url}/synthesis",
                params={"speaker": speaker_id},
                json=query,
                timeout=synthesis_timeout
            ) as response:
                response.raise_for_status()
                return await response.read()
    
    except asyncio.TimeoutError:
        print("⏱️ VOICEVOX API timeout")
        return None
    
    except aiohttp.ClientError as e:
        print(f"❌ VOICEVOX API error: {e}")
        return None
```

**asyncio.wait_forを使用したタイムアウト**:

```python
async def fetch_with_timeout(url: str, timeout_seconds: float = 5.0) -> Optional[str]:
    """
    タイムアウト付きでデータを取得
    
    Args:
        url: 取得元URL
        timeout_seconds: タイムアウト秒数
    
    Returns:
        レスポンステキスト、タイムアウト時はNone
    """
    try:
        # asyncio.wait_forで全体のタイムアウトを制御
        result = await asyncio.wait_for(
            _fetch_internal(url),
            timeout=timeout_seconds
        )
        return result
    
    except asyncio.TimeoutError:
        print(f"⏱️ Timeout after {timeout_seconds}s")
        return None

async def _fetch_internal(url: str) -> str:
    """内部的なfetch処理"""
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.text()
```

---

### 3. リトライロジックの実装

一時的なエラーに対してはリトライを実装する。

**✅ 推奨パターン（デコレータ使用）**:

```python
import asyncio
import functools
from typing import TypeVar, Callable, Any

T = TypeVar('T')

def async_retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,)
):
    """
    非同期関数のリトライデコレータ
    
    Args:
        max_attempts: 最大試行回数
        delay: 初回リトライまでの待機時間（秒）
        backoff: 待機時間の倍率（指数バックオフ）
        exceptions: リトライ対象の例外タプル
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            current_delay = delay
            last_exception = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                
                except exceptions as e:
                    last_exception = e
                    
                    if attempt == max_attempts:
                        # 最大試行回数に到達
                        print(f"❌ Failed after {max_attempts} attempts: {e}")
                        raise
                    
                    # リトライ
                    print(f"⚠️ Attempt {attempt} failed, retrying in {current_delay}s... ({e})")
                    await asyncio.sleep(current_delay)
                    current_delay *= backoff
            
            # 到達しないが、型チェック用
            if last_exception:
                raise last_exception
        
        return wrapper
    return decorator

# 使用例
@async_retry(max_attempts=3, delay=1.0, backoff=2.0, exceptions=(aiohttp.ClientError,))
async def fetch_with_retry(url: str) -> dict:
    """リトライ付きでデータを取得"""
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            response.raise_for_status()
            return await response.json()
```

**✅ 推奨パターン（手動実装）**:

```python
async def connect_voice_channel_with_retry(
    channel: discord.VoiceChannel,
    max_attempts: int = 3
) -> Optional[discord.VoiceClient]:
    """
    リトライ付きでボイスチャンネルに接続
    
    Args:
        channel: 接続先のボイスチャンネル
        max_attempts: 最大試行回数
    
    Returns:
        VoiceClientオブジェクト、失敗時はNone
    """
    for attempt in range(1, max_attempts + 1):
        try:
            voice_client = await channel.connect()
            print(f"✅ Connected to {channel.name}")
            return voice_client
        
        except discord.ClientException as e:
            if attempt == max_attempts:
                print(f"❌ Failed to connect after {max_attempts} attempts: {e}")
                return None
            
            print(f"⚠️ Connection attempt {attempt} failed, retrying... ({e})")
            await asyncio.sleep(2.0 * attempt)  # 指数バックオフ
    
    return None
```

---

### 4. 複数の非同期タスクの管理

**asyncio.gather を使用した並行処理**:

```python
async def process_multiple_messages(messages: list[str]) -> list[Optional[bytes]]:
    """
    複数のメッセージを並行処理
    
    Args:
        messages: 処理するメッセージのリスト
    
    Returns:
        音声データのリスト（失敗時はNoneを含む）
    """
    # 並行処理（return_exceptions=True で例外を結果として返す）
    results = await asyncio.gather(
        *[create_audio_safe(msg) for msg in messages],
        return_exceptions=True
    )
    
    # 結果を処理
    audio_list = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            print(f"❌ Message {i} failed: {result}")
            audio_list.append(None)
        else:
            audio_list.append(result)
    
    return audio_list

async def create_audio_safe(text: str) -> Optional[bytes]:
    """エラーを適切に処理する音声生成関数"""
    try:
        return await create_audio(text)
    except Exception as e:
        print(f"❌ Audio creation failed: {e}")
        return None
```

**asyncio.create_task でバックグラウンド実行**:

```python
class VoiceBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.default())
        self.background_tasks: set[asyncio.Task] = set()
    
    def create_background_task(self, coro):
        """
        バックグラウンドタスクを作成
        
        Args:
            coro: コルーチンオブジェクト
        """
        task = asyncio.create_task(coro)
        
        # タスクのセットに追加（GC対策）
        self.background_tasks.add(task)
        
        # 完了時にセットから削除
        task.add_done_callback(self.background_tasks.discard)
        
        # エラーハンドリング
        task.add_done_callback(self._handle_task_result)
    
    def _handle_task_result(self, task: asyncio.Task):
        """タスクの結果を処理"""
        try:
            task.result()
        except asyncio.CancelledError:
            print("⚠️ Task was cancelled")
        except Exception as e:
            print(f"❌ Background task failed: {e}")
            import traceback
            traceback.print_exc()

# 使用例
bot = VoiceBot()

@bot.event
async def on_message(message: discord.Message):
    """メッセージ受信時"""
    if message.author.bot:
        return
    
    # バックグラウンドで音声を生成・再生
    bot.create_background_task(
        process_and_play_message(message)
    )
```

---

### 5. セッション管理のベストプラクティス

**ClientSessionの再利用**:

```python
class VoicevoxClient:
    """VOICEVOX Engine クライアント"""
    
    def __init__(self, base_url: str = "http://127.0.0.1:50021"):
        self.base_url = base_url
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def initialize(self):
        """セッションを初期化"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
            print("✅ VOICEVOX client session initialized")
    
    async def close(self):
        """セッションをクローズ"""
        if self.session and not self.session.closed:
            await self.session.close()
            print("✅ VOICEVOX client session closed")
    
    async def __aenter__(self):
        """Context manager entry"""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        await self.close()
    
    async def create_audio(self, text: str, speaker_id: int = 1) -> Optional[bytes]:
        """
        音声を生成
        
        Args:
            text: 読み上げるテキスト
            speaker_id: 話者ID
        
        Returns:
            音声データ、失敗時はNone
        """
        if not self.session or self.session.closed:
            print("❌ Session is not initialized")
            return None
        
        try:
            # クエリ作成
            timeout = aiohttp.ClientTimeout(total=10.0)
            async with self.session.post(
                f"{self.base_url}/audio_query",
                params={"text": text, "speaker": speaker_id},
                timeout=timeout
            ) as response:
                response.raise_for_status()
                query = await response.json()
            
            # 音声合成
            async with self.session.post(
                f"{self.base_url}/synthesis",
                params={"speaker": speaker_id},
                json=query,
                timeout=timeout
            ) as response:
                response.raise_for_status()
                return await response.read()
        
        except Exception as e:
            print(f"❌ Audio creation failed: {e}")
            return None

# 使用例
async def main():
    async with VoicevoxClient() as client:
        audio = await client.create_audio("こんにちは")
        if audio:
            print(f"✅ Audio created: {len(audio)} bytes")
```

---

### 6. Discord.py 固有のエラーハンドリング

**コマンドエラーハンドラー**:

```python
@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError
):
    """グローバルコマンドエラーハンドラー"""
    
    # 既に応答済みかチェック
    responded = interaction.response.is_done()
    
    if isinstance(error, app_commands.CommandOnCooldown):
        message = f"⏱️ クールダウン中です。{error.retry_after:.1f}秒後に再試行してください。"
    
    elif isinstance(error, app_commands.MissingPermissions):
        permissions = ", ".join(error.missing_permissions)
        message = f"❌ 必要な権限がありません: {permissions}"
    
    elif isinstance(error, app_commands.BotMissingPermissions):
        permissions = ", ".join(error.missing_permissions)
        message = f"❌ Botに必要な権限がありません: {permissions}"
    
    elif isinstance(error, app_commands.CheckFailure):
        message = "❌ このコマンドを実行する権限がありません。"
    
    else:
        # 予期しないエラー
        import traceback
        print(f"❌ Unexpected command error:")
        traceback.print_exc()
        message = "❌ コマンドの実行中にエラーが発生しました。"
    
    # 応答
    try:
        if responded:
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except discord.HTTPException as e:
        print(f"❌ Failed to send error message: {e}")
```

**イベントエラーハンドリング**:

```python
@bot.event
async def on_error(event_name: str, *args, **kwargs):
    """グローバルイベントエラーハンドラー"""
    import traceback
    import sys
    
    print(f"❌ Error in event '{event_name}':")
    traceback.print_exc()
    
    # 致命的なエラーの場合はログに記録して終了
    exc_type, exc_value, exc_traceback = sys.exc_info()
    if exc_type in (KeyboardInterrupt, SystemExit):
        raise
```

---

## エラーハンドリングチェックリスト

### 非同期関数実装時

- [ ] すべての外部API呼び出しにタイムアウトを設定
- [ ] try-exceptで適切な例外をキャッチ
- [ ] finallyでリソースをクリーンアップ
- [ ] ユーザーフレンドリーなエラーメッセージ
- [ ] エラーログを適切に出力
- [ ] 型ヒント付きでOptional[T]を返す（失敗時はNone）

### HTTP通信実装時

- [ ] `aiohttp.ClientTimeout` を設定
- [ ] `aiohttp.ClientError` をキャッチ
- [ ] `response.raise_for_status()` でステータスコードをチェック
- [ ] セッションを適切にクローズ（context managerまたはfinally）
- [ ] リトライロジックを実装（一時的なエラー用）

### Discord Bot実装時

- [ ] グローバルエラーハンドラー（`@bot.tree.error`, `@bot.event on_error`）を実装
- [ ] コマンド固有のエラーハンドラーを実装
- [ ] `interaction.response.is_done()` をチェック
- [ ] `ephemeral=True` でエラーメッセージを送信
- [ ] 接続エラー、権限エラーを適切に処理

### バックグラウンドタスク実装時

- [ ] `asyncio.create_task()` の結果を保持（GC対策）
- [ ] `task.add_done_callback()` でエラーをハンドリング
- [ ] キャンセル時の処理を実装
- [ ] シャットダウン時にタスクをキャンセル

---

## よくあるエラーと対処法

### 1. RuntimeError: Event loop is closed

**原因**: イベントループが既にクローズされている状態で非同期処理を実行

**対処法**:

```python
# ❌ 間違い
asyncio.run(main())
asyncio.run(another())  # Error: loop is closed

# ✅ 正しい
async def main():
    await something()
    await another()

asyncio.run(main())
```

### 2. Task was destroyed but it is pending

**原因**: `asyncio.create_task()` の結果を保持していない

**対処法**:

```python
# ❌ 間違い
asyncio.create_task(background_work())  # GCで回収される可能性

# ✅ 正しい
background_tasks = set()
task = asyncio.create_task(background_work())
background_tasks.add(task)
task.add_done_callback(background_tasks.discard)
```

### 3. ClientConnectorError: Cannot connect to host

**原因**: VOICEVOX Engineが起動していない、URLが間違っている

**対処法**:

```python
async def check_voicevox_health(url: str) -> bool:
    """VOICEVOX Engineの稼働状態をチェック"""
    try:
        async with aiohttp.ClientSession() as session:
            timeout = aiohttp.ClientTimeout(total=5.0)
            async with session.get(f"{url}/version", timeout=timeout) as response:
                return response.status == 200
    except aiohttp.ClientError:
        return False

# 使用例
if not await check_voicevox_health("http://127.0.0.1:50021"):
    print("❌ VOICEVOX Engine is not running")
    return
```

---

## 参考リソース

- [asyncio 公式ドキュメント](https://docs.python.org/ja/3/library/asyncio.html)
- [aiohttp 公式ドキュメント](https://docs.aiohttp.org/)
- [discord.py エラーハンドリング](https://discordpy.readthedocs.io/en/stable/ext/commands/commands.html#error-handling)
- [PEP 492 - Coroutines with async and await syntax](https://peps.python.org/pep-0492/)

---

## 関連スキル

- **discord-bot-dev**: Discord Bot開発のベストプラクティス
- **discord-test**: テスト実装でのモック使用方法
- **commit**: 変更のコミットワークフロー

---

**更新履歴**:
- 2026-03-26: 初版作成
