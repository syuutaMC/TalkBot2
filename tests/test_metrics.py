"""
tests/test_metrics.py

src/metrics.py のユニットテスト
"""
import json
import sys
import time
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
    RETENTION_DAYS,
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
        assert data == {"latency": [], "errors": [], "commands": {}}

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
        assert data == {"latency": [], "errors": [], "commands": {}}

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


# ---------------------------------------------------------------------------
# get_metrics_summary のテスト
# ---------------------------------------------------------------------------

class TestGetMetricsSummary:
    """get_metrics_summary のテスト"""

    def test_summary_has_required_keys(self, tmp_path):
        """返り値に latency / errors / commands キーがあること"""
        f = tmp_path / "metrics.json"
        with patch("src.metrics.METRICS_PATH", f):
            summary = get_metrics_summary()
        assert "latency" in summary
        assert "errors" in summary
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
            "commands": {},
        }
        f.write_text(json.dumps(content), encoding="utf-8")
        with patch("src.metrics.METRICS_PATH", f):
            summary = get_metrics_summary()
        assert summary["latency"]["avg_ms"] == 150.0

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
