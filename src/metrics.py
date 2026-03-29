"""
メトリクス管理モジュール

VOICEVOX Engine へのレイテンシ、音声生成エラー数、コマンド使用回数を記録し、
30 日間のデータを保持します。
データは config/metrics.json に JSON 形式で保存されます。
"""
import json
import os
import time
import datetime
from pathlib import Path
from typing import Optional

METRICS_PATH = Path(os.getenv("METRICS_PATH", "config/metrics.json"))
RETENTION_DAYS = 30

JST = datetime.timezone(datetime.timedelta(hours=9))


def _load_metrics_sync() -> dict:
    """メトリクスファイルを同期的に読み込む"""
    if METRICS_PATH.exists():
        try:
            with open(METRICS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"latency": [], "errors": [], "commands": {}}


def _save_metrics_sync(data: dict) -> None:
    """メトリクスファイルを同期的に保存する"""
    METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(METRICS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def _cutoff_timestamp() -> float:
    """30 日前のタイムスタンプを返す"""
    return time.time() - RETENTION_DAYS * 86400


def _cleanup_old_data(data: dict) -> dict:
    """30 日より古いデータを削除する"""
    cutoff = _cutoff_timestamp()
    data["latency"] = [p for p in data.get("latency", []) if p["ts"] >= cutoff]
    data["errors"] = [p for p in data.get("errors", []) if p["ts"] >= cutoff]
    commands = data.get("commands", {})
    for cmd in list(commands.keys()):
        commands[cmd] = [e for e in commands[cmd] if e["ts"] >= cutoff]
    data["commands"] = commands
    return data


def record_latency(ms: float) -> None:
    """VOICEVOX Engine へのレイテンシ（ミリ秒）を記録する"""
    try:
        data = _load_metrics_sync()
        data = _cleanup_old_data(data)
        data["latency"].append({"ts": time.time(), "ms": round(ms, 2)})
        _save_metrics_sync(data)
    except Exception as e:
        print(f"メトリクス記録エラー (latency): {e}")


def record_error() -> None:
    """音声生成エラーを 1 件記録する"""
    try:
        data = _load_metrics_sync()
        data = _cleanup_old_data(data)
        data["errors"].append({"ts": time.time()})
        _save_metrics_sync(data)
    except Exception as e:
        print(f"メトリクス記録エラー (error): {e}")


def record_command(command_name: str) -> None:
    """コマンド使用回数を記録する"""
    try:
        data = _load_metrics_sync()
        data = _cleanup_old_data(data)
        if command_name not in data["commands"]:
            data["commands"][command_name] = []
        data["commands"][command_name].append({"ts": time.time()})
        _save_metrics_sync(data)
    except Exception as e:
        print(f"メトリクス記録エラー (command): {e}")


def get_metrics_summary(granularity: str = "day") -> dict:
    """ダッシュボード用にメトリクスを集計して返す

    Args:
        granularity (str): 集計単位。"minute"（過去60分）, "hour"（過去24時間）,
                           "day"（過去30日）のいずれか。デフォルトは "day"。

    Returns:
        dict: 以下のキーを持つ辞書
            latency     : labels (時刻ラベルリスト), values (各バケット平均 ms), avg_ms (期間平均)
            errors      : labels (時刻ラベルリスト), values (各バケット件数),  total (期間合計件数)
            commands    : labels (コマンド名リスト), values (使用回数リスト)
            granularity : 集計単位
    """
    if granularity not in ("minute", "hour", "day"):
        granularity = "day"

    data = _load_metrics_sync()
    data = _cleanup_old_data(data)

    now_jst = datetime.datetime.now(JST)

    if granularity == "minute":
        num_buckets = 60
        delta = datetime.timedelta(minutes=1)
        label_fmt = "%H:%M"
        key_fmt = "%Y-%m-%dT%H:%M"
    elif granularity == "hour":
        num_buckets = 24
        delta = datetime.timedelta(hours=1)
        label_fmt = "%m-%d %H:00"
        key_fmt = "%Y-%m-%dT%H"
    else:  # "day"
        num_buckets = RETENTION_DAYS
        delta = datetime.timedelta(days=1)
        label_fmt = "%Y-%m-%d"
        key_fmt = "%Y-%m-%d"

    buckets = [now_jst - delta * i for i in range(num_buckets - 1, -1, -1)]
    labels = [b.strftime(label_fmt) for b in buckets]
    keys = [b.strftime(key_fmt) for b in buckets]
    key_set = set(keys)

    def _ts_to_key(ts: float) -> str:
        return datetime.datetime.fromtimestamp(ts, JST).strftime(key_fmt)

    # ----- レイテンシ（各バケットの平均） -----
    latency_by_bucket: dict[str, list[float]] = {k: [] for k in keys}
    for point in data.get("latency", []):
        k = _ts_to_key(point["ts"])
        if k in key_set:
            latency_by_bucket[k].append(point["ms"])

    latency_values: list[Optional[float]] = []
    for k in keys:
        vals = latency_by_bucket[k]
        latency_values.append(round(sum(vals) / len(vals), 1) if vals else None)

    all_latencies = [p["ms"] for p in data.get("latency", []) if _ts_to_key(p["ts"]) in key_set]
    avg_ms: Optional[float] = (
        round(sum(all_latencies) / len(all_latencies), 1) if all_latencies else None
    )

    # ----- エラー（各バケットの件数） -----
    errors_by_bucket: dict[str, int] = {k: 0 for k in keys}
    for point in data.get("errors", []):
        k = _ts_to_key(point["ts"])
        if k in key_set:
            errors_by_bucket[k] += 1

    error_values = [errors_by_bucket[k] for k in keys]

    # ----- コマンド使用回数 -----
    commands = data.get("commands", {})
    command_labels = sorted(commands.keys())
    command_values = [len(commands[cmd]) for cmd in command_labels]

    return {
        "latency": {
            "labels": labels,
            "values": latency_values,
            "avg_ms": avg_ms,
        },
        "errors": {
            "labels": labels,
            "values": error_values,
            "total": sum(error_values),
        },
        "commands": {
            "labels": command_labels,
            "values": command_values,
        },
        "granularity": granularity,
    }
