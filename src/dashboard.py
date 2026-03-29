"""
TalkBot2 ダッシュボード

Bot の利用状況と VOICEVOX API のレスポンスを確認するための Web サーバー
ポート: 8080
"""
import json
import os
from pathlib import Path
from typing import Any

import aiohttp
from aiohttp import web

VOICEVOX_URL = os.getenv("VOICEVOX_URL", "http://127.0.0.1:50021")
CONFIG_PATH = Path(os.getenv("CONFIG_PATH", "/app/config/config.json"))
PORT = int(os.getenv("DASHBOARD_PORT", "8080"))

_TEMPLATES_DIR = Path(__file__).parent / "templates"


def _load_config_sync() -> dict:
    """設定ファイルを同期的に読み込む（スレッドプール内で実行）"""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"user_speakers": {}, "user_speeds": {}, "guild_configs": {}, "dictionary": {}}


async def read_config() -> dict:
    """設定ファイルを非同期で読み込む（イベントループをブロックしない）"""
    import asyncio

    try:
        return await asyncio.to_thread(_load_config_sync)
    except Exception as e:
        print(f"設定ファイル読み込みエラー: {e}")
    return {"user_speakers": {}, "user_speeds": {}, "guild_configs": {}, "dictionary": {}}


async def _fetch_voicevox(session: aiohttp.ClientSession, path: str) -> dict[str, Any]:
    """VOICEVOX Engine にリクエストを送って結果を返すヘルパー"""
    timeout = aiohttp.ClientTimeout(total=5)
    try:
        async with session.get(f"{VOICEVOX_URL}{path}", timeout=timeout) as resp:
            if resp.status == 200:
                content_type = resp.content_type or ""
                if "json" in content_type:
                    data = await resp.json()
                else:
                    data = await resp.text()
                return {"status": "ok", "data": data}
            return {"status": "error", "code": resp.status}
    except aiohttp.ClientConnectorError:
        return {"status": "error", "message": "VOICEVOX Engine に接続できません"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# HTTP ハンドラー
# ---------------------------------------------------------------------------

async def handle_index(request: web.Request) -> web.Response:
    """ダッシュボード HTML を返す"""
    content = (_TEMPLATES_DIR / "index.html").read_text(encoding="utf-8")
    return web.Response(text=content, content_type="text/html")


async def handle_api_status(request: web.Request) -> web.Response:
    """Bot の設定・利用状況を JSON で返す"""
    config = await read_config()
    data = {
        "guild_count": len(config.get("guild_configs", {})),
        "user_count": len(config.get("user_speakers", {})),
        "dictionary_count": len(config.get("dictionary", {})),
        "guild_configs": config.get("guild_configs", {}),
        "user_speakers": config.get("user_speakers", {}),
        "user_speeds": config.get("user_speeds", {}),
        "dictionary": config.get("dictionary", {}),
    }
    return web.json_response(data)


async def handle_api_voicevox_status(request: web.Request) -> web.Response:
    """VOICEVOX Engine のバージョン情報を JSON で返す"""
    async with aiohttp.ClientSession() as session:
        version_result = await _fetch_voicevox(session, "/version")
    return web.json_response({"voicevox_url": VOICEVOX_URL, "version": version_result})


async def handle_api_voicevox_speakers(request: web.Request) -> web.Response:
    """VOICEVOX Engine の話者一覧を JSON で返す"""
    async with aiohttp.ClientSession() as session:
        result = await _fetch_voicevox(session, "/speakers")
    return web.json_response(result)


# ---------------------------------------------------------------------------
# アプリケーション構築
# ---------------------------------------------------------------------------

def create_app() -> web.Application:
    """Web アプリケーションを生成して返す"""
    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/api/status", handle_api_status)
    app.router.add_get("/api/voicevox/status", handle_api_voicevox_status)
    app.router.add_get("/api/voicevox/speakers", handle_api_voicevox_speakers)
    return app


if __name__ == "__main__":
    app = create_app()
    print(f"ダッシュボードを起動します: http://0.0.0.0:{PORT}")
    web.run_app(app, host="0.0.0.0", port=PORT)
