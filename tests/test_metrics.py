"""
tests/test_metrics.py

src/metrics.py のユニットテスト
"""
import json
import sys
import time
import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

# src パスを追加
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.metrics import (
    _cleanup_old_data,
    _load_metrics_sync,
    _save_metrics_sync,
    get_metrics_summary,
    record_command,
    record_error,
    record_latency,
    record_tts_request,
    RETENTION_DAYS,
    JST,
)


# ---------------------------------------------------------------------------
# _load_metrics_sync / _save_metrics_sync のテスト
# ---------------------------------------------------------------------------

class TestLoadSaveMetrics:
    """メトリクスファイルの読み書きテスト"""

    def test_load_returns_default_when_file_missing(self, tmp_path):
        """ファイルが存在しない場合はデフォルト値を返すこと"""
        missing = tmp_path / "metrics.json"
        with patch("src.metrics.METRICS_PATH", missing):
            data = _load_metrics_sync()
        assert data == {"latency": [], "errors": [], "tts_requests": [], "commands": {}}

    def test_load_returns_file_content(self, tmp_path):
        """ファイルが存在する場合はその内容を返すこと"""
        content = {"latency": [{"ts": 1.0, "ms": 100.0}], "errors": [], "commands": {}}
        f = tmp_path / "metrics.json"
        f.write_text(json.dumps(content), encoding="utf-8")
        with patch("src.metrics.METRICS_PATH", f):
            data = _load_metrics_sync()
        assert data["latency"][0]["ms"] == 100.0

    def test_load_returns_default_on_invalid_json(self, tmp_path):
        """JSON が壊れている場合はデフォルト値を返すこと"""
        f = tmp_path / "metrics.json"
        f.write_text("not valid json", encoding="utf-8")
        with patch("src.metrics.METRICS_PATH", f):
            data = _load_metrics_sync()
        assert data == {"latency": [], "errors": [], "tts_requests": [], "commands": {}}

    def test_save_creates_file(self, tmp_path):
        """保存するとファイルが作成されること"""
        f = tmp_path / "metrics.json"
        with patch("src.metrics.METRICS_PATH", f):
            _save_metrics_sync({"latency": [], "errors": [], "commands": {}})
        assert f.exists()
        assert json.loads(f.read_text())["latency"] == []


# ---------------------------------------------------------------------------
# _cleanup_old_data のテスト
# ---------------------------------------------------------------------------

class TestCleanupOldData:
    """30 日より古いデータの削除テスト"""

    def test_cleanup_removes_old_latency(self):
        """30 日より古いレイテンシが削除されること"""
        old_ts = time.time() - (RETENTION_DAYS + 1) * 86400
        new_ts = time.time() - 3600
        data = {
            "latency": [{"ts": old_ts, "ms": 100.0}, {"ts": new_ts, "ms": 200.0}],
            "errors": [],
            "commands": {},
        }
        result = _cleanup_old_data(data)
        assert len(result["latency"]) == 1
        assert result["latency"][0]["ms"] == 200.0

    def test_cleanup_removes_old_errors(self):
        """30 日より古いエラーが削除されること"""
        old_ts = time.time() - (RETENTION_DAYS + 1) * 86400
        new_ts = time.time()
        data = {
            "latency": [],
            "errors": [{"ts": old_ts}, {"ts": new_ts}],
            "commands": {},
        }
        result = _cleanup_old_data(data)
        assert len(result["errors"]) == 1

    def test_cleanup_removes_old_commands(self):
        """30 日より古いコマンド使用履歴が削除されること"""
        old_ts = time.time() - (RETENTION_DAYS + 1) * 86400
        new_ts = time.time()
        data = {
            "latency": [],
            "errors": [],
            "commands": {"join": [{"ts": old_ts}, {"ts": new_ts}]},
        }
        result = _cleanup_old_data(data)
        assert len(result["commands"]["join"]) == 1


# ---------------------------------------------------------------------------
# record_* 関数のテスト
# ---------------------------------------------------------------------------

class TestRecordFunctions:
    """メトリクス記録関数のテスト"""

    def test_record_latency_appends_entry(self, tmp_path):
        """record_latency がエントリを追加すること"""
        f = tmp_path / "metrics.json"
        with patch("src.metrics.METRICS_PATH", f):
            record_latency(123.45)
            data = _load_metrics_sync()
        assert len(data["latency"]) == 1
        assert data["latency"][0]["ms"] == 123.45

    def test_record_error_appends_entry(self, tmp_path):
        """record_error がエントリを追加すること"""
        f = tmp_path / "metrics.json"
        with patch("src.metrics.METRICS_PATH", f):
            record_error()
            data = _load_metrics_sync()
        assert len(data["errors"]) == 1
        assert "ts" in data["errors"][0]

    def test_record_command_appends_entry(self, tmp_path):
        """record_command がコマンドエントリを追加すること"""
        f = tmp_path / "metrics.json"
        with patch("src.metrics.METRICS_PATH", f):
            record_command("join")
            record_command("join")
            record_command("leave")
            data = _load_metrics_sync()
        assert len(data["commands"]["join"]) == 2
        assert len(data["commands"]["leave"]) == 1

    def test_record_latency_does_not_raise_on_io_error(self, tmp_path):
        """ファイル I/O エラーが発生しても例外を送出しないこと"""
        read_only_dir = tmp_path / "ro"
        read_only_dir.mkdir()
        f = read_only_dir / "sub" / "metrics.json"
        with patch("src.metrics.METRICS_PATH", f), \
             patch("src.metrics._save_metrics_sync", side_effect=OSError("disk full")):
            # 例外が外に出ないこと
            record_latency(10.0)

    def test_record_tts_request_appends_entry(self, tmp_path):
        """record_tts_request がエントリを追加すること"""
        f = tmp_path / "metrics.json"
        with patch("src.metrics.METRICS_PATH", f):
            record_tts_request()
            record_tts_request()
            data = _load_metrics_sync()
        assert len(data["tts_requests"]) == 2
        assert "ts" in data["tts_requests"][0]

    def test_record_tts_request_does_not_raise_on_io_error(self, tmp_path):
        """ファイル I/O エラーが発生しても例外を送出しないこと"""
        f = tmp_path / "sub" / "metrics.json"
        with patch("src.metrics.METRICS_PATH", f), \
             patch("src.metrics._save_metrics_sync", side_effect=OSError("disk full")):
            record_tts_request()


# ---------------------------------------------------------------------------
# get_metrics_summary のテスト
# ---------------------------------------------------------------------------

class TestGetMetricsSummary:
    """get_metrics_summary のテスト"""

    def test_summary_has_required_keys(self, tmp_path):
        """返り値に latency / errors / tts_requests / commands キーがあること"""
        f = tmp_path / "metrics.json"
        with patch("src.metrics.METRICS_PATH", f):
            summary = get_metrics_summary()
        assert "latency" in summary
        assert "errors" in summary
        assert "tts_requests" in summary
        assert "commands" in summary

    def test_latency_labels_length_equals_30(self, tmp_path):
        """latency の labels が 30 件であること"""
        f = tmp_path / "metrics.json"
        with patch("src.metrics.METRICS_PATH", f):
            summary = get_metrics_summary()
        assert len(summary["latency"]["labels"]) == RETENTION_DAYS

    def test_errors_labels_length_equals_30(self, tmp_path):
        """errors の labels が 30 件であること"""
        f = tmp_path / "metrics.json"
        with patch("src.metrics.METRICS_PATH", f):
            summary = get_metrics_summary()
        assert len(summary["errors"]["labels"]) == RETENTION_DAYS

    def test_avg_ms_none_when_no_data(self, tmp_path):
        """データがない場合 avg_ms が None であること"""
        f = tmp_path / "metrics.json"
        with patch("src.metrics.METRICS_PATH", f):
            summary = get_metrics_summary()
        assert summary["latency"]["avg_ms"] is None
        assert summary["latency"]["min_ms"] is None
        assert summary["latency"]["max_ms"] is None

    def test_avg_ms_calculated_correctly(self, tmp_path):
        """avg_ms がすべてのデータ点の平均であること"""
        f = tmp_path / "metrics.json"
        now_ts = time.time()
        content = {
            "latency": [
                {"ts": now_ts, "ms": 100.0},
                {"ts": now_ts - 3600, "ms": 200.0},
            ],
            "errors": [],
            "tts_requests": [],
            "commands": {},
        }
        f.write_text(json.dumps(content), encoding="utf-8")
        with patch("src.metrics.METRICS_PATH", f):
            summary = get_metrics_summary()
        assert summary["latency"]["avg_ms"] == 150.0
        assert summary["latency"]["min_ms"] == 100.0
        assert summary["latency"]["max_ms"] == 200.0

    def test_errors_total_counted_correctly(self, tmp_path):
        """errors.total が正しくカウントされること"""
        f = tmp_path / "metrics.json"
        now_ts = time.time()
        content = {
            "latency": [],
            "errors": [{"ts": now_ts}, {"ts": now_ts - 60}],
            "commands": {},
        }
        f.write_text(json.dumps(content), encoding="utf-8")
        with patch("src.metrics.METRICS_PATH", f):
            summary = get_metrics_summary()
        assert summary["errors"]["total"] == 2

    def test_commands_aggregated_correctly(self, tmp_path):
        """コマンド使用回数が集計されること"""
        f = tmp_path / "metrics.json"
        now_ts = time.time()
        content = {
            "latency": [],
            "errors": [],
            "tts_requests": [],
            "commands": {
                "join": [{"ts": now_ts}, {"ts": now_ts - 60}],
                "leave": [{"ts": now_ts}],
            },
        }
        f.write_text(json.dumps(content), encoding="utf-8")
        with patch("src.metrics.METRICS_PATH", f):
            summary = get_metrics_summary()
        cmd_map = dict(zip(summary["commands"]["labels"], summary["commands"]["values"]))
        assert cmd_map["join"] == 2
        assert cmd_map["leave"] == 1

    def test_tts_requests_total_counted_correctly(self, tmp_path):
        """tts_requests.total が正しくカウントされること"""
        f = tmp_path / "metrics.json"
        now_ts = time.time()
        content = {
            "latency": [],
            "errors": [],
            "tts_requests": [{"ts": now_ts}, {"ts": now_ts - 60}, {"ts": now_ts - 120}],
            "commands": {},
        }
        f.write_text(json.dumps(content), encoding="utf-8")
        with patch("src.metrics.METRICS_PATH", f):
            summary = get_metrics_summary()
        assert summary["tts_requests"]["total"] == 3
        assert len(summary["tts_requests"]["labels"]) == RETENTION_DAYS
        assert len(summary["tts_requests"]["values"]) == RETENTION_DAYS


# ---------------------------------------------------------------------------
# get_metrics_summary の granularity パラメータのテスト
# ---------------------------------------------------------------------------

class TestGetMetricsSummaryGranularity:
    """get_metrics_summary の granularity パラメータのテスト"""

    def test_summary_includes_granularity_key(self, tmp_path):
        """返り値に granularity キーがあること"""
        f = tmp_path / "metrics.json"
        with patch("src.metrics.METRICS_PATH", f):
            summary = get_metrics_summary()
        assert "granularity" in summary
        assert summary["granularity"] == "day"

    def test_granularity_day_returns_30_labels(self, tmp_path):
        """granularity='day' の場合 labels が 30 件であること"""
        f = tmp_path / "metrics.json"
        with patch("src.metrics.METRICS_PATH", f):
            summary = get_metrics_summary(granularity="day")
        assert len(summary["latency"]["labels"]) == RETENTION_DAYS
        assert len(summary["errors"]["labels"]) == RETENTION_DAYS
        assert summary["granularity"] == "day"

    def test_granularity_hour_returns_24_labels(self, tmp_path):
        """granularity='hour' の場合 labels が 24 件であること"""
        f = tmp_path / "metrics.json"
        with patch("src.metrics.METRICS_PATH", f):
            summary = get_metrics_summary(granularity="hour")
        assert len(summary["latency"]["labels"]) == 24
        assert len(summary["errors"]["labels"]) == 24
        assert summary["granularity"] == "hour"

    def test_granularity_minute_returns_60_labels(self, tmp_path):
        """granularity='minute' の場合 labels が 60 件であること"""
        f = tmp_path / "metrics.json"
        with patch("src.metrics.METRICS_PATH", f):
            summary = get_metrics_summary(granularity="minute")
        assert len(summary["latency"]["labels"]) == 60
        assert len(summary["errors"]["labels"]) == 60
        assert summary["granularity"] == "minute"

    def test_invalid_granularity_falls_back_to_day(self, tmp_path):
        """不正な granularity は 'day' にフォールバックすること"""
        f = tmp_path / "metrics.json"
        with patch("src.metrics.METRICS_PATH", f):
            summary = get_metrics_summary(granularity="week")
        assert len(summary["latency"]["labels"]) == RETENTION_DAYS
        assert summary["granularity"] == "day"

    def test_granularity_minute_aggregates_same_minute(self, tmp_path):
        """granularity='minute' で同じ分のデータが正しく集計されること"""
        f = tmp_path / "metrics.json"
        now_ts = time.time()
        content = {
            "latency": [
                {"ts": now_ts, "ms": 100.0},
                {"ts": now_ts - 30, "ms": 200.0},  # 同じ分（30秒前）
            ],
            "errors": [{"ts": now_ts}],
            "commands": {},
        }
        f.write_text(json.dumps(content), encoding="utf-8")
        with patch("src.metrics.METRICS_PATH", f):
            summary = get_metrics_summary(granularity="minute")
        assert summary["latency"]["avg_ms"] == 150.0
        assert summary["errors"]["total"] == 1

    def test_granularity_hour_aggregates_same_hour(self, tmp_path):
        """granularity='hour' で同じ時間のデータが正しく集計されること"""
        f = tmp_path / "metrics.json"
        now_ts = time.time()
        content = {
            "latency": [
                {"ts": now_ts, "ms": 100.0},
                {"ts": now_ts - 1800, "ms": 200.0},  # 同じ時間（30分前）
            ],
            "errors": [{"ts": now_ts}, {"ts": now_ts - 1800}],
            "commands": {},
        }
        f.write_text(json.dumps(content), encoding="utf-8")
        with patch("src.metrics.METRICS_PATH", f):
            summary = get_metrics_summary(granularity="hour")
        assert summary["latency"]["avg_ms"] == 150.0
        assert summary["errors"]["total"] == 2

    def test_granularity_minute_excludes_old_data(self, tmp_path):
        """granularity='minute' で 60 分より古いデータが含まれないこと"""
        f = tmp_path / "metrics.json"
        now_ts = time.time()
        content = {
            "latency": [
                {"ts": now_ts, "ms": 100.0},
                {"ts": now_ts - 7200, "ms": 999.0},  # 2時間前（対象外）
            ],
            "errors": [{"ts": now_ts - 7200}],  # 2時間前（対象外）
            "commands": {},
        }
        f.write_text(json.dumps(content), encoding="utf-8")
        with patch("src.metrics.METRICS_PATH", f):
            summary = get_metrics_summary(granularity="minute")
        assert summary["latency"]["avg_ms"] == 100.0
        assert summary["errors"]["total"] == 0

    def test_granularity_hour_excludes_old_data(self, tmp_path):
        """granularity='hour' で 24 時間より古いデータが含まれないこと"""
        f = tmp_path / "metrics.json"
        now_ts = time.time()
        content = {
            "latency": [
                {"ts": now_ts, "ms": 100.0},
                {"ts": now_ts - 90000, "ms": 999.0},  # 25時間前（対象外）
            ],
            "errors": [{"ts": now_ts - 90000}],  # 25時間前（対象外）
            "commands": {},
        }
        f.write_text(json.dumps(content), encoding="utf-8")
        with patch("src.metrics.METRICS_PATH", f):
            summary = get_metrics_summary(granularity="hour")
        assert summary["latency"]["avg_ms"] == 100.0
        assert summary["errors"]["total"] == 0


# ---------------------------------------------------------------------------
# JST タイムゾーンのテスト
# ---------------------------------------------------------------------------

class TestJstTimezone:
    """時刻ラベルが JST (UTC+9) で生成されることのテスト"""

    def test_jst_offset_is_plus_9(self):
        """JST は UTC+9 であること"""
        assert JST.utcoffset(None) == datetime.timedelta(hours=9)

    def test_labels_use_jst_not_utc(self, tmp_path):
        """ラベルが UTC ではなく JST の時刻で生成されること"""
        f = tmp_path / "metrics.json"
        with patch("src.metrics.METRICS_PATH", f):
            summary = get_metrics_summary(granularity="day")

        now_jst = datetime.datetime.now(JST)
        today_jst = now_jst.strftime("%Y-%m-%d")
        # 最後のラベル（最新のバケット）が JST の今日であること
        assert summary["latency"]["labels"][-1] == today_jst

    def test_minute_labels_use_jst_current_time(self, tmp_path):
        """granularity='minute' のラベルが JST の現在時刻を含むこと"""
        f = tmp_path / "metrics.json"
        with patch("src.metrics.METRICS_PATH", f):
            summary = get_metrics_summary(granularity="minute")

        now_jst = datetime.datetime.now(JST)
        current_minute_jst = now_jst.strftime("%H:%M")
        assert summary["latency"]["labels"][-1] == current_minute_jst
