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

from src.bot import VoiceBot, join, leave


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

