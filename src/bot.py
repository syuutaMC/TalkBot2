"""
Discord 読み上げBot - VOICEVOX連携
"""
import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import os
import json
import re
from pathlib import Path
from dotenv import load_dotenv
from typing import Dict, Optional, Set
import tempfile

import time

from src.voicevox_client import VoicevoxClient
from src import metrics

# 環境変数の読み込み
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

# 設定
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
VOICEVOX_URL = os.getenv("VOICEVOX_URL", "http://127.0.0.1:50021")
CONFIG_FILE = Path("config/config.json")

# テスト用のギルドID（環境変数から取得、未設定の場合はNone）
# 特定のギルドでのみコマンドを使いたい場合は、ここにギルドIDを設定
GUILD_ID = os.getenv("DISCORD_GUILD_ID")
TEST_GUILD = discord.Object(id=int(GUILD_ID)) if GUILD_ID else None

# Intentsの設定
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.voice_states = True


class DictionaryListView(discord.ui.View):
    """辞書一覧のページネーションビュー"""

    PER_PAGE = 20

    def __init__(self, entries: list):
        super().__init__(timeout=60)
        self.entries = entries
        self.page = 0
        self.total_pages = max(1, (len(entries) + self.PER_PAGE - 1) // self.PER_PAGE)
        self._update_buttons()

    def _update_buttons(self):
        self.prev_button.disabled = self.page == 0
        self.next_button.disabled = self.page >= self.total_pages - 1

    def _build_embed(self) -> discord.Embed:
        start = self.page * self.PER_PAGE
        end = min(start + self.PER_PAGE, len(self.entries))
        page_entries = self.entries[start:end]

        embed = discord.Embed(title="📖 読み上げ辞書一覧", color=discord.Color.blue())
        if page_entries:
            embed.description = "\n".join(f"`{b}` → `{a}`" for b, a in page_entries)
        else:
            embed.description = "辞書が空です"
        embed.set_footer(text=f"ページ {self.page + 1}/{self.total_pages}（全{len(self.entries)}件）")
        return embed

    @discord.ui.button(label="◀ 前へ", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

    @discord.ui.button(label="次へ ▶", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self._build_embed(), view=self)


class VoiceBot(commands.Bot):
    """読み上げBot本体"""
    
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.voicevox = VoicevoxClient(VOICEVOX_URL)
        
        # 設定ファイルから読み込み
        self._load_config()
        
        # 読み上げキュー
        self.voice_queues: Dict[int, asyncio.Queue] = {}
        # 音声再生中フラグ
        self.is_playing: Dict[int, bool] = {}
    
    def _load_config(self):
        """設定ファイルを読み込む"""
        try:
            if CONFIG_FILE.exists():
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    # 文字列キーを整数に変換
                    self.user_speakers = {int(k): v for k, v in config.get("user_speakers", {}).items()}
                    self.user_speeds = {int(k): v for k, v in config.get("user_speeds", {}).items()}
                    self.guild_configs = {int(k): v for k, v in config.get("guild_configs", {}).items()}
                    self.joined_guilds: Set[int] = set(config.get("joined_guilds", []))
                    total_dict = sum(len(gc.get("dictionary", {})) for gc in self.guild_configs.values())
                    print(f"✓ 設定ファイルを読み込みました（話者設定: {len(self.user_speakers)}件、速度設定: {len(self.user_speeds)}件、辞書: {total_dict}件）")
            else:
                self.user_speakers = {}
                self.user_speeds = {}
                self.guild_configs = {}
                self.joined_guilds: Set[int] = set()
                print("⚠ 設定ファイルが見つかりません。新規作成します。")
        except Exception as e:
            print(f"⚠ 設定ファイルの読み込みに失敗: {e}")
            self.user_speakers = {}
            self.user_speeds = {}
            self.guild_configs = {}
            self.joined_guilds: Set[int] = set()
    
    def _save_config(self):
        """設定ファイルに保存する"""
        try:
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            config = {
                "user_speakers": {str(k): v for k, v in self.user_speakers.items()},
                "user_speeds": {str(k): v for k, v in self.user_speeds.items()},
                "guild_configs": {str(k): v for k, v in self.guild_configs.items()},
                "joined_guilds": list(self.joined_guilds),
            }
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"⚠ 設定ファイルの保存に失敗: {e}")
    
    async def setup_hook(self):
        """Bot起動時の初期化処理"""
        await self.voicevox.initialize()
        
        # VOICEVOX Engineの接続確認
        if await self.voicevox.is_available():
            print("✓ VOICEVOX Engineに接続しました")
        else:
            print("⚠ VOICEVOX Engineに接続できません。起動していることを確認してください。")
        
        # コマンドの同期
        if TEST_GUILD:
            # 特定のギルドにのみコマンドを同期（即座に反映）
            # まずグローバルコマンドをギルドにコピーしてからグローバルをクリアする
            # これにより、以前グローバルに同期された古いコマンドが残らないようにする
            self.tree.copy_global_to(guild=TEST_GUILD)
            self.tree.clear_commands(guild=None)
            await self.tree.sync()
            await self.tree.sync(guild=TEST_GUILD)
            print(f"✓ スラッシュコマンドをギルド {TEST_GUILD.id} に同期しました（即座に反映）")
        else:
            # 全ギルドに同期（グローバル、反映に最大1時間）
            await self.tree.sync()
            print("✓ スラッシュコマンドをグローバルに同期しました（反映に最大1時間）")
    
    async def close(self):
        """Bot終了時の処理"""
        await self.voicevox.close()
        await super().close()


# Botインスタンスの作成
bot = VoiceBot()


@bot.event
async def on_ready():
    """Bot起動完了時のイベント"""
    print(f"✓ {bot.user.name} としてログインしました")
    print(f"✓ Bot ID: {bot.user.id}")
    print("=" * 50)
    # 現在参加しているサーバー一覧で joined_guilds を同期して保存
    bot.joined_guilds = {g.id for g in bot.guilds}
    bot._save_config()


@bot.event
async def on_guild_join(guild: discord.Guild):
    """Bot が新しいサーバーに参加したときのイベント"""
    bot.joined_guilds.add(guild.id)
    bot._save_config()


@bot.event
async def on_guild_remove(guild: discord.Guild):
    """Bot がサーバーから退出・削除されたときのイベント"""
    guild_id = guild.id
    bot.joined_guilds.discard(guild_id)
    bot.guild_configs.pop(guild_id, None)
    bot.voice_queues.pop(guild_id, None)
    bot.is_playing.pop(guild_id, None)
    bot._save_config()


@bot.tree.command(name="join", description="ボイスチャンネルに参加します")
async def join(interaction: discord.Interaction):
    """ボイスチャンネルに参加するコマンド"""
    
    # ユーザーがボイスチャンネルに接続しているか確認
    if not interaction.user.voice:
        await interaction.response.send_message("先にボイスチャンネルに接続してください！", ephemeral=True)
        return
    
    channel = interaction.user.voice.channel
    guild_id = interaction.guild.id
    
    # 既に接続している場合
    if interaction.guild.voice_client:
        await interaction.response.send_message("既にボイスチャンネルに接続しています！", ephemeral=True)
        return
    
    # 接続に時間がかかる場合でもインタラクションが失効しないよう defer する
    await interaction.response.defer()
    
    try:
        # ボイスチャンネルに接続
        await channel.connect()
        
        # ギルドの設定を初期化
        if guild_id not in bot.guild_configs:
            bot.guild_configs[guild_id] = {
                "read_channel": interaction.channel.id  # 現在のチャンネルを読み上げ対象に
            }
            bot.voice_queues[guild_id] = asyncio.Queue()
            bot.is_playing[guild_id] = False
            bot._save_config()
        
        metrics.record_command("join")
        await interaction.followup.send(f"✓ {channel.name} に参加しました！このチャンネルのメッセージを読み上げます。")
        
    except Exception as e:
        await interaction.followup.send(f"エラーが発生しました: {e}", ephemeral=True)


@bot.tree.command(name="leave", description="ボイスチャンネルから退出します")
async def leave(interaction: discord.Interaction):
    """ボイスチャンネルから退出するコマンド"""
    
    if not interaction.guild.voice_client:
        await interaction.response.send_message("ボイスチャンネルに接続していません！", ephemeral=True)
        return
    
    # 切断に時間がかかる場合でもインタラクションが失効しないよう defer する
    await interaction.response.defer()
    
    try:
        await interaction.guild.voice_client.disconnect()
        
        # ギルドの設定をクリーン
        guild_id = interaction.guild.id
        if guild_id in bot.guild_configs:
            del bot.guild_configs[guild_id]
        if guild_id in bot.voice_queues:
            del bot.voice_queues[guild_id]
        if guild_id in bot.is_playing:
            del bot.is_playing[guild_id]
        bot._save_config()
        
        metrics.record_command("leave")
        await interaction.followup.send("✓ ボイスチャンネルから退出しました")
        
    except Exception as e:
        await interaction.followup.send(f"エラーが発生しました: {e}", ephemeral=True)


@bot.tree.command(name="help", description="使い方と話者一覧を表示します")
async def help_command(interaction: discord.Interaction):
    """ヘルプと話者一覧を表示するコマンド"""
    
    await interaction.response.defer(ephemeral=True)
    
    # 基本的な使い方
    help_text = """**📢 Discord読み上げBot - 使い方**

**基本コマンド:**
• `/join` - ボイスチャンネルに参加
• `/leave` - ボイスチャンネルから退出
• `/voice <番号>` - 読み上げ音声を変更（下の一覧から選択）
• `/speed <数値>` - 読み上げ速度を設定（0.5〜2.0）
• `/speakers` - 詳細な話者一覧を表示
• `/help` - このヘルプを表示

**使い方:**
1. `/join` でボイスチャンネルに参加
2. テキストチャンネルにメッセージを送ると自動で読み上げ
3. `/voice <番号>` で自分の声を変更できます

"""
    
    # 話者一覧を取得
    speakers_list = await bot.voicevox.get_speakers()
    
    if speakers_list:
        help_text += "**🎭 主な話者一覧（番号で指定）:**\n\n"
        
        # 話者をID順にソート
        all_styles = []
        for speaker in speakers_list:
            speaker_name = speaker.get("name", "不明")
            for style in speaker.get("styles", []):
                style_name = style.get("name", "")
                style_id = style.get("id", 0)
                all_styles.append((style_id, speaker_name, style_name))
        
        all_styles.sort(key=lambda x: x[0])
        
        # 番号付きで表示
        for style_id, speaker_name, style_name in all_styles:
            help_text += f"`{style_id:2d}` - **{speaker_name}** ({style_name})\n"
        
        help_text += "\n💡 例: `/voice 3` で「ずんだもん（ノーマル）」に変更"
    else:
        help_text += "⚠ 話者一覧を取得できませんでした。VOICEVOX Engineが起動しているか確認してください。"
    
    metrics.record_command("help")
    # メッセージが長すぎる場合は分割
    if len(help_text) > 2000:
        chunks = []
        current_chunk = ""
        for line in help_text.split("\n"):
            if len(current_chunk) + len(line) + 1 > 2000:
                chunks.append(current_chunk)
                current_chunk = line + "\n"
            else:
                current_chunk += line + "\n"
        if current_chunk:
            chunks.append(current_chunk)
        
        for i, chunk in enumerate(chunks):
            await interaction.followup.send(chunk, ephemeral=True)
    else:
        await interaction.followup.send(help_text, ephemeral=True)


@bot.tree.command(name="voice", description="読み上げ音声を変更します")
@app_commands.describe(speaker_id="話者ID（1-60程度、詳細は/helpで確認）")
async def voice(interaction: discord.Interaction, speaker_id: int):
    """ユーザーごとの読み上げ音声を設定するコマンド"""
    
    if speaker_id < 0:
        await interaction.response.send_message("話者IDは0以上を指定してください", ephemeral=True)
        return
    
    bot.user_speakers[interaction.user.id] = speaker_id
    bot._save_config()  # 設定を保存
    metrics.record_command("voice")
    await interaction.response.send_message(f"✓ あなたの読み上げ音声を話者ID {speaker_id} に設定しました", ephemeral=True)


@bot.tree.command(name="speakers", description="利用可能な話者一覧を表示します")
async def speakers(interaction: discord.Interaction):
    """話者一覧を表示するコマンド"""
    
    await interaction.response.defer(ephemeral=True)
    
    speakers_list = await bot.voicevox.get_speakers()
    
    if not speakers_list:
        await interaction.followup.send("話者一覧を取得できませんでした。VOICEVOX Engineが起動しているか確認してください。", ephemeral=True)
        return
    
    # 話者情報を整形
    message = "**利用可能な話者一覧**\n\n"
    for speaker in speakers_list:
        speaker_name = speaker.get("name", "不明")
        for style in speaker.get("styles", []):
            style_name = style.get("name", "")
            style_id = style.get("id", 0)
            message += f"• **{speaker_name}** - {style_name} (ID: `{style_id}`)\n"
    
    metrics.record_command("speakers")
    # メッセージが長すぎる場合は分割
    if len(message) > 2000:
        chunks = [message[i:i+2000] for i in range(0, len(message), 2000)]
        for chunk in chunks:
            await interaction.followup.send(chunk, ephemeral=True)
    else:
        await interaction.followup.send(message, ephemeral=True)


@bot.tree.command(name="speed", description="読み上げ速度を設定します")
@app_commands.describe(speed="読み上げ速度（0.5〜2.0、デフォルト1.0）")
async def speed(interaction: discord.Interaction, speed: float):
    """読み上げ速度を設定するコマンド"""
    
    if speed < 0.5 or speed > 2.0:
        await interaction.response.send_message("速度は0.5〜2.0の範囲で指定してください", ephemeral=True)
        return
    
    bot.user_speeds[interaction.user.id] = speed
    bot._save_config()  # 設定を保存
    metrics.record_command("speed")
    await interaction.response.send_message(f"✓ あなたの読み上げ速度を {speed} に設定しました", ephemeral=True)


@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    """ボイスチャンネルの状態が変更されたときのイベント"""
    
    # Botのボイスクライアントを取得
    voice_client = member.guild.voice_client
    
    # Botがボイスチャンネルに接続していない場合は何もしない
    if not voice_client:
        return
    
    # Botが接続しているチャンネルを取得
    bot_channel = voice_client.channel
    
    # メンバーがBotのいるチャンネルから退出した場合のみチェック
    if before.channel == bot_channel:
        # Bot以外のメンバー数をカウント
        human_members = [m for m in bot_channel.members if not m.bot]
        
        # Bot以外のメンバーがいなくなった場合、自動で退出
        if len(human_members) == 0:
            print(f"✓ {member.guild.name} のボイスチャンネルにメンバーがいなくなったため、自動退出します")
            await voice_client.disconnect()
            
            # ギルドの設定をクリーンアップ
            guild_id = member.guild.id
            if guild_id in bot.guild_configs:
                del bot.guild_configs[guild_id]
            if guild_id in bot.voice_queues:
                del bot.voice_queues[guild_id]
            if guild_id in bot.is_playing:
                del bot.is_playing[guild_id]
            bot._save_config()


@bot.event
async def on_message(message: discord.Message):
    """メッセージ受信時のイベント"""
    
    # Botのメッセージは無視
    if message.author.bot:
        return
    
    # コマンドの処理
    await bot.process_commands(message)
    
    # ギルドのメッセージでない場合は無視
    if not message.guild:
        return
    
    guild_id = message.guild.id
    
    # ボイスチャンネルに接続していない場合は無視
    if not message.guild.voice_client:
        return
    
    # 読み上げ対象チャンネルでない場合は無視
    if guild_id not in bot.guild_configs:
        return
    if bot.guild_configs[guild_id].get("read_channel") != message.channel.id:
        return
    
    # メッセージを読み上げキューに追加
    text = message.clean_content
    
    # URLや特殊文字の処理
    if not text or text.startswith(("http://", "https://")):
        text = "URL省略"
    
    # 辞書による変換（最長一致・単一パスで多重置換を防ぐ）
    guild_dict = bot.guild_configs.get(guild_id, {}).get("dictionary", {})
    if guild_dict:
        pattern = "|".join(
            re.escape(k) for k in sorted(guild_dict.keys(), key=len, reverse=True)
        )
        text = re.sub(pattern, lambda m: guild_dict[m.group(0)], text)
    
    # 長すぎるメッセージは省略
    if len(text) > 500:
        text = text[:500] + "、以下省略"
    
    # ユーザーの話者IDを取得（未設定なら1）
    speaker_id = bot.user_speakers.get(message.author.id, 1)
    
    # ユーザーの速度設定を取得（未設定なら1.0）
    speed = bot.user_speeds.get(message.author.id, 1.0)
    
    # キューに追加（未初期化の場合は初期化する）
    if guild_id not in bot.voice_queues:
        bot.voice_queues[guild_id] = asyncio.Queue()
    await bot.voice_queues[guild_id].put({
        "text": text,
        "speaker_id": speaker_id,
        "speed": speed
    })
    
    # 再生タスクを開始（まだ開始していない場合）
    # create_task() はコルーチンをスケジュールするだけで即座には実行しないため、
    # is_playing を True に設定してから create_task() を呼ぶことで
    # 同一ギルドに対して複数タスクが起動されるのを防ぐ
    if not bot.is_playing.get(guild_id, False):
        bot.is_playing[guild_id] = True
        bot.loop.create_task(play_voice_queue(message.guild))


async def play_voice_queue(guild: discord.Guild):
    """音声キューを再生するタスク"""
    guild_id = guild.id
    bot.is_playing[guild_id] = True
    
    try:
        while True:
            # ギルドが切断済みの場合（/leave や自動退出でキューが削除された）は終了
            if guild_id not in bot.voice_queues:
                break

            # キューが空なら終了
            if bot.voice_queues[guild_id].empty():
                break
            
            # キューからアイテムを取得
            item = await bot.voice_queues[guild_id].get()
            
            # 音声データを生成（レイテンシを計測）
            start_time = time.monotonic()
            audio_data = await bot.voicevox.create_audio(
                text=item["text"],
                speaker_id=item["speaker_id"],
                speed=item["speed"]
            )
            elapsed_ms = (time.monotonic() - start_time) * 1000
            
            if not audio_data:
                metrics.record_error()
                continue
            
            metrics.record_latency(elapsed_ms)
            metrics.record_tts_request()

            # 一時ファイルに保存
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                temp_file.write(audio_data)
                temp_path = temp_file.name
            
            try:
                # 音声を再生
                voice_client = guild.voice_client
                if voice_client and voice_client.is_connected():
                    audio_source = discord.FFmpegPCMAudio(temp_path)
                    voice_client.play(audio_source)
                    
                    # 再生が終わるまで待機
                    while voice_client.is_playing():
                        await asyncio.sleep(0.1)
                
            finally:
                # 一時ファイルを削除
                try:
                    os.unlink(temp_path)
                except:
                    pass
            
            # 次の再生まで少し待つ
            await asyncio.sleep(0.5)
    
    finally:
        bot.is_playing[guild_id] = False


# 辞書コマンドグループ
dictionary_group = app_commands.Group(name="dictionary", description="読み上げ辞書の管理")


def _ensure_guild_dictionary(guild_id: int) -> Dict[str, str]:
    """ギルド固有の辞書を返す（存在しない場合は初期化して返す）"""
    if guild_id not in bot.guild_configs:
        bot.guild_configs[guild_id] = {}
    if "dictionary" not in bot.guild_configs[guild_id]:
        bot.guild_configs[guild_id]["dictionary"] = {}
    return bot.guild_configs[guild_id]["dictionary"]


@dictionary_group.command(name="add", description="読み上げ辞書に登録します")
@app_commands.describe(before="変換前のテキスト", after="変換後のテキスト")
async def dictionary_add(interaction: discord.Interaction, before: str, after: str):
    """辞書登録コマンド: before を after に変換する"""
    if not interaction.guild:
        await interaction.response.send_message("⚠ このコマンドはサーバー内でのみ使用できます", ephemeral=True)
        return
    guild_id = interaction.guild.id
    _ensure_guild_dictionary(guild_id)[before] = after
    bot._save_config()
    metrics.record_command("dictionary_add")
    await interaction.response.send_message(f"✓ 辞書に登録しました: `{before}` → `{after}`", ephemeral=True)


@dictionary_group.command(name="remove", description="読み上げ辞書から削除します")
@app_commands.describe(before="削除する変換前テキスト")
async def dictionary_remove(interaction: discord.Interaction, before: str):
    """辞書削除コマンド: before の読み方でヒットする場合は削除する"""
    if not interaction.guild:
        await interaction.response.send_message("⚠ このコマンドはサーバー内でのみ使用できます", ephemeral=True)
        return
    guild_id = interaction.guild.id
    guild_dict = _ensure_guild_dictionary(guild_id)
    if before in guild_dict:
        del guild_dict[before]
        bot._save_config()
        metrics.record_command("dictionary_remove")
        await interaction.response.send_message(f"✓ 辞書から削除しました: `{before}`", ephemeral=True)
    else:
        await interaction.response.send_message(f"⚠ `{before}` は辞書に登録されていません", ephemeral=True)


@dictionary_group.command(name="list", description="辞書の一覧を表示します（20件ずつ）")
async def dictionary_list(interaction: discord.Interaction):
    """辞書一覧表示コマンド（ページネーションUI付き）"""
    if not interaction.guild:
        await interaction.response.send_message("⚠ このコマンドはサーバー内でのみ使用できます", ephemeral=True)
        return
    guild_id = interaction.guild.id
    guild_dict = _ensure_guild_dictionary(guild_id)
    entries = list(guild_dict.items())
    view = DictionaryListView(entries)
    metrics.record_command("dictionary_list")
    await interaction.response.send_message(embed=view._build_embed(), view=view, ephemeral=True)


bot.tree.add_command(dictionary_group)


def main():
    """メイン関数"""
    if not DISCORD_TOKEN:
        print("エラー: DISCORD_TOKENが設定されていません")
        print(".envファイルを作成し、DISCORD_TOKENを設定してください")
        return
    
    print("=" * 50)
    print("Discord 読み上げBot 起動中...")
    print("=" * 50)
    
    try:
        bot.run(DISCORD_TOKEN)
    except discord.LoginFailure:
        print("エラー: Discord Tokenが無効です")
    except Exception as e:
        print(f"エラーが発生しました: {e}")


if __name__ == "__main__":
    main()
