"""
DictionaryDB のユニットテスト
"""
import pytest
from pathlib import Path

from src.dictionary_db import DictionaryDB


@pytest.fixture
def db(tmp_path: Path) -> DictionaryDB:
    """テスト用の一時SQLiteデータベースを作成するフィクスチャ"""
    return DictionaryDB(tmp_path / "test_dictionary.db")


class TestDictionaryDBInitialize:
    """DictionaryDB の初期化に関するテスト"""

    def test_creates_database_file(self, tmp_path: Path):
        """初期化時にデータベースファイルが作成されること"""
        db_path = tmp_path / "subdir" / "test.db"
        DictionaryDB(db_path)
        assert db_path.exists()

    def test_creates_parent_directories(self, tmp_path: Path):
        """親ディレクトリが存在しない場合でも作成されること"""
        db_path = tmp_path / "a" / "b" / "c" / "test.db"
        DictionaryDB(db_path)
        assert db_path.exists()

    def test_initialize_twice_does_not_raise(self, tmp_path: Path):
        """同じパスで2回初期化しても例外が発生しないこと"""
        db_path = tmp_path / "test.db"
        DictionaryDB(db_path)
        DictionaryDB(db_path)  # CREATE TABLE IF NOT EXISTS で冪等


class TestDictionaryDBAdd:
    """DictionaryDB.add に関するテスト"""

    def test_add_stores_entry(self, db: DictionaryDB):
        """add でエントリが保存されること"""
        db.add(1, "テスト", "てすと")
        result = db.get_all(1)
        assert result["テスト"] == "てすと"

    def test_add_multiple_entries(self, db: DictionaryDB):
        """複数のエントリを追加できること"""
        db.add(1, "AI", "エーアイ")
        db.add(1, "Discord", "でぃすこーど")
        result = db.get_all(1)
        assert result == {"AI": "エーアイ", "Discord": "でぃすこーど"}

    def test_add_overwrites_existing_entry(self, db: DictionaryDB):
        """同じ word を add すると上書きされること"""
        db.add(1, "hello", "こんにちは")
        db.add(1, "hello", "ハロー")
        result = db.get_all(1)
        assert result["hello"] == "ハロー"

    def test_add_is_isolated_per_guild(self, db: DictionaryDB):
        """異なるギルドのエントリは独立していること"""
        db.add(100, "AI", "エーアイ")
        db.add(200, "AI", "藍")
        assert db.get_all(100)["AI"] == "エーアイ"
        assert db.get_all(200)["AI"] == "藍"


class TestDictionaryDBRemove:
    """DictionaryDB.remove に関するテスト"""

    def test_remove_existing_entry_returns_true(self, db: DictionaryDB):
        """存在するエントリを削除すると True が返ること"""
        db.add(1, "word", "読み")
        assert db.remove(1, "word") is True

    def test_remove_existing_entry_deletes_it(self, db: DictionaryDB):
        """削除後にエントリが存在しないこと"""
        db.add(1, "word", "読み")
        db.remove(1, "word")
        assert "word" not in db.get_all(1)

    def test_remove_nonexistent_entry_returns_false(self, db: DictionaryDB):
        """存在しないエントリを削除すると False が返ること"""
        assert db.remove(1, "存在しないワード") is False

    def test_remove_only_affects_own_guild(self, db: DictionaryDB):
        """削除は指定ギルドのみに影響すること"""
        db.add(100, "word", "読みA")
        db.add(200, "word", "読みB")
        db.remove(100, "word")
        assert "word" not in db.get_all(100)
        assert db.get_all(200)["word"] == "読みB"


class TestDictionaryDBGetAll:
    """DictionaryDB.get_all に関するテスト"""

    def test_get_all_returns_empty_dict_for_unknown_guild(self, db: DictionaryDB):
        """未知のギルドIDに対して空の辞書が返ること"""
        assert db.get_all(99999) == {}

    def test_get_all_returns_only_own_guild_entries(self, db: DictionaryDB):
        """自ギルドのエントリのみ返ること"""
        db.add(1, "サーバー1専用", "A")
        db.add(2, "サーバー2専用", "B")
        result = db.get_all(1)
        assert "サーバー1専用" in result
        assert "サーバー2専用" not in result


class TestDictionaryDBGetAllGuilds:
    """DictionaryDB.get_all_guilds に関するテスト"""

    def test_get_all_guilds_returns_empty_when_no_entries(self, db: DictionaryDB):
        """エントリがない場合は空の辞書が返ること"""
        assert db.get_all_guilds() == {}

    def test_get_all_guilds_returns_all_entries(self, db: DictionaryDB):
        """全ギルドのエントリが返ること"""
        db.add(1, "hello", "こんにちは")
        db.add(2, "bye", "さようなら")
        result = db.get_all_guilds()
        assert result == {1: {"hello": "こんにちは"}, 2: {"bye": "さようなら"}}


class TestDictionaryDBMigrateFromDict:
    """DictionaryDB.migrate_from_dict に関するテスト"""

    def test_migrate_inserts_all_entries(self, db: DictionaryDB):
        """migrate_from_dict で全エントリが挿入されること"""
        data = {"hello": "こんにちは", "bye": "さようなら"}
        db.migrate_from_dict(1, data)
        assert db.get_all(1) == data

    def test_migrate_does_not_overwrite_existing_entries(self, db: DictionaryDB):
        """既存エントリは上書きされないこと"""
        db.add(1, "hello", "ハロー")
        db.migrate_from_dict(1, {"hello": "こんにちは", "bye": "さようなら"})
        result = db.get_all(1)
        assert result["hello"] == "ハロー"   # 上書きされない
        assert result["bye"] == "さようなら"   # 新規は追加される

    def test_migrate_empty_dict_does_not_raise(self, db: DictionaryDB):
        """空の辞書を移行しても例外が発生しないこと"""
        db.migrate_from_dict(1, {})
        assert db.get_all(1) == {}


class TestDictionaryDBClearGuild:
    """DictionaryDB.clear_guild に関するテスト"""

    def test_clear_guild_removes_all_entries(self, db: DictionaryDB):
        """clear_guild で指定ギルドのエントリが全て削除されること"""
        db.add(1, "word1", "読み1")
        db.add(1, "word2", "読み2")
        db.clear_guild(1)
        assert db.get_all(1) == {}

    def test_clear_guild_only_affects_own_guild(self, db: DictionaryDB):
        """clear_guild は指定ギルドのみに影響すること"""
        db.add(1, "word", "読みA")
        db.add(2, "word", "読みB")
        db.clear_guild(1)
        assert db.get_all(1) == {}
        assert db.get_all(2) == {"word": "読みB"}

    def test_clear_nonexistent_guild_does_not_raise(self, db: DictionaryDB):
        """存在しないギルドを clear しても例外が発生しないこと"""
        db.clear_guild(99999)  # 例外なく終了すること


class TestDictionaryDBPersistence:
    """DictionaryDB の永続性に関するテスト"""

    def test_data_persists_across_instances(self, tmp_path: Path):
        """データベースを再度開いてもデータが保持されること"""
        db_path = tmp_path / "test.db"
        db1 = DictionaryDB(db_path)
        db1.add(1, "hello", "こんにちは")
        db1.add(2, "bye", "さようなら")

        db2 = DictionaryDB(db_path)
        assert db2.get_all(1) == {"hello": "こんにちは"}
        assert db2.get_all(2) == {"bye": "さようなら"}
