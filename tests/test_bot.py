"""
VoiceBot の setup_hook におけるスラッシュコマンド同期のテスト

更新時に古いコマンドが残らないことを確認するテスト群。
"""
import os
from unittest.mock import AsyncMock, MagicMock, patch, call

import discord
import pytest

# テスト対象のモジュールをインポートする前に環境変数を設定
os.environ.setdefault("DISCORD_TOKEN", "dummy_token_for_testing")
os.environ.setdefault("VOICEVOX_URL", "http://127.0.0.1:50021")

from src.bot import VoiceBot, join, leave, play_voice_queue


class TestSetupHookCommandSync:
    """setup_hook のコマンド同期に関するテスト"""

    @pytest.mark.asyncio
    async def test_setup_hook_with_test_guild_clears_global_commands(self):
        """TEST_GUILD が設定されている場合、グローバルコマンドがクリアされてからギルドに同期されること"""
        bot = VoiceBot()

        mock_voicevox = AsyncMock()
        mock_voicevox.initialize = AsyncMock()
        mock_voicevox.is_available = AsyncMock(return_value=True)
        bot.voicevox = mock_voicevox

        test_guild = discord.Object(id=123456789)

        with patch.object(bot.tree, "sync", new_callable=AsyncMock) as mock_sync, \
             patch.object(bot.tree, "copy_global_to", new_callable=MagicMock) as mock_copy, \
             patch.object(bot.tree, "clear_commands", new_callable=MagicMock) as mock_clear, \
             patch("src.bot.TEST_GUILD", test_guild):
            await bot.setup_hook()

        # copy_global_to がテストギルドで呼ばれること
        mock_copy.assert_called_once_with(guild=test_guild)

        # clear_commands が guild=None で呼ばれること（グローバルコマンドをクリア）
        mock_clear.assert_called_once_with(guild=None)

        # sync が合計2回呼ばれること
        assert mock_sync.call_count == 2

        # 1回目の sync が引数なし（グローバルコマンドを空にする）
        assert mock_sync.call_args_list[0] == call()

        # 2回目の sync がギルド指定で呼ばれること
        assert mock_sync.call_args_list[1] == call(guild=test_guild)

        await bot.close()

    @pytest.mark.asyncio
    async def test_setup_hook_with_test_guild_copy_before_clear(self):
        """TEST_GUILD が設定されている場合、copy_global_to が clear_commands より先に呼ばれること"""
        bot = VoiceBot()

        mock_voicevox = AsyncMock()
        mock_voicevox.initialize = AsyncMock()
        mock_voicevox.is_available = AsyncMock(return_value=True)
        bot.voicevox = mock_voicevox

        test_guild = discord.Object(id=123456789)
        call_log: list = []

        def record_copy(*args, **kwargs):
            call_log.append("copy_global_to")

        def record_clear(*args, **kwargs):
            call_log.append("clear_commands")

        async def record_sync(*args, **kwargs):
            call_log.append("sync(guild)" if kwargs.get("guild") else "sync(global)")
            return []

        with patch.object(bot.tree, "sync", side_effect=record_sync), \
             patch.object(bot.tree, "copy_global_to", side_effect=record_copy), \
             patch.object(bot.tree, "clear_commands", side_effect=record_clear), \
             patch("src.bot.TEST_GUILD", test_guild):
            await bot.setup_hook()

        # 呼び出し順序を確認
        assert call_log == [
            "copy_global_to",
            "clear_commands",
            "sync(global)",
            "sync(guild)",
        ]

        await bot.close()

    @pytest.mark.asyncio
    async def test_setup_hook_without_test_guild_syncs_globally(self):
        """TEST_GUILD が設定されていない場合、グローバル同期のみ行われること"""
        bot = VoiceBot()

        mock_voicevox = AsyncMock()
        mock_voicevox.initialize = AsyncMock()
        mock_voicevox.is_available = AsyncMock(return_value=True)
        bot.voicevox = mock_voicevox

        with patch.object(bot.tree, "sync", new_callable=AsyncMock) as mock_sync, \
             patch.object(bot.tree, "copy_global_to", new_callable=MagicMock) as mock_copy, \
             patch.object(bot.tree, "clear_commands", new_callable=MagicMock) as mock_clear, \
             patch("src.bot.TEST_GUILD", None):
            await bot.setup_hook()

        # グローバル同期が1回のみ呼ばれること
        mock_sync.assert_called_once_with()

        # copy_global_to と clear_commands は呼ばれないこと
        mock_copy.assert_not_called()
        mock_clear.assert_not_called()

        await bot.close()


class TestJoinCommandDeferred:
    """/join コマンドのインタラクション defer に関するテスト"""

    def _make_interaction(self, *, has_voice=True, voice_client=None):
        """テスト用の Interaction モックを生成するヘルパー"""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.response = AsyncMock()
        interaction.followup = AsyncMock()

        # ユーザーのボイス状態
        if has_voice:
            mock_channel = MagicMock()
            mock_channel.name = "テストチャンネル"
            mock_channel.connect = AsyncMock()
            interaction.user.voice = MagicMock()
            interaction.user.voice.channel = mock_channel
        else:
            interaction.user.voice = None

        # ギルド
        interaction.guild = MagicMock()
        interaction.guild.id = 111222333
        interaction.guild.voice_client = voice_client
        interaction.channel = MagicMock()
        interaction.channel.id = 999888777

        return interaction

    @pytest.mark.asyncio
    async def test_join_defers_before_connect(self):
        """/join は channel.connect() の前に defer() を呼ぶこと"""
        interaction = self._make_interaction()
        call_log: list = []

        async def record_defer():
            call_log.append("defer")

        async def record_connect():
            call_log.append("connect")

        interaction.response.defer.side_effect = record_defer
        interaction.user.voice.channel.connect.side_effect = record_connect
        interaction.followup.send = AsyncMock()

        await join.callback(interaction)

        assert "defer" in call_log
        assert "connect" in call_log
        assert call_log.index("defer") < call_log.index("connect")

    @pytest.mark.asyncio
    async def test_join_uses_followup_on_success(self):
        """/join 成功時は followup.send() を使うこと（response.send_message ではない）"""
        interaction = self._make_interaction()
        interaction.followup.send = AsyncMock()

        await join.callback(interaction)

        interaction.response.defer.assert_called_once()
        interaction.followup.send.assert_called_once()
        # response.send_message は呼ばれないこと
        interaction.response.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_join_uses_followup_on_error(self):
        """/join でエラーが発生した場合も followup.send() を使うこと"""
        interaction = self._make_interaction()
        interaction.user.voice.channel.connect.side_effect = Exception("接続エラー")
        interaction.followup.send = AsyncMock()

        await join.callback(interaction)

        interaction.response.defer.assert_called_once()
        interaction.followup.send.assert_called_once()
        # エラーメッセージに ephemeral=True が付くこと
        _, kwargs = interaction.followup.send.call_args
        assert kwargs.get("ephemeral") is True

    @pytest.mark.asyncio
    async def test_join_no_voice_returns_immediately(self):
        """/join はユーザーがボイスチャンネル未接続の場合、defer せずにエラーを返すこと"""
        interaction = self._make_interaction(has_voice=False)

        await join.callback(interaction)

        interaction.response.send_message.assert_called_once()
        interaction.response.defer.assert_not_called()

    @pytest.mark.asyncio
    async def test_join_already_connected_returns_immediately(self):
        """/join はすでにボイスチャンネルに接続済みの場合、defer せずにエラーを返すこと"""
        interaction = self._make_interaction(voice_client=MagicMock())

        await join.callback(interaction)

        interaction.response.send_message.assert_called_once()
        interaction.response.defer.assert_not_called()


class TestLeaveCommandDeferred:
    """/leave コマンドのインタラクション defer に関するテスト"""

    def _make_interaction(self, *, has_voice_client=True):
        """テスト用の Interaction モックを生成するヘルパー"""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.response = AsyncMock()
        interaction.followup = AsyncMock()

        interaction.guild = MagicMock()
        interaction.guild.id = 111222333

        if has_voice_client:
            mock_vc = AsyncMock()
            mock_vc.disconnect = AsyncMock()
            interaction.guild.voice_client = mock_vc
        else:
            interaction.guild.voice_client = None

        return interaction

    @pytest.mark.asyncio
    async def test_leave_defers_before_disconnect(self):
        """/leave は voice_client.disconnect() の前に defer() を呼ぶこと"""
        interaction = self._make_interaction()
        call_log: list = []

        async def record_defer():
            call_log.append("defer")

        async def record_disconnect():
            call_log.append("disconnect")

        interaction.response.defer.side_effect = record_defer
        interaction.guild.voice_client.disconnect.side_effect = record_disconnect
        interaction.followup.send = AsyncMock()

        await leave.callback(interaction)

        assert "defer" in call_log
        assert "disconnect" in call_log
        assert call_log.index("defer") < call_log.index("disconnect")

    @pytest.mark.asyncio
    async def test_leave_uses_followup_on_success(self):
        """/leave 成功時は followup.send() を使うこと（response.send_message ではない）"""
        interaction = self._make_interaction()
        interaction.followup.send = AsyncMock()

        await leave.callback(interaction)

        interaction.response.defer.assert_called_once()
        interaction.followup.send.assert_called_once()
        interaction.response.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_leave_uses_followup_on_error(self):
        """/leave でエラーが発生した場合も followup.send() を使うこと"""
        interaction = self._make_interaction()
        interaction.guild.voice_client.disconnect.side_effect = Exception("切断エラー")
        interaction.followup.send = AsyncMock()

        await leave.callback(interaction)

        interaction.response.defer.assert_called_once()
        interaction.followup.send.assert_called_once()
        _, kwargs = interaction.followup.send.call_args
        assert kwargs.get("ephemeral") is True

    @pytest.mark.asyncio
    async def test_leave_not_connected_returns_immediately(self):
        """/leave はボイスチャンネルに接続していない場合、defer せずにエラーを返すこと"""
        interaction = self._make_interaction(has_voice_client=False)

        await leave.callback(interaction)

        interaction.response.send_message.assert_called_once()
        interaction.response.defer.assert_not_called()


class TestMultiGuildIsolation:
    """複数ギルドの同時接続における分離・競合状態のテスト"""

    def _setup_bot_state(self, mock_bot, guild_id: int):
        """指定ギルドの初期状態をモック bot に設定するヘルパー"""
        import asyncio
        mock_bot.voice_queues[guild_id] = asyncio.Queue()
        mock_bot.is_playing[guild_id] = False
        mock_bot.guild_configs[guild_id] = {"read_channel": 999}

    # ------------------------------------------------------------------
    # Fix 1: on_message が create_task の前に is_playing を True にすること
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_on_message_sets_is_playing_before_create_task(self):
        """on_message は create_task() より前に is_playing を True にセットすること。
        これにより、同一ギルドへの連続メッセージで重複タスクが生成されるのを防ぐ。"""
        import asyncio
        import src.bot as bot_module

        guild_id = 111222333

        # bot のキュー・フラグを初期化
        bot_module.bot.voice_queues[guild_id] = asyncio.Queue()
        bot_module.bot.is_playing[guild_id] = False
        bot_module.bot.guild_configs[guild_id] = {"read_channel": 777}
        bot_module.bot.user_speakers = {}
        bot_module.bot.user_speeds = {}
        bot_module.bot.dictionary = {}

        mock_guild = MagicMock()
        mock_guild.id = guild_id
        mock_guild.voice_client = MagicMock()

        mock_message = MagicMock(spec=discord.Message)
        mock_message.author.bot = False
        mock_message.guild = mock_guild
        mock_message.channel.id = 777
        mock_message.clean_content = "テスト"
        mock_message.author.id = 42

        captured_is_playing: list = []

        def fake_create_task(coro):
            # create_task が呼ばれた瞬間の is_playing の値を記録
            captured_is_playing.append(bot_module.bot.is_playing.get(guild_id))
            # コルーチンをキャンセルしてリソースリーク防止
            coro.close()
            return MagicMock()

        with patch.object(bot_module.bot, 'process_commands', new_callable=AsyncMock), \
             patch.object(bot_module.bot, 'loop') as mock_loop:
            mock_loop.create_task.side_effect = fake_create_task
            await bot_module.on_message(mock_message)

        # create_task が呼ばれていること
        assert mock_loop.create_task.call_count == 1

        # create_task が呼ばれた時点で is_playing が True になっていること
        assert captured_is_playing == [True], (
            "create_task() 呼び出し前に is_playing が True にセットされていない。"
            "複数メッセージが届いた場合に重複タスクが生成される可能性がある。"
        )

        # テスト後のクリーンアップ
        bot_module.bot.voice_queues.pop(guild_id, None)
        bot_module.bot.is_playing.pop(guild_id, None)
        bot_module.bot.guild_configs.pop(guild_id, None)

    @pytest.mark.asyncio
    async def test_on_message_does_not_create_duplicate_task_when_already_playing(self):
        """is_playing が True の場合、create_task() は呼ばれないこと"""
        import asyncio
        import src.bot as bot_module

        guild_id = 222333444

        bot_module.bot.voice_queues[guild_id] = asyncio.Queue()
        bot_module.bot.is_playing[guild_id] = True  # 既に再生中
        bot_module.bot.guild_configs[guild_id] = {"read_channel": 888}
        bot_module.bot.user_speakers = {}
        bot_module.bot.user_speeds = {}
        bot_module.bot.dictionary = {}

        mock_guild = MagicMock()
        mock_guild.id = guild_id
        mock_guild.voice_client = MagicMock()

        mock_message = MagicMock(spec=discord.Message)
        mock_message.author.bot = False
        mock_message.guild = mock_guild
        mock_message.channel.id = 888
        mock_message.clean_content = "テスト2"
        mock_message.author.id = 43

        with patch.object(bot_module.bot, 'process_commands', new_callable=AsyncMock), \
             patch.object(bot_module.bot, 'loop') as mock_loop:
            await bot_module.on_message(mock_message)

        # 既に再生中なので create_task は呼ばれないこと
        mock_loop.create_task.assert_not_called()

        # テスト後のクリーンアップ
        bot_module.bot.voice_queues.pop(guild_id, None)
        bot_module.bot.is_playing.pop(guild_id, None)
        bot_module.bot.guild_configs.pop(guild_id, None)

    # ------------------------------------------------------------------
    # Fix 2: play_voice_queue がギルド切断後にクラッシュしないこと
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_play_voice_queue_exits_gracefully_when_queue_deleted(self):
        """play_voice_queue は実行中にギルドが切断されキューが削除されても
        KeyError を起こさず正常終了すること"""
        import asyncio
        import src.bot as bot_module

        guild_id = 333444555

        # キューにアイテムを1つ入れておく
        bot_module.bot.voice_queues[guild_id] = asyncio.Queue()
        await bot_module.bot.voice_queues[guild_id].put({
            "text": "テスト",
            "speaker_id": 1,
            "speed": 1.0,
        })
        bot_module.bot.is_playing[guild_id] = False

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.voice_client = None  # 切断済み

        # create_audio が呼ばれたタイミングでキューを削除（ギルド切断をシミュレート）
        async def simulate_disconnect(text, speaker_id, speed):
            bot_module.bot.voice_queues.pop(guild_id, None)
            return None  # 切断後は音声データなし

        bot_module.bot.voicevox.create_audio = simulate_disconnect

        # KeyError が発生しないことを確認
        await play_voice_queue(mock_guild)

        # タスク終了後に is_playing が False になっていること
        assert bot_module.bot.is_playing.get(guild_id) is False

        # クリーンアップ
        bot_module.bot.is_playing.pop(guild_id, None)

    @pytest.mark.asyncio
    async def test_play_voice_queue_exits_immediately_when_queue_missing_at_start(self):
        """play_voice_queue 開始時にキューが存在しない場合、即座に終了すること"""
        import src.bot as bot_module

        guild_id = 444555666

        # voice_queues にエントリを作らない（切断済み状態）
        bot_module.bot.voice_queues.pop(guild_id, None)
        bot_module.bot.is_playing[guild_id] = False

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.voice_client = None

        # KeyError が発生せず正常終了すること
        await play_voice_queue(mock_guild)

        assert bot_module.bot.is_playing.get(guild_id) is False

        # クリーンアップ
        bot_module.bot.is_playing.pop(guild_id, None)

    @pytest.mark.asyncio
    async def test_two_guilds_have_independent_queues(self):
        """2つのギルドのキューが独立していること（一方への操作が他方に影響しない）"""
        import asyncio
        import src.bot as bot_module

        guild_a = 555666777
        guild_b = 888999000

        bot_module.bot.voice_queues[guild_a] = asyncio.Queue()
        bot_module.bot.voice_queues[guild_b] = asyncio.Queue()
        bot_module.bot.is_playing[guild_a] = False
        bot_module.bot.is_playing[guild_b] = False

        await bot_module.bot.voice_queues[guild_a].put({"text": "A", "speaker_id": 1, "speed": 1.0})
        await bot_module.bot.voice_queues[guild_b].put({"text": "B", "speaker_id": 2, "speed": 1.5})

        # Guild A のキューを消去（/leave をシミュレート）
        del bot_module.bot.voice_queues[guild_a]

        # Guild B のキューは影響を受けないこと
        assert guild_b in bot_module.bot.voice_queues
        assert not bot_module.bot.voice_queues[guild_b].empty()
        item = await bot_module.bot.voice_queues[guild_b].get()
        assert item["text"] == "B"

        # クリーンアップ
        bot_module.bot.voice_queues.pop(guild_a, None)
        bot_module.bot.voice_queues.pop(guild_b, None)
        bot_module.bot.is_playing.pop(guild_a, None)
        bot_module.bot.is_playing.pop(guild_b, None)

    @pytest.mark.asyncio
    async def test_play_voice_queue_resets_is_playing_after_normal_completion(self):
        """play_voice_queue は通常完了後（キュー空）に is_playing を False にリセットすること"""
        import asyncio
        import src.bot as bot_module

        guild_id = 777888999

        # キューを空で用意（アイテムなし）
        bot_module.bot.voice_queues[guild_id] = asyncio.Queue()
        bot_module.bot.is_playing[guild_id] = True  # タスク開始前の状態

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.voice_client = None

        await play_voice_queue(mock_guild)

        # 正常終了後に is_playing が False にリセットされていること
        assert bot_module.bot.is_playing.get(guild_id) is False

        # クリーンアップ
        bot_module.bot.voice_queues.pop(guild_id, None)
        bot_module.bot.is_playing.pop(guild_id, None)



