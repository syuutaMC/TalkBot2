"""
VoiceBot の setup_hook におけるスラッシュコマンド同期のテスト

更新時に古いコマンドが残らないことを確認するテスト群。
"""
import os
import json
from unittest.mock import AsyncMock, MagicMock, patch, call

import discord
import pytest

# テスト対象のモジュールをインポートする前に環境変数を設定
os.environ.setdefault("DISCORD_TOKEN", "dummy_token_for_testing")
os.environ.setdefault("VOICEVOX_URL", "http://127.0.0.1:50021")

from src.bot import VoiceBot, join, leave, play_voice_queue, on_guild_join, on_guild_remove, on_ready, on_voice_state_update


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
    async def test_play_voice_queue_records_tts_request_on_success(self):
        """play_voice_queue は音声生成成功時に voice_play_total をインクリメントすること"""
        import asyncio
        import src.bot as bot_module

        guild_id = 101010101

        bot_module.bot.voice_queues[guild_id] = asyncio.Queue()
        await bot_module.bot.voice_queues[guild_id].put({
            "text": "テスト",
            "speaker_id": 1,
            "speed": 1.0,
        })
        bot_module.bot.is_playing[guild_id] = False

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.voice_client = None  # 接続なし（再生はスキップされる）

        async def fake_create_audio(text, speaker_id, speed):
            return b"fake_audio_data"

        with patch("src.bot.prom.voice_play_total") as mock_voice_play, \
             patch("src.bot.tempfile.NamedTemporaryFile"), \
             patch("src.bot.os.unlink"):
            bot_module.bot.voicevox.create_audio = fake_create_audio
            await play_voice_queue(mock_guild)

        mock_voice_play.inc.assert_called_once()

        # クリーンアップ
        bot_module.bot.voice_queues.pop(guild_id, None)
        bot_module.bot.is_playing.pop(guild_id, None)

    @pytest.mark.asyncio
    async def test_play_voice_queue_does_not_record_tts_request_on_failure(self):
        """play_voice_queue は音声生成失敗（None 返却）時に voice_play_total をインクリメントしないこと"""
        import asyncio
        import src.bot as bot_module

        guild_id = 202020202

        bot_module.bot.voice_queues[guild_id] = asyncio.Queue()
        await bot_module.bot.voice_queues[guild_id].put({
            "text": "テスト",
            "speaker_id": 1,
            "speed": 1.0,
        })
        bot_module.bot.is_playing[guild_id] = False

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.voice_client = None

        async def fake_create_audio_fail(text, speaker_id, speed):
            return None  # 失敗をシミュレート

        with patch("src.bot.prom.voice_play_total") as mock_voice_play:
            bot_module.bot.voicevox.create_audio = fake_create_audio_fail
            await play_voice_queue(mock_guild)

        mock_voice_play.inc.assert_not_called()

        # クリーンアップ
        bot_module.bot.voice_queues.pop(guild_id, None)
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


class TestGuildTracking:
    """サーバー参加数追跡のテスト"""

    @pytest.mark.asyncio
    async def test_on_guild_join_adds_guild_and_saves(self):
        """on_guild_join が joined_guilds にギルドを追加して設定を保存すること"""
        import src.bot as bot_module

        bot_module.bot.joined_guilds = set()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123456789

        with patch.object(bot_module.bot, "_save_config") as mock_save:
            await bot_module.on_guild_join(mock_guild)

        assert 123456789 in bot_module.bot.joined_guilds
        mock_save.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_guild_remove_removes_guild_and_saves(self):
        """on_guild_remove が joined_guilds からギルドを削除して設定を保存すること"""
        import src.bot as bot_module

        bot_module.bot.joined_guilds = {111, 222, 333}

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 222

        with patch.object(bot_module.bot, "_save_config") as mock_save:
            await bot_module.on_guild_remove(mock_guild)

        assert 222 not in bot_module.bot.joined_guilds
        assert 111 in bot_module.bot.joined_guilds
        assert 333 in bot_module.bot.joined_guilds
        mock_save.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_guild_remove_nonexistent_guild_does_not_raise(self):
        """存在しないギルドを on_guild_remove しても例外が発生しないこと"""
        import src.bot as bot_module

        bot_module.bot.joined_guilds = {111}

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 999

        with patch.object(bot_module.bot, "_save_config"):
            await bot_module.on_guild_remove(mock_guild)

        assert 111 in bot_module.bot.joined_guilds

    @pytest.mark.asyncio
    async def test_on_guild_remove_clears_guild_configs(self):
        """on_guild_remove が guild_configs からギルドの設定を削除すること"""
        import asyncio
        import src.bot as bot_module

        guild_id = 222
        bot_module.bot.joined_guilds = {111, guild_id, 333}
        bot_module.bot.guild_configs = {
            111: {"read_channel": 1, "dictionary": {}},
            guild_id: {"read_channel": 2, "dictionary": {"テスト": "test"}},
            333: {"read_channel": 3, "dictionary": {}},
        }
        bot_module.bot.voice_queues = {guild_id: asyncio.Queue()}
        bot_module.bot.is_playing = {guild_id: False}

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id

        with patch.object(bot_module.bot, "_save_config"):
            await bot_module.on_guild_remove(mock_guild)

        assert guild_id not in bot_module.bot.guild_configs
        assert 111 in bot_module.bot.guild_configs
        assert 333 in bot_module.bot.guild_configs

    @pytest.mark.asyncio
    async def test_on_guild_remove_clears_voice_queues_and_is_playing(self):
        """on_guild_remove が voice_queues と is_playing からギルドのデータを削除すること"""
        import asyncio
        import src.bot as bot_module

        guild_id = 444
        bot_module.bot.joined_guilds = {guild_id}
        bot_module.bot.guild_configs = {guild_id: {"read_channel": 1, "dictionary": {}}}
        bot_module.bot.voice_queues = {guild_id: asyncio.Queue(), 555: asyncio.Queue()}
        bot_module.bot.is_playing = {guild_id: True, 555: False}

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id

        with patch.object(bot_module.bot, "_save_config"):
            await bot_module.on_guild_remove(mock_guild)

        assert guild_id not in bot_module.bot.voice_queues
        assert guild_id not in bot_module.bot.is_playing
        assert 555 in bot_module.bot.voice_queues
        assert 555 in bot_module.bot.is_playing

    @pytest.mark.asyncio
    async def test_on_guild_remove_missing_data_does_not_raise(self):
        """voice_queues や guild_configs にデータがない場合でも on_guild_remove が例外を発生させないこと"""
        import src.bot as bot_module

        guild_id = 777
        bot_module.bot.joined_guilds = {guild_id}
        bot_module.bot.guild_configs = {}
        bot_module.bot.voice_queues = {}
        bot_module.bot.is_playing = {}

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id

        with patch.object(bot_module.bot, "_save_config"):
            await bot_module.on_guild_remove(mock_guild)

        assert guild_id not in bot_module.bot.joined_guilds

    @pytest.mark.asyncio
    async def test_on_ready_syncs_joined_guilds_from_actual_guilds(self):
        """on_ready が bot.guilds の内容で joined_guilds を同期して保存すること"""
        from unittest.mock import PropertyMock
        import src.bot as bot_module

        bot_module.bot.joined_guilds = {999}  # 古い状態

        mock_guild_a = MagicMock(spec=discord.Guild)
        mock_guild_a.id = 111

        mock_guild_b = MagicMock(spec=discord.Guild)
        mock_guild_b.id = 222

        mock_user = MagicMock()
        mock_user.name = "TestBot"
        mock_user.id = 1

        with (
            patch.object(type(bot_module.bot), "guilds", new_callable=PropertyMock, return_value=[mock_guild_a, mock_guild_b]),
            patch.object(type(bot_module.bot), "user", new_callable=PropertyMock, return_value=mock_user),
            patch.object(bot_module.bot, "_save_config") as mock_save,
        ):
            await bot_module.on_ready()

        assert bot_module.bot.joined_guilds == {111, 222}
        mock_save.assert_called_once()

    def test_load_config_initializes_joined_guilds(self, tmp_path):
        """設定ファイルに joined_guilds がある場合は正しく読み込まれること"""
        config_data = {
            "user_speakers": {},
            "user_speeds": {},
            "guild_configs": {},
            "joined_guilds": [100, 200, 300],
        }
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config_data), encoding="utf-8")

        with patch("src.bot.CONFIG_FILE", config_file):
            bot = VoiceBot()

        assert bot.joined_guilds == {100, 200, 300}

    def test_save_config_persists_joined_guilds(self, tmp_path):
        """_save_config が joined_guilds を設定ファイルに保存すること"""
        config_file = tmp_path / "config.json"

        with patch("src.bot.CONFIG_FILE", config_file):
            bot = VoiceBot()
            bot.joined_guilds = {111, 222, 333}
            bot._save_config()

        saved = json.loads(config_file.read_text(encoding="utf-8"))
        assert set(saved["joined_guilds"]) == {111, 222, 333}


class TestGuildConfigPersistence:
    """guild_configs が /join・/leave・自動退出で正しく保存されることのテスト"""

    def _make_join_interaction(self, guild_id: int, read_channel_id: int):
        """テスト用の /join インタラクションモックを生成するヘルパー"""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.response = AsyncMock()
        interaction.followup = AsyncMock()

        mock_channel = MagicMock()
        mock_channel.name = "テストチャンネル"
        mock_channel.connect = AsyncMock()
        interaction.user.voice = MagicMock()
        interaction.user.voice.channel = mock_channel

        interaction.guild = MagicMock()
        interaction.guild.id = guild_id
        interaction.guild.voice_client = None
        interaction.channel = MagicMock()
        interaction.channel.id = read_channel_id

        return interaction

    def _cleanup(self, *guild_ids):
        """指定したギルドIDのbot状態をクリーンアップするヘルパー"""
        import src.bot as bot_module
        for gid in guild_ids:
            bot_module.bot.guild_configs.pop(gid, None)
            bot_module.bot.voice_queues.pop(gid, None)
            bot_module.bot.is_playing.pop(gid, None)

    def _make_leave_interaction(self, guild_id: int):
        """テスト用の /leave インタラクションモックを生成するヘルパー"""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.response = AsyncMock()
        interaction.followup = AsyncMock()

        interaction.guild = MagicMock()
        interaction.guild.id = guild_id

        mock_vc = AsyncMock()
        mock_vc.disconnect = AsyncMock()
        interaction.guild.voice_client = mock_vc

        return interaction

    @pytest.mark.asyncio
    async def test_join_saves_guild_config(self):
        """/join はギルド設定を guild_configs に追加して設定を保存すること"""
        import src.bot as bot_module

        guild_id = 100200300
        bot_module.bot.guild_configs.pop(guild_id, None)

        interaction = self._make_join_interaction(guild_id, 2)

        with patch.object(bot_module.bot, "_save_config") as mock_save:
            await join.callback(interaction)

        assert guild_id in bot_module.bot.guild_configs
        mock_save.assert_called_once()

        # クリーンアップ
        self._cleanup(guild_id)

    @pytest.mark.asyncio
    async def test_join_multiple_guilds_saves_all_configs(self):
        """複数のギルドで /join したとき、それぞれ guild_configs が保存されること"""
        import src.bot as bot_module

        guild_a = 111000111
        guild_b = 222000222
        bot_module.bot.guild_configs.pop(guild_a, None)
        bot_module.bot.guild_configs.pop(guild_b, None)

        interaction_a = self._make_join_interaction(guild_a, 10)
        interaction_b = self._make_join_interaction(guild_b, 20)

        save_calls = []

        def record_save():
            # 保存時点の guild_configs のキーを記録
            save_calls.append(set(bot_module.bot.guild_configs.keys()))

        with patch.object(bot_module.bot, "_save_config", side_effect=record_save):
            await join.callback(interaction_a)
            await join.callback(interaction_b)

        # それぞれの /join で _save_config が呼ばれること
        assert len(save_calls) == 2
        # 2 回目の保存時点では両ギルドが guild_configs にいること
        assert guild_a in save_calls[1]
        assert guild_b in save_calls[1]

        # クリーンアップ
        self._cleanup(guild_a, guild_b)

    @pytest.mark.asyncio
    async def test_leave_saves_config_and_preserves_guild_config(self):
        """/leave は音声状態をクリアしつつギルド設定（辞書など）を保持して保存すること"""
        import asyncio
        import src.bot as bot_module

        guild_id = 300400500
        bot_module.bot.guild_configs[guild_id] = {"read_channel": 999, "dictionary": {"hello": "こんにちは"}}
        bot_module.bot.voice_queues[guild_id] = asyncio.Queue()
        bot_module.bot.is_playing[guild_id] = False

        interaction = self._make_leave_interaction(guild_id)

        with patch.object(bot_module.bot, "_save_config") as mock_save:
            await leave.callback(interaction)

        # guild_configs は保持されること（辞書を保存するため）
        assert guild_id in bot_module.bot.guild_configs
        assert bot_module.bot.guild_configs[guild_id]["dictionary"] == {"hello": "こんにちは"}
        # 音声状態はクリアされること
        assert guild_id not in bot_module.bot.voice_queues
        assert guild_id not in bot_module.bot.is_playing
        mock_save.assert_called_once()

        # クリーンアップ
        self._cleanup(guild_id)

    @pytest.mark.asyncio
    async def test_auto_leave_saves_config_and_preserves_guild_config(self):
        """全員退出による自動退出時も guild_configs（辞書など）を保持して保存されること"""
        import asyncio
        import src.bot as bot_module

        guild_id = 500600700

        bot_module.bot.guild_configs[guild_id] = {"read_channel": 888, "dictionary": {"bye": "さようなら"}}
        bot_module.bot.voice_queues[guild_id] = asyncio.Queue()
        bot_module.bot.is_playing[guild_id] = False

        mock_bot_member = MagicMock(spec=discord.Member)
        mock_bot_member.bot = True

        mock_channel = MagicMock()
        mock_channel.members = [mock_bot_member]  # ボットのみ残っている

        mock_vc = AsyncMock()
        mock_vc.channel = mock_channel
        mock_vc.disconnect = AsyncMock()

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = guild_id
        mock_guild.voice_client = mock_vc

        member = MagicMock(spec=discord.Member)
        member.guild = mock_guild
        member.bot = False

        before = MagicMock(spec=discord.VoiceState)
        before.channel = mock_channel
        after = MagicMock(spec=discord.VoiceState)
        after.channel = None

        with patch.object(bot_module.bot, "_save_config") as mock_save:
            await on_voice_state_update(member, before, after)

        # guild_configs は保持されること（辞書を保存するため）
        assert guild_id in bot_module.bot.guild_configs
        assert bot_module.bot.guild_configs[guild_id]["dictionary"] == {"bye": "さようなら"}
        # 音声状態はクリアされること
        assert guild_id not in bot_module.bot.voice_queues
        assert guild_id not in bot_module.bot.is_playing
        mock_save.assert_called_once()

        # クリーンアップ
        self._cleanup(guild_id)

    @pytest.mark.asyncio
    async def test_join_updates_read_channel_when_guild_config_exists(self):
        """/join は既存のギルド設定があっても read_channel を更新すること"""
        import asyncio
        import src.bot as bot_module

        guild_id = 700800900
        # 既存の設定（辞書あり）
        bot_module.bot.guild_configs[guild_id] = {
            "read_channel": 111,
            "dictionary": {"hello": "こんにちは"},
        }

        interaction = self._make_join_interaction(guild_id, 999)

        with patch.object(bot_module.bot, "_save_config"):
            await join.callback(interaction)

        # read_channel が新しいチャンネルに更新されること
        assert bot_module.bot.guild_configs[guild_id]["read_channel"] == 999
        # 辞書は保持されること
        assert bot_module.bot.guild_configs[guild_id]["dictionary"] == {"hello": "こんにちは"}

        # クリーンアップ
        self._cleanup(guild_id)


class TestPerGuildDictionary:
    """辞書がサーバーごとに分離されることのテスト"""

    def _make_interaction(self, guild_id: int):
        """テスト用の Interaction モックを生成するヘルパー"""
        interaction = MagicMock(spec=discord.Interaction)
        interaction.response = AsyncMock()
        interaction.guild = MagicMock(spec=discord.Guild)
        interaction.guild.id = guild_id
        return interaction

    def _cleanup(self, *guild_ids):
        """指定したギルドIDのbot状態をクリーンアップするヘルパー"""
        import src.bot as bot_module
        for gid in guild_ids:
            bot_module.bot.guild_configs.pop(gid, None)

    @pytest.mark.asyncio
    async def test_dictionary_add_stores_entry_in_guild_config(self):
        """dictionary add はギルド設定内の辞書にエントリを追加すること"""
        import src.bot as bot_module

        guild_id = 10001
        bot_module.bot.guild_configs.pop(guild_id, None)

        interaction = self._make_interaction(guild_id)

        with patch.object(bot_module.bot, "_save_config"):
            await bot_module.dictionary_add.callback(interaction, "テスト", "テスト読み")

        assert guild_id in bot_module.bot.guild_configs
        assert bot_module.bot.guild_configs[guild_id]["dictionary"]["テスト"] == "テスト読み"

        self._cleanup(guild_id)

    @pytest.mark.asyncio
    async def test_dictionary_add_is_isolated_per_guild(self):
        """dictionary add は別のギルドの辞書に影響を与えないこと"""
        import src.bot as bot_module

        guild_a = 20001
        guild_b = 20002
        bot_module.bot.guild_configs.pop(guild_a, None)
        bot_module.bot.guild_configs.pop(guild_b, None)

        interaction_a = self._make_interaction(guild_a)
        interaction_b = self._make_interaction(guild_b)

        with patch.object(bot_module.bot, "_save_config"):
            await bot_module.dictionary_add.callback(interaction_a, "AI", "エーアイ")
            await bot_module.dictionary_add.callback(interaction_b, "AI", "藍")

        assert bot_module.bot.guild_configs[guild_a]["dictionary"]["AI"] == "エーアイ"
        assert bot_module.bot.guild_configs[guild_b]["dictionary"]["AI"] == "藍"

        self._cleanup(guild_a, guild_b)

    @pytest.mark.asyncio
    async def test_dictionary_remove_only_affects_own_guild(self):
        """dictionary remove は自ギルドの辞書のみ削除すること"""
        import src.bot as bot_module

        guild_a = 30001
        guild_b = 30002
        bot_module.bot.guild_configs[guild_a] = {"dictionary": {"word": "読みA"}}
        bot_module.bot.guild_configs[guild_b] = {"dictionary": {"word": "読みB"}}

        interaction_a = self._make_interaction(guild_a)

        with patch.object(bot_module.bot, "_save_config"):
            await bot_module.dictionary_remove.callback(interaction_a, "word")

        assert "word" not in bot_module.bot.guild_configs[guild_a].get("dictionary", {})
        assert bot_module.bot.guild_configs[guild_b]["dictionary"]["word"] == "読みB"

        self._cleanup(guild_a, guild_b)

    @pytest.mark.asyncio
    async def test_dictionary_list_shows_only_own_guild_entries(self):
        """dictionary list は自ギルドの辞書のみ表示すること"""
        import src.bot as bot_module

        guild_a = 40001
        guild_b = 40002
        bot_module.bot.guild_configs[guild_a] = {"dictionary": {"サーバーA専用": "A"}}
        bot_module.bot.guild_configs[guild_b] = {"dictionary": {"サーバーB専用": "B"}}

        interaction_a = self._make_interaction(guild_a)
        interaction_a.response.send_message = AsyncMock()

        await bot_module.dictionary_list.callback(interaction_a)

        interaction_a.response.send_message.assert_called_once()
        _, kwargs = interaction_a.response.send_message.call_args
        embed = kwargs.get("embed")
        assert embed is not None
        assert "サーバーA専用" in embed.description
        assert "サーバーB専用" not in embed.description

        self._cleanup(guild_a, guild_b)

    @pytest.mark.asyncio
    async def test_dictionary_add_no_guild_returns_error(self):
        """辞書コマンドはDMなどギルド外では使用できないこと"""
        import src.bot as bot_module

        interaction = MagicMock(spec=discord.Interaction)
        interaction.response = AsyncMock()
        interaction.guild = None

        await bot_module.dictionary_add.callback(interaction, "test", "テスト")

        interaction.response.send_message.assert_called_once()
        _, kwargs = interaction.response.send_message.call_args
        assert kwargs.get("ephemeral") is True

    @pytest.mark.asyncio
    async def test_on_message_uses_per_guild_dictionary(self):
        """on_message はサーバー固有の辞書を使って変換すること"""
        import asyncio
        import src.bot as bot_module

        guild_id = 50001
        bot_module.bot.voice_queues[guild_id] = asyncio.Queue()
        bot_module.bot.is_playing[guild_id] = False
        bot_module.bot.guild_configs[guild_id] = {
            "read_channel": 777,
            "dictionary": {"テスト": "てすと"},
        }
        bot_module.bot.user_speakers = {}
        bot_module.bot.user_speeds = {}

        mock_guild = MagicMock()
        mock_guild.id = guild_id
        mock_guild.voice_client = MagicMock()

        mock_message = MagicMock(spec=discord.Message)
        mock_message.author.bot = False
        mock_message.guild = mock_guild
        mock_message.channel.id = 777
        mock_message.clean_content = "テスト"
        mock_message.author.id = 42

        with patch.object(bot_module.bot, "process_commands", new_callable=AsyncMock), \
             patch.object(bot_module.bot, "loop") as mock_loop:
            def cancel_coro(coro):
                coro.close()
                return MagicMock()
            mock_loop.create_task.side_effect = cancel_coro
            await bot_module.on_message(mock_message)

        queued = await bot_module.bot.voice_queues[guild_id].get()
        assert queued["text"] == "てすと"

        # クリーンアップ
        bot_module.bot.voice_queues.pop(guild_id, None)
        bot_module.bot.is_playing.pop(guild_id, None)
        bot_module.bot.guild_configs.pop(guild_id, None)

    def test_save_and_load_config_persists_per_guild_dictionary(self, tmp_path):
        """_save_config と _load_config で辞書がギルドごとに保存・復元されること"""
        config_file = tmp_path / "config.json"

        with patch("src.bot.CONFIG_FILE", config_file):
            bot = VoiceBot()
            bot.guild_configs = {
                111: {"read_channel": 1, "dictionary": {"hello": "こんにちは"}},
                222: {"read_channel": 2, "dictionary": {"bye": "さようなら"}},
            }
            bot._save_config()

        with patch("src.bot.CONFIG_FILE", config_file):
            bot2 = VoiceBot()

        assert bot2.guild_configs[111]["dictionary"] == {"hello": "こんにちは"}
        assert bot2.guild_configs[222]["dictionary"] == {"bye": "さようなら"}
