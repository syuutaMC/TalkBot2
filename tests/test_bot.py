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

from src.bot import VoiceBot


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
