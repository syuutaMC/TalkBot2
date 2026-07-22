import pytest
from unittest.mock import MagicMock

from src.voicevox_client import VoicevoxClient


class _Response:
    def __init__(self, status, payload=None, body=b"wav"):
        self.status = status
        self.payload = payload
        self.body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def json(self):
        return self.payload

    async def read(self):
        return self.body


@pytest.mark.asyncio
async def test_create_audio_applies_volume_and_intonation_to_synthesis_json():
    session = MagicMock()
    session.post.side_effect = [
        _Response(200, {"speedScale": 1.0, "volumeScale": 1.0, "intonationScale": 1.0}),
        _Response(200, body=b"audio"),
    ]
    client = VoicevoxClient("http://engine")
    client.session = session

    assert await client.create_audio("hello", 3, 1.25, 0.7, 1.4) == b"audio"
    synthesis = session.post.call_args_list[1]
    assert synthesis.kwargs["json"]["speedScale"] == 1.25
    assert synthesis.kwargs["json"]["volumeScale"] == 0.7
    assert synthesis.kwargs["json"]["intonationScale"] == 1.4
