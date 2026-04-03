"""
Prometheus Exporter モジュール

TalkBot2 のメトリクスを Prometheus 形式で公開します。
ダッシュボードの /metrics エンドポイントで利用されます。
"""
import os
import time
from typing import Optional

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

async def handle_metrics(_request: web.Request) -> web.Response:
    """Prometheus 形式のメトリクスを返すエンドポイント"""
    update_dynamic_metrics()
    output = generate_latest(registry)
    return web.Response(
        body=output,
        headers={"Content-Type": CONTENT_TYPE_LATEST},
    )
