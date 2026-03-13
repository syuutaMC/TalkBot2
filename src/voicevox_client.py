"""
VOICEVOX Engine連携モジュール
"""
import aiohttp
import asyncio
from typing import Optional


class VoicevoxClient:
    """VOICEVOX Engineとの通信を管理するクライアント"""
    
    def __init__(self, base_url: str = "http://127.0.0.1:50021"):
        self.base_url = base_url
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def initialize(self):
        """セッションの初期化"""
        if not self.session:
            self.session = aiohttp.ClientSession()
    
    async def close(self):
        """セッションのクローズ"""
        if self.session:
            await self.session.close()
    
    async def get_speakers(self) -> list:
        """
        利用可能な話者一覧を取得
        
        Returns:
            list: 話者情報のリスト
        """
        try:
            async with self.session.get(f"{self.base_url}/speakers") as response:
                if response.status == 200:
                    return await response.json()
                return []
        except Exception as e:
            print(f"話者一覧取得エラー: {e}")
            return []
    
    async def create_audio(self, text: str, speaker_id: int = 1, speed: float = 1.0) -> Optional[bytes]:
        """
        テキストから音声データを生成
        
        Args:
            text (str): 読み上げるテキスト
            speaker_id (int): 話者ID (デフォルト: 1)
            speed (float): 読み上げ速度 (デフォルト: 1.0)
        
        Returns:
            Optional[bytes]: 音声データ (WAV形式)、エラー時はNone
        """
        try:
            # クエリの生成
            params = {"text": text, "speaker": speaker_id}
            async with self.session.post(
                f"{self.base_url}/audio_query",
                params=params
            ) as response:
                if response.status != 200:
                    print(f"クエリ生成エラー: {response.status}")
                    return None
                query = await response.json()
            
            # 速度の調整
            query["speedScale"] = speed
            
            # 音声合成
            params = {"speaker": speaker_id}
            async with self.session.post(
                f"{self.base_url}/synthesis",
                params=params,
                json=query
            ) as response:
                if response.status == 200:
                    return await response.read()
                print(f"音声合成エラー: {response.status}")
                return None
                
        except Exception as e:
            print(f"音声生成エラー: {e}")
            return None
    
    async def is_available(self) -> bool:
        """
        VOICEVOX Engineが利用可能かチェック
        
        Returns:
            bool: 利用可能ならTrue
        """
        try:
            async with self.session.get(f"{self.base_url}/version") as response:
                return response.status == 200
        except Exception:
            return False
