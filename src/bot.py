"""
Discord 読み上げBot - VOICEVOX連携
"""
import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import os
import json
from pathlib import Path
from dotenv import load_dotenv
from typing import Dict, Optional
import tempfile

from src.voicevox_client import VoicevoxClient

# 環境変数の読み込み
load_dotenv()

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
                    self.guild_configs = {int(k): v for k, v in config.get("guild_configs", {}).items()}
                    print(f"✓ 設定ファイルを読み込みました（ユーザー設定: {len(self.user_speakers)}件）")
            else:
                self.user_speakers = {}
                self.guild_configs = {}
                print("⚠ 設定ファイルが見つかりません。新規作成します。")
        except Exception as e:
            print(f"⚠ 設定ファイルの読み込みに失敗: {e}")
            self.user_speakers = {}
            self.guild_configs = {}
    
    def _save_config(self):
        """設定ファイルに保存する"""
        try:
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            config = {
                "user_speakers": {str(k): v for k, v in self.user_speakers.items()},
                "guild_configs": {str(k): v for k, v in self.guild_configs.items()}
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
            self.tree.copy_global_to(guild=TEST_GUILD)
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
        
        await interaction.response.send_message(f"✓ {channel.name} に参加しました！このチャンネルのメッセージを読み上げます。")
        
    except Exception as e:
        await interaction.response.send_message(f"エラーが発生しました: {e}", ephemeral=True)


@bot.tree.command(name="leave", description="ボイスチャンネルから退出します")
async def leave(interaction: discord.Interaction):
    """ボイスチャンネルから退出するコマンド"""
    
    if not interaction.guild.voice_client:
        await interaction.response.send_message("ボイスチャンネルに接続していません！", ephemeral=True)
        return
    
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
        
        await interaction.response.send_message("✓ ボイスチャンネルから退出しました")
        
    except Exception as e:
        await interaction.response.send_message(f"エラーが発生しました: {e}", ephemeral=True)


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
    
    guild_id = interaction.guild.id
    if guild_id not in bot.guild_configs:
        bot.guild_configs[guild_id] = {}
    
    bot.guild_configs[guild_id]["speed"] = speed
    await interaction.response.send_message(f"✓ 読み上げ速度を {speed} に設定しました", ephemeral=True)


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
    
    # 長すぎるメッセージは省略
    if len(text) > 100:
        text = text[:100] + "、以下省略"
    
    # ユーザーの話者IDを取得（未設定なら1）
    speaker_id = bot.user_speakers.get(message.author.id, 1)
    
    # 速度設定を取得（未設定なら1.0）
    speed = bot.guild_configs[guild_id].get("speed", 1.0)
    
    # キューに追加
    await bot.voice_queues[guild_id].put({
        "text": text,
        "speaker_id": speaker_id,
        "speed": speed
    })
    
    # 再生タスクを開始（まだ開始していない場合）
    if not bot.is_playing.get(guild_id, False):
        bot.loop.create_task(play_voice_queue(message.guild))


async def play_voice_queue(guild: discord.Guild):
    """音声キューを再生するタスク"""
    guild_id = guild.id
    bot.is_playing[guild_id] = True
    
    try:
        while True:
            # キューが空なら終了
            if bot.voice_queues[guild_id].empty():
                break
            
            # キューからアイテムを取得
            item = await bot.voice_queues[guild_id].get()
            
            # 音声データを生成
            audio_data = await bot.voicevox.create_audio(
                text=item["text"],
                speaker_id=item["speaker_id"],
                speed=item["speed"]
            )
            
            if not audio_data:
                continue
            
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
