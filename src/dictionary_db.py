"""
SQLite-based dictionary storage for per-guild word replacement.
"""
import sqlite3
from pathlib import Path
from typing import Dict


class DictionaryDB:
    """ギルド別読み上げ辞書をSQLiteで管理するクラス"""

    def __init__(self, db_path: Path):
        """
        SQLite辞書データベースを初期化する

        Args:
            db_path (Path): SQLiteデータベースファイルのパス
        """
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _initialize(self) -> None:
        """データベーステーブルを作成する（存在しない場合のみ）"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS dictionary (
                    guild_id INTEGER NOT NULL,
                    word     TEXT    NOT NULL,
                    reading  TEXT    NOT NULL,
                    PRIMARY KEY (guild_id, word)
                )
                """
            )

    def add(self, guild_id: int, word: str, reading: str) -> None:
        """辞書エントリを追加または上書きする

        Args:
            guild_id (int): DiscordギルドID
            word (str): 変換前のテキスト
            reading (str): 変換後のテキスト
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO dictionary (guild_id, word, reading) VALUES (?, ?, ?)",
                (guild_id, word, reading),
            )

    def remove(self, guild_id: int, word: str) -> bool:
        """辞書エントリを削除する

        Args:
            guild_id (int): DiscordギルドID
            word (str): 削除する変換前テキスト

        Returns:
            bool: エントリが存在して削除された場合は True
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM dictionary WHERE guild_id = ? AND word = ?",
                (guild_id, word),
            )
            return cursor.rowcount > 0

    def get_all(self, guild_id: int) -> Dict[str, str]:
        """ギルドの辞書エントリを全て返す

        Args:
            guild_id (int): DiscordギルドID

        Returns:
            Dict[str, str]: {word: reading} の辞書
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT word, reading FROM dictionary WHERE guild_id = ?",
                (guild_id,),
            )
            return {row[0]: row[1] for row in cursor.fetchall()}

    def get_all_guilds(self) -> Dict[int, Dict[str, str]]:
        """全ギルドの辞書エントリを返す

        Returns:
            Dict[int, Dict[str, str]]: {guild_id: {word: reading}} の辞書
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT guild_id, word, reading FROM dictionary")
            result: Dict[int, Dict[str, str]] = {}
            for guild_id, word, reading in cursor.fetchall():
                if guild_id not in result:
                    result[guild_id] = {}
                result[guild_id][word] = reading
            return result

    def migrate_from_dict(self, guild_id: int, data: Dict[str, str]) -> None:
        """既存のdict形式の辞書データをSQLiteに移行する（既存エントリは上書きしない）

        Args:
            guild_id (int): DiscordギルドID
            data (Dict[str, str]): 移行する辞書データ {word: reading}
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.executemany(
                "INSERT OR IGNORE INTO dictionary (guild_id, word, reading) VALUES (?, ?, ?)",
                [(guild_id, word, reading) for word, reading in data.items()],
            )

    def clear_guild(self, guild_id: int) -> None:
        """指定ギルドの辞書エントリを全て削除する

        Args:
            guild_id (int): DiscordギルドID
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM dictionary WHERE guild_id = ?", (guild_id,))
