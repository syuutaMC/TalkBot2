"""
Prometheus Exporter モジュール

TalkBot2 のメトリクスを Prometheus 形式で公開します。
ダッシュボードの /metrics エンドポイントで利用されます。
"""
import os
import time
from typing import Any, Optional

import psutil
from aiohttp import web
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# ---------------------------------------------------------------------------
# Prometheus レジストリと各メトリクスの定義
# ---------------------------------------------------------------------------

# デフォルトのグローバルレジストリを使わずに独自レジストリを使うことで、
# テスト間の干渉やプロセス組み込みメトリクスの混入を防ぐ
registry = CollectorRegistry()

# --- Bot イベント ---
messages_total = Counter(
    "talkbot_messages_total",
    "受信したメッセージの総数",
    registry=registry,
)

commands_total = Counter(
    "talkbot_commands_total",
    "スラッシュコマンドの実行数",
    ["command"],
    registry=registry,
)

voice_play_total = Counter(
    "talkbot_voice_play_total",
    "音声再生の回数",
    registry=registry,
)

errors_total = Counter(
    "talkbot_errors_total",
    "Bot 内部エラーの総数",
    registry=registry,
)

# --- VOICEVOX 関連 ---
voicevox_requests_total = Counter(
    "talkbot_voicevox_requests_total",
    "VOICEVOX API の呼び出し回数",
    registry=registry,
)

voicevox_latency_seconds = Histogram(
    "talkbot_voicevox_latency_seconds",
    "VOICEVOX 音声生成のレイテンシ（秒）",
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=registry,
)

voicevox_errors_total = Counter(
    "talkbot_voicevox_errors_total",
    "VOICEVOX API のエラー数",
    registry=registry,
)

# --- システム情報 ---
uptime_seconds = Gauge(
    "talkbot_uptime_seconds",
    "Bot プロセスの稼働時間（秒）",
    registry=registry,
)

memory_usage_bytes = Gauge(
    "talkbot_memory_usage_bytes",
    "Bot プロセスのメモリ使用量（バイト）",
    registry=registry,
)

# ---------------------------------------------------------------------------
# 起動時刻の記録
# ---------------------------------------------------------------------------

_start_time: float = time.monotonic()


def update_dynamic_metrics() -> None:
    """稼働時間・メモリ使用量など動的に変わるゲージを更新する"""
    uptime_seconds.set(time.monotonic() - _start_time)
    try:
        proc = psutil.Process(os.getpid())
        memory_usage_bytes.set(proc.memory_info().rss)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# aiohttp ハンドラー
# ---------------------------------------------------------------------------

def _collect_all() -> list:
    """現在のモードに応じてすべてのメトリクスを収集して返す。

    PROMETHEUS_MULTIPROC_DIR が設定されている場合はマルチプロセスモード
    （ファイルベース）で全プロセス分を集約し、未設定の場合はモジュールレベルの
    レジストリから収集する。
    """
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        from prometheus_client import multiprocess as _mp
        mp_reg = CollectorRegistry()
        _mp.MultiProcessCollector(mp_reg)
        return list(mp_reg.collect())
    return list(registry.collect())


def get_snapshot() -> dict[str, Any]:
    """ダッシュボード用に Prometheus メトリクスの現在値をスナップショットとして返す。

    Returns:
        dict: 以下のキーを持つ辞書
            messages_total            : 受信メッセージ数（累積）
            voice_play_total          : 音声再生回数（累積）
            errors_total              : Bot 内部エラー数（累積）
            voicevox_requests_total   : VOICEVOX API 呼び出し数（累積）
            voicevox_errors_total     : VOICEVOX エラー数（累積）
            voicevox_latency_avg_ms   : VOICEVOX レイテンシ平均値（ms）、データなしは None
            voicevox_latency_count    : レイテンシ計測件数
            voicevox_latency_buckets  : ヒストグラムバケット [{le, count}, ...]
            commands                  : コマンド別累積実行数 {name: count}
            uptime_seconds            : 稼働時間（秒）
    """
    update_dynamic_metrics()

    collected = _collect_all()

    def _counter_total(sample_name: str) -> int:
        """指定されたサンプル名（_total 付き）の値をすべてのプロセス分合計して返す。"""
        total = 0
        for mf in collected:
            for s in mf.samples:
                if s.name == sample_name and not s.labels:
                    total += int(s.value)
        return total

    # コマンド別カウント
    cmds: dict[str, int] = {}
    # レイテンシヒストグラム
    lat_sum = 0.0
    lat_count = 0.0
    lat_buckets_map: dict[float, int] = {}

    for mf in collected:
        for s in mf.samples:
            # コマンドカウンター（command ラベル付き）
            if s.name == "talkbot_commands_total" and s.labels.get("command") is not None:
                cmd = s.labels["command"]
                cmds[cmd] = cmds.get(cmd, 0) + int(s.value)
            # ヒストグラム（メトリクスファミリー名で絞り込む）
            if mf.name == "talkbot_voicevox_latency_seconds":
                if s.name.endswith("_sum"):
                    lat_sum += s.value
                elif s.name.endswith("_count"):
                    lat_count += s.value
                elif s.name.endswith("_bucket") and s.labels.get("le") != "+Inf":
                    le_val = float(s.labels["le"])
                    lat_buckets_map[le_val] = lat_buckets_map.get(le_val, 0) + int(s.value)

    avg_ms: Optional[float] = round(lat_sum / lat_count * 1000, 1) if lat_count > 0 else None
    lat_buckets = sorted(
        [{"le": le, "count": cnt} for le, cnt in lat_buckets_map.items()],
        key=lambda x: x["le"],
    )

    return {
        "messages_total": _counter_total("talkbot_messages_total"),
        "voice_play_total": _counter_total("talkbot_voice_play_total"),
        "errors_total": _counter_total("talkbot_errors_total"),
        "voicevox_requests_total": _counter_total("talkbot_voicevox_requests_total"),
        "voicevox_errors_total": _counter_total("talkbot_voicevox_errors_total"),
        "voicevox_latency_avg_ms": avg_ms,
        "voicevox_latency_count": int(lat_count),
        "voicevox_latency_buckets": lat_buckets,
        "commands": cmds,
        "uptime_seconds": round(time.monotonic() - _start_time, 1),
    }


async def handle_metrics(_request: web.Request) -> web.Response:
    """Prometheus 形式のメトリクスを返すエンドポイント"""
    update_dynamic_metrics()
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        from prometheus_client import multiprocess as _mp
        mp_reg = CollectorRegistry()
        _mp.MultiProcessCollector(mp_reg)
        output = generate_latest(mp_reg)
    else:
        output = generate_latest(registry)
    return web.Response(
        body=output,
        headers={"Content-Type": CONTENT_TYPE_LATEST},
    )
