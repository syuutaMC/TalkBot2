"""
VoicevoxClient のテスト
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.voicevox_client import VoicevoxClient


SAMPLE_SPEAKERS = [
    {
        "name": "ずんだもん",
        "styles": [
            {"id": 3, "name": "ノーマル"},
            {"id": 1, "name": "あまあま"},
        ],
    },
    {
        "name": "四国めたん",
        "styles": [
            {"id": 2, "name": "ノーマル"},
        ],
    },
]


class TestGetValidSpeakerIds:
    """get_valid_speaker_ids のテスト"""

    @pytest.mark.asyncio
    async def test_returns_all_style_ids_from_speakers(self):
        """speakers リストから全スタイル ID の集合を返すこと"""
        client = VoicevoxClient()
        client.get_speakers = AsyncMock(return_value=SAMPLE_SPEAKERS)

        result = await client.get_valid_speaker_ids()

        assert result == {1, 2, 3}

    @pytest.mark.asyncio
    async def test_returns_empty_set_when_speakers_unavailable(self):
        """VOICEVOX が応答しない場合は空集合を返すこと"""
        client = VoicevoxClient()
        client.get_speakers = AsyncMock(return_value=[])

        result = await client.get_valid_speaker_ids()

        assert result == set()

    @pytest.mark.asyncio
    async def test_ignores_styles_without_id(self):
        """'id' キーを持たないスタイルは無視すること"""
        speakers = [
            {
                "name": "テスト話者",
                "styles": [
                    {"id": 5, "name": "ノーマル"},
                    {"name": "壊れたスタイル"},  # id なし
                ],
            }
        ]
        client = VoicevoxClient()
        client.get_speakers = AsyncMock(return_value=speakers)

        result = await client.get_valid_speaker_ids()

        assert result == {5}

    @pytest.mark.asyncio
    async def test_returns_empty_set_for_speaker_with_no_styles(self):
        """styles が空の話者しかいない場合は空集合を返すこと"""
        speakers = [{"name": "空の話者", "styles": []}]
        client = VoicevoxClient()
        client.get_speakers = AsyncMock(return_value=speakers)

        result = await client.get_valid_speaker_ids()

        assert result == set()
