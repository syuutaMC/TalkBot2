"""
tests/test_dashboard.py

ダッシュボード (src/dashboard.py) のユニットテスト
"""
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

# src パスを追加
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.dashboard import (
    _fetch_voicevox,
    create_app,
    handle_api_metrics,
    handle_api_status,
    handle_api_voicevox_speakers,
    handle_api_voicevox_status,
    handle_index,
    read_config,
)


# ---------------------------------------------------------------------------
# read_config のテスト
# ---------------------------------------------------------------------------

class TestReadConfig:
    """read_config 関数のテスト"""

    @pytest.mark.asyncio
    async def test_read_config_returns_default_when_file_missing(self, tmp_path):
        """設定ファイルが存在しない場合はデフォルト値を返すこと"""
        missing_path = tmp_path / "missing.json"
        with patch("src.dashboard.CONFIG_PATH", missing_path):
            config = await read_config()

        assert config == {
            "user_speakers": {},
            "user_speeds": {},
            "guild_configs": {},
            "joined_guilds": [],
        }

    @pytest.mark.asyncio
    async def test_read_config_loads_existing_file(self, tmp_path):
        """設定ファイルが存在する場合はその内容を返すこと"""
        config_data = {
            "user_speakers": {"123": 2},
            "user_speeds": {"123": 1.5},
            "guild_configs": {"456": {"read_channel": 789}},
            "dictionary": {"おはよう": "おはようございます"},
        }
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config_data), encoding="utf-8")

        with patch("src.dashboard.CONFIG_PATH", config_file):
            result = await read_config()

        assert result == config_data

    @pytest.mark.asyncio
    async def test_read_config_returns_default_on_invalid_json(self, tmp_path):
        """JSON が壊れている場合はデフォルト値を返すこと"""
        config_file = tmp_path / "config.json"
        config_file.write_text("not valid json", encoding="utf-8")

        with patch("src.dashboard.CONFIG_PATH", config_file):
            result = await read_config()

        assert result["user_speakers"] == {}


# ---------------------------------------------------------------------------
# _fetch_voicevox のテスト
# ---------------------------------------------------------------------------

class TestFetchVoicevox:
    """_fetch_voicevox ヘルパーのテスト"""

    @pytest.mark.asyncio
    async def test_fetch_voicevox_returns_ok_on_success(self):
        """200 レスポンスの場合は status: ok とデータを返すこと"""
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.content_type = "application/json"
        mock_resp.json = AsyncMock(return_value={"key": "value"})
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp)

        result = await _fetch_voicevox(mock_session, "/version")

        assert result["status"] == "ok"
        assert result["data"] == {"key": "value"}

    @pytest.mark.asyncio
    async def test_fetch_voicevox_returns_error_on_non_200(self):
        """200 以外のステータスの場合は status: error を返すこと"""
        mock_resp = AsyncMock()
        mock_resp.status = 503
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp)

        result = await _fetch_voicevox(mock_session, "/version")

        assert result["status"] == "error"
        assert result["code"] == 503

    @pytest.mark.asyncio
    async def test_fetch_voicevox_returns_error_on_connection_failure(self):
        """接続に失敗した場合は status: error とメッセージを返すこと"""
        import aiohttp

        mock_session = MagicMock()
        mock_session.get = MagicMock(
            side_effect=aiohttp.ClientConnectorError(
                connection_key=MagicMock(), os_error=OSError("refused")
            )
        )

        result = await _fetch_voicevox(mock_session, "/version")

        assert result["status"] == "error"
        assert "message" in result


# ---------------------------------------------------------------------------
# HTTP エンドポイントのテスト (aiohttp TestClient)
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    """テスト用アプリケーションを返す"""
    return create_app()


class TestHandleIndex:
    """GET / のテスト"""

    @pytest.mark.asyncio
    async def test_index_returns_html(self, aiohttp_client, app):
        """/ は HTML を返すこと"""
        client: TestClient = await aiohttp_client(app)
        resp = await client.get("/")
        assert resp.status == 200
        assert "text/html" in resp.content_type
        text = await resp.text()
        assert "TalkBot2" in text


class TestHandleApiStatus:
    """GET /api/status のテスト"""

    @pytest.mark.asyncio
    async def test_api_status_returns_json_with_counts(self, aiohttp_client, app, tmp_path):
        """設定ファイルの内容が JSON で返ること"""
        config_data = {
            "user_speakers": {"1": 2, "3": 4},
            "user_speeds": {"1": 1.2},
            "guild_configs": {"100": {"read_channel": 200, "dictionary": {"a": "b"}}},
            "joined_guilds": [100, 200, 300],
        }
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config_data), encoding="utf-8")

        with patch("src.dashboard.CONFIG_PATH", config_file):
            client: TestClient = await aiohttp_client(app)
            resp = await client.get("/api/status")
            assert resp.status == 200
            data = await resp.json()

        assert data["guild_count"] == 3
        assert data["user_count"] == 2
        assert data["dictionary_count"] == 1

    @pytest.mark.asyncio
    async def test_api_status_guild_count_uses_joined_guilds_not_guild_configs(self, aiohttp_client, app, tmp_path):
        """guild_count は guild_configs ではなく joined_guilds を使うこと"""
        config_data = {
            "user_speakers": {},
            "user_speeds": {},
            "guild_configs": {"100": {"read_channel": 200}},
            "joined_guilds": [100, 200, 300, 400, 500],
        }
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config_data), encoding="utf-8")

        with patch("src.dashboard.CONFIG_PATH", config_file):
            client: TestClient = await aiohttp_client(app)
            resp = await client.get("/api/status")
            data = await resp.json()

        # guild_configs には 1 件しかないが、joined_guilds は 5 件
        assert data["guild_count"] == 5

    @pytest.mark.asyncio
    async def test_api_status_returns_zeros_when_config_empty(self, aiohttp_client, app, tmp_path):
        """設定が空の場合はカウントが 0 であること"""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({}), encoding="utf-8")

        with patch("src.dashboard.CONFIG_PATH", config_file):
            client: TestClient = await aiohttp_client(app)
            resp = await client.get("/api/status")
            data = await resp.json()

        assert data["guild_count"] == 0
        assert data["user_count"] == 0
        assert data["dictionary_count"] == 0


class TestHandleApiVoicevoxStatus:
    """GET /api/voicevox/status のテスト"""

    @pytest.mark.asyncio
    async def test_voicevox_status_ok(self, aiohttp_client, app):
        """VOICEVOX が正常なら status: ok のレスポンスを返すこと"""
        mock_result = {"status": "ok", "data": "0.14.0"}

        with patch("src.dashboard._fetch_voicevox", new=AsyncMock(return_value=mock_result)):
            client: TestClient = await aiohttp_client(app)
            resp = await client.get("/api/voicevox/status")
            assert resp.status == 200
            data = await resp.json()

        assert data["version"]["status"] == "ok"
        assert "voicevox_url" in data

    @pytest.mark.asyncio
    async def test_voicevox_status_error(self, aiohttp_client, app):
        """VOICEVOX が接続できない場合も 200 を返し error ステータスを含むこと"""
        mock_result = {"status": "error", "message": "接続できません"}

        with patch("src.dashboard._fetch_voicevox", new=AsyncMock(return_value=mock_result)):
            client: TestClient = await aiohttp_client(app)
            resp = await client.get("/api/voicevox/status")
            assert resp.status == 200
            data = await resp.json()

        assert data["version"]["status"] == "error"


class TestHandleApiVoicevoxSpeakers:
    """GET /api/voicevox/speakers のテスト"""

    @pytest.mark.asyncio
    async def test_speakers_ok(self, aiohttp_client, app):
        """話者一覧が正常に返ること"""
        speakers = [{"name": "ずんだもん", "styles": [{"id": 3, "name": "ノーマル"}]}]
        mock_result = {"status": "ok", "data": speakers}

        with patch("src.dashboard._fetch_voicevox", new=AsyncMock(return_value=mock_result)):
            client: TestClient = await aiohttp_client(app)
            resp = await client.get("/api/voicevox/speakers")
            assert resp.status == 200
            data = await resp.json()

        assert data["status"] == "ok"
        assert data["data"][0]["name"] == "ずんだもん"


# ---------------------------------------------------------------------------
# create_app のテスト
# ---------------------------------------------------------------------------

class TestCreateApp:
    """create_app 関数のテスト"""

    def test_create_app_returns_application(self):
        """create_app は web.Application を返すこと"""
        app = create_app()
        assert isinstance(app, web.Application)

    def test_create_app_has_required_routes(self):
        """必要なルートが登録されていること"""
        app = create_app()
        routes = {r.resource.canonical for r in app.router.routes()}
        assert "/" in routes
        assert "/api/status" in routes
        assert "/api/voicevox/status" in routes
        assert "/api/voicevox/speakers" in routes
        assert "/api/metrics" in routes


# ---------------------------------------------------------------------------
# handle_api_metrics のテスト
# ---------------------------------------------------------------------------

class TestHandleApiMetrics:
    """GET /api/metrics のテスト"""

    @pytest.mark.asyncio
    async def test_metrics_returns_json_with_required_keys(self, tmp_path):
        """メトリクス API が latency / errors / commands キーを含む JSON を返すこと"""
        mock_summary = {
            "latency": {"labels": [], "values": [], "avg_ms": None},
            "errors":  {"labels": [], "values": [], "total": 0},
            "commands": {"labels": [], "values": []},
            "granularity": "day",
        }
        request = MagicMock()
        with patch("asyncio.to_thread", new=AsyncMock(return_value=mock_summary)):
            response = await handle_api_metrics(request)
        assert response.status == 200

    @pytest.mark.asyncio
    async def test_metrics_passes_granularity_minute(self, tmp_path):
        """granularity=minute パラメータが get_metrics_summary に渡されること"""
        mock_summary = {
            "latency": {"labels": [], "values": [], "avg_ms": None},
            "errors":  {"labels": [], "values": [], "total": 0},
            "commands": {"labels": [], "values": []},
            "granularity": "minute",
        }
        request = MagicMock()
        request.rel_url.query.get = MagicMock(return_value="minute")
        with patch("asyncio.to_thread", new=AsyncMock(return_value=mock_summary)) as mock_thread:
            response = await handle_api_metrics(request)
        assert response.status == 200
        mock_thread.assert_called_once()

    @pytest.mark.asyncio
    async def test_metrics_passes_granularity_hour(self, tmp_path):
        """granularity=hour パラメータが get_metrics_summary に渡されること"""
        mock_summary = {
            "latency": {"labels": [], "values": [], "avg_ms": None},
            "errors":  {"labels": [], "values": [], "total": 0},
            "commands": {"labels": [], "values": []},
            "granularity": "hour",
        }
        request = MagicMock()
        request.rel_url.query.get = MagicMock(return_value="hour")
        with patch("asyncio.to_thread", new=AsyncMock(return_value=mock_summary)) as mock_thread:
            response = await handle_api_metrics(request)
        assert response.status == 200
        mock_thread.assert_called_once()

    @pytest.mark.asyncio
    async def test_metrics_invalid_granularity_falls_back_to_day(self):
        """不正な granularity の場合は day にフォールバックすること"""
        mock_summary = {
            "latency": {"labels": [], "values": [], "avg_ms": None},
            "errors":  {"labels": [], "values": [], "total": 0},
            "commands": {"labels": [], "values": []},
            "granularity": "day",
        }
        request = MagicMock()
        request.rel_url.query.get = MagicMock(return_value="invalid")
        with patch("asyncio.to_thread", new=AsyncMock(return_value=mock_summary)) as mock_thread:
            response = await handle_api_metrics(request)
        assert response.status == 200
        # フォールバック後は "day" で呼ばれること
        args = mock_thread.call_args[0]
        assert args[1] == "day"
        # レスポンス JSON に granularity: "day" が含まれること
        import json as _json
        body = _json.loads(response.body)
        assert body["granularity"] == "day"

    @pytest.mark.asyncio
    async def test_api_status_dictionary_count_aggregates_per_guild(self, aiohttp_client, app, tmp_path):
        """dictionary_count は全ギルドの辞書エントリ数の合計であること"""
        config_data = {
            "user_speakers": {},
            "user_speeds": {},
            "guild_configs": {
                "100": {"read_channel": 1, "dictionary": {"a": "A", "b": "B"}},
                "200": {"read_channel": 2, "dictionary": {"c": "C"}},
                "300": {"read_channel": 3},
            },
            "joined_guilds": [100, 200, 300],
        }
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config_data), encoding="utf-8")

        with patch("src.dashboard.CONFIG_PATH", config_file):
            client: TestClient = await aiohttp_client(app)
            resp = await client.get("/api/status")
            data = await resp.json()

        assert data["dictionary_count"] == 3
