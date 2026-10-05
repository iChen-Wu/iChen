import httpx
import base64
import uuid
import os
from typing import Optional
from GYun.LLM._config import get_config
from GYun.LLM.exceptions import APIRequestError, AuthenticationError

class VolcTTSAdapter:
    """火山引擎语音合成 (TTS) 适配器，支持声音复刻"""
    def __init__(self):
        config = get_config()
        self.tts_url = "https://openspeech.bytedance.com/api/v1/tts"
        self.cluster = config.VOLC_CLUSTER
        self.api_key = (config.VOLC_VOICE_API_KEY or "").strip()
        self.appid = (config.VOLC_APP_ID or "").strip()
        self.token = (config.VOLC_TOKEN or "").strip()
        
        if not self.api_key:
            raise AuthenticationError("缺少 TTS 认证信息：请配置 VOLC_VOICE_API_KEY")
            
        self.default_voice = "BV001_V2_streaming"
        self._client = httpx.Client(timeout=30.0)

    def _get_voice_id(self, voice_name: Optional[str]) -> str:
        if voice_name is None:
            return self.default_voice
            
        # 如果直接传入以 BV 开头的系统音色 ID，直接返回
        if voice_name.startswith("BV"):
            return voice_name
            
        # 否则视为自定义音色别名，从环境变量读取 (如 voice="rinai" -> 读取 VOICE_RINAI_ID)
        env_var = f"VOICE_{voice_name.upper()}_ID"
        custom_id = os.getenv(env_var)
        if custom_id:
            return custom_id.strip()
            
        # 如果环境变量没找到，直接把传入的当 ID 用
        return voice_name

    def synthesize(self, text: str, voice: Optional[str] = None, **kwargs) -> bytes:
        if not text or not text.strip():
            raise ValueError("合成文本不能为空")
            
        voice_id = self._get_voice_id(voice)
        reqid = str(uuid.uuid4())
        
        headers = {
            "X-Api-Key": self.api_key,
            "Content-Type": "application/json"
        }
        
        payload = {
            "app": {"appid": self.appid, "cluster": self.cluster, "token": self.token},
            "user": {"uid": kwargs.get("uid", "gyun_llm_user")},
            "audio": {
                "voice_type": voice_id,
                "encoding": kwargs.get("format", "mp3"),
                "speed_ratio": kwargs.get("speed", 1.0),
                "volume_ratio": kwargs.get("volume", 1.0),
                "pitch_ratio": kwargs.get("pitch", 1.0),
            },
            "request": {"reqid": reqid, "text": text, "operation": "query", "with_subtitle": False}
        }
        
        resp = self._client.post(self.tts_url, json=payload, headers=headers)
        
        if resp.status_code != 200:
            if resp.status_code == 401:
                raise AuthenticationError("TTS 鉴权失败，请检查 VOLC_VOICE_API_KEY")
            raise APIRequestError(f"TTS 错误 {resp.status_code}: {resp.text}")
            
        result = resp.json()
        audio_b64 = result.get("data") or result.get("audio")
        if audio_b64:
            return base64.b64decode(audio_b64)
            
        code = result.get("code")
        if code is not None and str(code) != "0" and str(code) != "1000":
            raise APIRequestError(f"TTS 失败: {result.get('message', 'Unknown error')} (code={code})")
        raise APIRequestError(f"TTS 响应异常: {result}")

    def close(self):
        self._client.close()