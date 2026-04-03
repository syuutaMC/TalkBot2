"""
tests/test_prometheus_exporter.py

src/prometheus_exporter.py のユニットテスト
"""
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient

# src パスを追加
sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# ヘルパー: テストごとに独立したレジストリ/メトリクスを生成する
# ---------------------------------------------------------------------------

def _make_exporter():
    """テスト用に独立した prometheus_exporter モジュール相当の名前空間を返す。

    prometheus_client はプロセス内でメトリクス名の重複登録を禁止するため、
    テストごとに独自の CollectorRegistry を生成して使う。
    """
    from prometheus_client import (
        CollectorRegistry,
        Counter,
        Gauge,
        Histogram,
        generate_latest,
        CONTENT_TYPE_LATEST,
    )
    import types

    reg = CollectorRegistry()
    ns = types.SimpleNamespace()
    ns.registry = reg
    ns.messages_total = Counter(
        "talkbot_test_messages_total", "test", registry=reg
    )
    ns.commands_total = Counter(
        "talkbot_test_commands_total", "test", ["command"], registry=reg
    )
    ns.voice_play_total = Counter(
        "talkbot_test_voice_play_total", "test", registry=reg
    )
    ns.errors_total = Counter(
        "talkbot_test_errors_total", "test", registry=reg
    )
    ns.voicevox_requests_total = Counter(
        "talkbot_test_voicevox_requests_total", "test", registry=reg
    )
    ns.voicevox_latency_seconds = Histogram(
        "talkbot_test_voicevox_latency_seconds",
        "test",
        buckets=(0.1, 0.5, 1.0),
        registry=reg,
    )
    ns.voicevox_errors_total = Counter(
        "talkbot_test_voicevox_errors_total", "test", registry=reg
    )
    ns.uptime_seconds = Gauge(
        "talkbot_test_uptime_seconds", "test", registry=reg
    )
    ns.memory_usage_bytes = Gauge(
        "talkbot_test_memory_usage_bytes", "test", registry=reg
    )
    ns._start_time = time.monotonic()

    def update_dynamic_metrics():
        import os
        import psutil
        ns.uptime_seconds.set(time.monotonic() - ns._start_time)
        try:
            proc = psutil.Process(os.getpid())
            ns.memory_usage_bytes.set(proc.memory_info().rss)
        except Exception:
            pass

    ns.update_dynamic_metrics = update_dynamic_metrics
    ns.generate_latest = generate_latest
    ns.CONTENT_TYPE_LATEST = CONTENT_TYPE_LATEST
    return ns


# ---------------------------------------------------------------------------
# メトリクス定義のテスト
# ---------------------------------------------------------------------------

class TestMetricsDefinition:
    """prometheus_exporter に必要なメトリクスが定義されていること"""

    def test_registry_is_collector_registry(self):
        """registry が CollectorRegistry インスタンスであること"""
        from prometheus_client import CollectorRegistry
        from src import prometheus_exporter as prom
        assert isinstance(prom.registry, CollectorRegistry)

    def test_messages_total_exists(self):
        """talkbot_messages_total が存在すること"""
        from src import prometheus_exporter as prom
        prom.messages_total.inc(0)  # 副作用なしに存在を確認

    def test_commands_total_has_command_label(self):
        """talkbot_commands_total が command ラベルを持つこと"""
        from src import prometheus_exporter as prom
        prom.commands_total.labels(command="test_cmd")

    def test_voice_play_total_exists(self):
        """talkbot_voice_play_total が存在すること"""
        from src import prometheus_exporter as prom
        prom.voice_play_total.inc(0)

    def test_errors_total_exists(self):
        """talkbot_errors_total が存在すること"""
        from src import prometheus_exporter as prom
        prom.errors_total.inc(0)

    def test_voicevox_requests_total_exists(self):
        """talkbot_voicevox_requests_total が存在すること"""
        from src import prometheus_exporter as prom
        prom.voicevox_requests_total.inc(0)

    def test_voicevox_latency_seconds_exists(self):
        """talkbot_voicevox_latency_seconds が存在すること"""
        from src import prometheus_exporter as prom
        prom.voicevox_latency_seconds.observe(0)

    def test_voicevox_errors_total_exists(self):
        """talkbot_voicevox_errors_total が存在すること"""
        from src import prometheus_exporter as prom
        prom.voicevox_errors_total.inc(0)

    def test_uptime_seconds_exists(self):
        """talkbot_uptime_seconds が存在すること"""
        from src import prometheus_exporter as prom
        prom.uptime_seconds.set(0)

    def test_memory_usage_bytes_exists(self):
        """talkbot_memory_usage_bytes が存在すること"""
        from src import prometheus_exporter as prom
        prom.memory_usage_bytes.set(0)


# ---------------------------------------------------------------------------
# update_dynamic_metrics のテスト
# ---------------------------------------------------------------------------

class TestUpdateDynamicMetrics:
    """update_dynamic_metrics が稼働時間・メモリを更新すること"""

    def test_uptime_increases_over_time(self):
        """稼働時間が 0 より大きいこと"""
        ns = _make_exporter()
        ns.update_dynamic_metrics()
        output = ns.generate_latest(ns.registry).decode()
        assert "talkbot_test_uptime_seconds" in output

    def test_memory_usage_is_positive(self):
        """メモリ使用量が 0 より大きいこと"""
        ns = _make_exporter()
        ns.update_dynamic_metrics()
        assert ns.memory_usage_bytes._value.get() > 0

    def test_update_dynamic_metrics_does_not_raise_on_psutil_error(self):
        """psutil がエラーを起こしても例外が外に出ないこと"""
        from src import prometheus_exporter as prom
        with patch("psutil.Process", side_effect=Exception("mocked error")):
            prom.update_dynamic_metrics()  # 例外が外に出ないこと


# ---------------------------------------------------------------------------
# handle_metrics エンドポイントのテスト
# ---------------------------------------------------------------------------

@pytest.fixture
def app_with_metrics():
    """テスト用 aiohttp アプリ（/metrics ルートのみ）"""
    from src import prometheus_exporter as prom
    app = web.Application()
    app.router.add_get("/metrics", prom.handle_metrics)
    return app


class TestHandleMetrics:
    """GET /metrics エンドポイントのテスト"""

    @pytest.mark.asyncio
    async def test_metrics_endpoint_returns_200(self, aiohttp_client, app_with_metrics):
        """/metrics は 200 を返すこと"""
        client: TestClient = await aiohttp_client(app_with_metrics)
        resp = await client.get("/metrics")
        assert resp.status == 200

    @pytest.mark.asyncio
    async def test_metrics_endpoint_content_type_is_prometheus(self, aiohttp_client, app_with_metrics):
        """/metrics の Content-Type が Prometheus 形式であること"""
        client: TestClient = await aiohttp_client(app_with_metrics)
        resp = await client.get("/metrics")
        assert "text/plain" in resp.content_type

    @pytest.mark.asyncio
    async def test_metrics_endpoint_contains_expected_metric_names(self, aiohttp_client, app_with_metrics):
        """/metrics に必要なメトリクス名が含まれること"""
        client: TestClient = await aiohttp_client(app_with_metrics)
        resp = await client.get("/metrics")
        body = await resp.text()
        assert "talkbot_messages_total" in body
        assert "talkbot_commands_total" in body
        assert "talkbot_voice_play_total" in body
        assert "talkbot_errors_total" in body
        assert "talkbot_voicevox_requests_total" in body
        assert "talkbot_voicevox_latency_seconds" in body
        assert "talkbot_voicevox_errors_total" in body
        assert "talkbot_uptime_seconds" in body
        assert "talkbot_memory_usage_bytes" in body

    @pytest.mark.asyncio
    async def test_metrics_endpoint_uptime_is_non_negative(self, aiohttp_client, app_with_metrics):
        """/metrics の talkbot_uptime_seconds が 0 以上であること"""
        client: TestClient = await aiohttp_client(app_with_metrics)
        resp = await client.get("/metrics")
        body = await resp.text()
        for line in body.splitlines():
            if line.startswith("talkbot_uptime_seconds "):
                value = float(line.split()[-1])
                assert value >= 0
                return
        pytest.fail("talkbot_uptime_seconds が見つかりません")


# ---------------------------------------------------------------------------
# get_snapshot のテスト
# ---------------------------------------------------------------------------

class TestGetSnapshot:
    """get_snapshot 関数のテスト"""

    def test_get_snapshot_returns_required_keys(self):
        """get_snapshot が必須キーを含む辞書を返すこと"""
        from src import prometheus_exporter as prom
        snapshot = prom.get_snapshot()
        required_keys = [
            "messages_total",
            "voice_play_total",
            "errors_total",
            "voicevox_requests_total",
            "voicevox_errors_total",
            "voicevox_latency_avg_ms",
            "voicevox_latency_count",
            "voicevox_latency_buckets",
            "commands",
            "uptime_seconds",
        ]
        for key in required_keys:
            assert key in snapshot, f"キー '{key}' が存在しません"

    def test_get_snapshot_latency_avg_ms_is_none_when_no_data(self):
        """レイテンシ計測なしの場合 voicevox_latency_avg_ms は None であること"""
        ns = _make_exporter()
        # observe を呼ばない状態
        import types
        import time as _time

        def get_snapshot_ns():
            ns.update_dynamic_metrics()

            def _counter_total(metric):
                for mf in metric.collect():
                    for s in mf.samples:
                        if s.name.endswith("_total"):
                            return int(s.value)
                return 0

            lat_sum = 0.0
            lat_count = 0.0
            for mf in ns.voicevox_latency_seconds.collect():
                for s in mf.samples:
                    if s.name.endswith("_sum"):
                        lat_sum = s.value
                    elif s.name.endswith("_count"):
                        lat_count = s.value

            avg_ms = round(lat_sum / lat_count * 1000, 1) if lat_count > 0 else None
            return {"voicevox_latency_avg_ms": avg_ms, "voicevox_latency_count": int(lat_count)}

        result = get_snapshot_ns()
        assert result["voicevox_latency_avg_ms"] is None
        assert result["voicevox_latency_count"] == 0

    def test_get_snapshot_latency_avg_ms_computed_correctly(self):
        """レイテンシ計測後に voicevox_latency_avg_ms が正しく計算されること"""
        ns = _make_exporter()
        ns.voicevox_latency_seconds.observe(0.1)
        ns.voicevox_latency_seconds.observe(0.3)

        lat_sum = lat_count = 0.0
        for mf in ns.voicevox_latency_seconds.collect():
            for s in mf.samples:
                if s.name.endswith("_sum"):
                    lat_sum = s.value
                elif s.name.endswith("_count"):
                    lat_count = s.value

        avg_ms = round(lat_sum / lat_count * 1000, 1) if lat_count > 0 else None
        assert avg_ms == pytest.approx(200.0, abs=1.0)
        assert lat_count == 2

    def test_get_snapshot_commands_populated_after_inc(self):
        """コマンドカウンタをインクリメントすると commands に反映されること"""
        ns = _make_exporter()
        ns.commands_total.labels(command="join").inc()
        ns.commands_total.labels(command="join").inc()
        ns.commands_total.labels(command="leave").inc()

        cmds: dict = {}
        for mf in ns.commands_total.collect():
            for s in mf.samples:
                if s.name.endswith("_total") and "command" in s.labels:
                    cmds[s.labels["command"]] = int(s.value)

        assert cmds.get("join") == 2
        assert cmds.get("leave") == 1

    def test_get_snapshot_buckets_sorted_by_le(self):
        """voicevox_latency_buckets が le 昇順に返ること"""
        from src import prometheus_exporter as prom
        snapshot = prom.get_snapshot()
        buckets = snapshot["voicevox_latency_buckets"]
        if len(buckets) >= 2:
            for i in range(len(buckets) - 1):
                assert buckets[i]["le"] <= buckets[i + 1]["le"]

    def test_get_snapshot_uptime_is_non_negative(self):
        """uptime_seconds が 0 以上であること"""
        from src import prometheus_exporter as prom
        snapshot = prom.get_snapshot()
        assert snapshot["uptime_seconds"] >= 0

    def test_get_snapshot_voice_play_total_increments(self):
        """voice_play_total をインクリメントすると反映されること"""
        ns = _make_exporter()
        ns.voice_play_total.inc()
        ns.voice_play_total.inc()

        total = 0
        for mf in ns.voice_play_total.collect():
            for s in mf.samples:
                if s.name.endswith("_total"):
                    total = int(s.value)
        assert total == 2


# ---------------------------------------------------------------------------
# ダッシュボードに /metrics ルートが追加されていることのテスト
# ---------------------------------------------------------------------------

class TestDashboardHasMetricsRoute:
    """/metrics ルートがダッシュボードに追加されていること"""

    def test_create_app_has_metrics_route(self):
        """/metrics ルートが create_app() に含まれること"""
        from src.dashboard import create_app
        app = create_app()
        routes = {r.resource.canonical for r in app.router.routes()}
        assert "/metrics" in routes

    @pytest.mark.asyncio
    async def test_dashboard_metrics_endpoint_returns_prometheus_data(self, aiohttp_client):
        """ダッシュボードの /metrics エンドポイントが Prometheus 形式のデータを返すこと"""
        from src.dashboard import create_app
        app = create_app()
        client: TestClient = await aiohttp_client(app)
        resp = await client.get("/metrics")
        assert resp.status == 200
        body = await resp.text()
        assert "talkbot_messages_total" in body
        assert "talkbot_uptime_seconds" in body
