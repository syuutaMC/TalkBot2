---
name: discord-bot-dev
description: Discord.pyを使用したBot開発のベストプラクティスとパターン。スラッシュコマンド、音声処理、イベントハンドリングの実装ガイド
compatibility: Designed for GitHub Copilot CLI
metadata:
  author: TalkBot2 Project
  version: "1.0"
  original-source: https://github.com/syuutaMC
---

# Discord Bot Development Skill

このスキルは、discord.pyを使用したDiscord Bot開発における実装パターンとベストプラクティスを提供します。

## スキルの対象

- **対象ファイル**: `src/bot.py`, `src/**/*.py`
- **対象タスク**: Bot機能の実装、コマンド追加、イベントハンドリング、音声処理
- **前提知識**: discord.py 2.0+, async/await, Python 3.9+

---

## 開発原則

### 1. スラッシュコマンド優先

discord.py 2.0以降では、スラッシュコマンド（`app_commands`）を優先的に使用する。

**✅ 推奨パターン**:

```python
from discord import app_commands
from discord.ext import commands
import discord

class VoiceBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.voice_states = True
        super().__init__(command_prefix="!", intents=intents)
    
    async def setup_hook(self):
        """Bot起動時の初期化処理"""
        # スラッシュコマンドを同期
        await self.tree.sync()

# スラッシュコマンドの定義
@app_commands.command(name="join", description="ボイスチャンネルに参加します")
@app_commands.describe(channel="参加するボイスチャンネル（省略時は現在のチャンネル）")
async def join(
    interaction: discord.Interaction,
    channel: Optional[discord.VoiceChannel] = None
):
    """ボイスチャンネルに参加するコマンド"""
    target_channel = channel or interaction.user.voice.channel
    
    if not target_channel:
        await interaction.response.send_message(
            "❌ ボイスチャンネルに接続していません。",
            ephemeral=True
        )
        return
    
    try:
        await target_channel.connect()
        await interaction.response.send_message(
            f"✅ {target_channel.name} に参加しました！"
        )
    except discord.ClientException as e:
        await interaction.response.send_message(
            f"❌ 接続に失敗しました: {e}",
            ephemeral=True
        )
```

**❌ 避けるべきパターン** (prefix commands):

```python
# discord.py 2.0以降では非推奨
@bot.command()
async def join(ctx):
    # prefix command (!join) は使用しない
    pass
```

---

### 2. Intents設定の最小化

必要なIntentsのみを有効化し、セキュリティとパフォーマンスを向上させる。

**✅ 推奨パターン**:

```python
import discord

# 必要最小限のIntents
intents = discord.Intents.default()
intents.message_content = True  # メッセージ読み上げに必要
intents.voice_states = True     # 音声チャンネル参加/退出の検知に必要
intents.guilds = True           # サーバー情報取得に必要（default に含まれる）

# 不要なIntentsは明示的に無効化
intents.presences = False       # プレゼンス情報は不要
intents.members = False         # メンバー情報は不要（特権Intent）

bot = commands.Bot(command_prefix="!", intents=intents)
```

**❌ 避けるべきパターン**:

```python
# すべてのIntentsを有効化（不要な権限を要求）
intents = discord.Intents.all()
```

---

### 3. 権限チェックの実装

コマンド実行前に必要な権限をチェックし、明確なエラーメッセージを返す。

**✅ 推奨パターン**:

```python
@app_commands.command(name="clear_queue", description="再生キューをクリアします")
@app_commands.checks.has_permissions(manage_messages=True)
async def clear_queue(interaction: discord.Interaction):
    """キューをクリアするコマンド（メッセージ管理権限が必要）"""
    if not interaction.guild:
        await interaction.response.send_message(
            "❌ このコマンドはサーバー内でのみ使用できます。",
            ephemeral=True
        )
        return
    
    # キューをクリア
    queue.clear()
    await interaction.response.send_message("✅ キューをクリアしました。")

# エラーハンドリング
@clear_queue.error
async def clear_queue_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    """権限エラーを適切に処理"""
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "❌ このコマンドを実行する権限がありません。\n"
            "必要な権限: メッセージの管理",
            ephemeral=True
        )
```

---

### 4. 音声処理の実装パターン

**音声キューの管理**:

```python
import asyncio
from collections import deque
from typing import Optional, Deque

class VoiceQueue:
    """音声再生キューの管理"""
    
    def __init__(self):
        self.queue: Deque[bytes] = deque()
        self.is_playing: bool = False
        self.voice_client: Optional[discord.VoiceClient] = None
    
    async def add(self, audio_data: bytes):
        """キューに音声を追加"""
        self.queue.append(audio_data)
        if not self.is_playing:
            await self.process_queue()
    
    async def process_queue(self):
        """キューを順次処理"""
        while self.queue and self.voice_client and self.voice_client.is_connected():
            self.is_playing = True
            audio_data = self.queue.popleft()
            
            # 音声を再生
            await self.play_audio(audio_data)
            
            # 再生完了まで待機
            while self.voice_client.is_playing():
                await asyncio.sleep(0.1)
        
        self.is_playing = False
    
    async def play_audio(self, audio_data: bytes):
        """音声データを再生"""
        import io
        import discord
        
        # BytesIOからFFmpegPCMAudioを作成
        audio_source = discord.FFmpegPCMAudio(
            io.BytesIO(audio_data),
            pipe=True,
            options="-f wav"
        )
        
        self.voice_client.play(audio_source)
    
    async def cleanup(self):
        """リソースのクリーンアップ"""
        self.queue.clear()
        self.is_playing = False
        if self.voice_client and self.voice_client.is_connected():
            await self.voice_client.disconnect()
```

**音声イベントのハンドリング**:

```python
@bot.event
async def on_voice_state_update(
    member: discord.Member,
    before: discord.VoiceState,
    after: discord.VoiceState
):
    """ボイスチャンネルの状態変化を検知"""
    
    # Bot自身の状態変化は無視
    if member.bot:
        return
    
    # ユーザーがチャンネルから退出した場合
    if before.channel and not after.channel:
        # 誰もいなくなったらBotも退出
        if before.channel.members and len(before.channel.members) == 1:
            voice_client = discord.utils.get(bot.voice_clients, channel=before.channel)
            if voice_client:
                await voice_client.disconnect()
```

---

### 5. エラーハンドリング

**グローバルエラーハンドラー**:

```python
@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError
):
    """スラッシュコマンドのグローバルエラーハンドラー"""
    
    if isinstance(error, app_commands.CommandOnCooldown):
        await interaction.response.send_message(
            f"⏱️ クールダウン中です。{error.retry_after:.1f}秒後に再試行してください。",
            ephemeral=True
        )
    elif isinstance(error, app_commands.MissingPermissions):
        permissions = ", ".join(error.missing_permissions)
        await interaction.response.send_message(
            f"❌ 必要な権限がありません: {permissions}",
            ephemeral=True
        )
    elif isinstance(error, app_commands.BotMissingPermissions):
        permissions = ", ".join(error.missing_permissions)
        await interaction.response.send_message(
            f"❌ Botに必要な権限がありません: {permissions}",
            ephemeral=True
        )
    else:
        # 予期しないエラー
        import traceback
        print(f"Unexpected error: {error}")
        traceback.print_exc()
        
        await interaction.response.send_message(
            "❌ コマンドの実行中にエラーが発生しました。",
            ephemeral=True
        )
```

---

### 6. イベントハンドリングのベストプラクティス

**Bot起動イベント**:

```python
@bot.event
async def on_ready():
    """Bot起動時の処理"""
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print(f"Connected to {len(bot.guilds)} guilds")
    
    # ステータスを設定
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.listening,
            name="メッセージを読み上げ中"
        )
    )
```

**メッセージイベント**:

```python
@bot.event
async def on_message(message: discord.Message):
    """メッセージ受信時の処理"""
    
    # Bot自身のメッセージは無視
    if message.author.bot:
        return
    
    # DMは無視
    if not message.guild:
        return
    
    # システムメッセージは無視
    if message.type != discord.MessageType.default:
        return
    
    # ボイスチャンネルに接続しているかチェック
    voice_client = message.guild.voice_client
    if not voice_client or not voice_client.is_connected():
        return
    
    # メッセージを読み上げ
    await read_message(message)
```

---

## 実装チェックリスト

### コマンド実装時

- [ ] `@app_commands.command()` デコレータを使用
- [ ] コマンドに `name` と `description` を指定
- [ ] すべてのパラメータに `@app_commands.describe()` で説明を追加
- [ ] 型ヒントをすべてのパラメータに付与
- [ ] 権限チェックを実装（必要な場合）
- [ ] エラーハンドラーを実装
- [ ] `ephemeral=True` を適切に使用（エラーメッセージなど）
- [ ] ユーザーフレンドリーなメッセージ（絵文字、明確な説明）

### 音声処理実装時

- [ ] 音声キューを実装
- [ ] 複数の音声を順次再生できる
- [ ] 再生完了を適切に待機
- [ ] 切断時のクリーンアップ処理を実装
- [ ] ユーザーが誰もいなくなったら自動切断
- [ ] FFmpegの依存関係を確認

### テスト実装時

- [ ] Discord API をモック化
- [ ] 音声処理をモック化
- [ ] 各コマンドの成功ケースをテスト
- [ ] エラーケースをテスト（権限不足、接続失敗など）
- [ ] エッジケース（空のキュー、既に接続済みなど）をテスト

---

## コード例

### 完全なコマンド実装例

```python
# src/bot.py

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
import asyncio
from collections import deque

class VoiceBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.voice_states = True
        
        super().__init__(command_prefix="!", intents=intents)
        
        # 音声キュー
        self.voice_queue: dict[int, deque] = {}  # guild_id -> deque
    
    async def setup_hook(self):
        """初期化処理"""
        await self.tree.sync()

bot = VoiceBot()

@bot.tree.command(name="join", description="ボイスチャンネルに参加します")
@app_commands.describe(channel="参加するボイスチャンネル（省略時は現在のチャンネル）")
async def join(
    interaction: discord.Interaction,
    channel: Optional[discord.VoiceChannel] = None
):
    """ボイスチャンネル参加コマンド"""
    # チャンネル判定
    target_channel = channel or getattr(interaction.user.voice, "channel", None)
    
    if not target_channel:
        await interaction.response.send_message(
            "❌ ボイスチャンネルに接続していないか、チャンネルを指定してください。",
            ephemeral=True
        )
        return
    
    # 既に接続済みの場合
    if interaction.guild.voice_client:
        if interaction.guild.voice_client.channel == target_channel:
            await interaction.response.send_message(
                f"✅ 既に {target_channel.name} に接続しています。",
                ephemeral=True
            )
            return
        else:
            # 別のチャンネルに移動
            await interaction.guild.voice_client.move_to(target_channel)
            await interaction.response.send_message(
                f"🔄 {target_channel.name} に移動しました。"
            )
            return
    
    # 接続
    try:
        await target_channel.connect()
        await interaction.response.send_message(
            f"✅ {target_channel.name} に参加しました！"
        )
    except discord.ClientException as e:
        await interaction.response.send_message(
            f"❌ 接続に失敗しました: {e}",
            ephemeral=True
        )

@bot.tree.command(name="leave", description="ボイスチャンネルから退出します")
async def leave(interaction: discord.Interaction):
    """ボイスチャンネル退出コマンド"""
    if not interaction.guild.voice_client:
        await interaction.response.send_message(
            "❌ ボイスチャンネルに接続していません。",
            ephemeral=True
        )
        return
    
    # キューをクリア
    if interaction.guild.id in bot.voice_queue:
        bot.voice_queue[interaction.guild.id].clear()
    
    # 切断
    await interaction.guild.voice_client.disconnect()
    await interaction.response.send_message("👋 ボイスチャンネルから退出しました。")

@bot.event
async def on_ready():
    """Bot起動時"""
    print(f"✅ Logged in as {bot.user}")
    print(f"📊 Connected to {len(bot.guilds)} guilds")

if __name__ == "__main__":
    import os
    bot.run(os.getenv("DISCORD_TOKEN"))
```

---

## 参考リソース

- [discord.py 公式ドキュメント](https://discordpy.readthedocs.io/)
- [discord.py GitHub リポジトリ](https://github.com/Rapptz/discord.py)
- [Discord Developer Portal](https://discord.com/developers/docs)
- [app_commands ガイド](https://discordpy.readthedocs.io/en/stable/interactions/api.html)

---

## 関連スキル

- **discord-test**: Discord Botのテスト作成ガイドライン
- **async-error-handling**: 非同期エラーハンドリングのベストプラクティス
- **commit**: Git コミットのワークフロー

---

**更新履歴**:
- 2026-03-26: 初版作成
