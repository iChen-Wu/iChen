import httpx
import base64
import re
from typing import Optional
from GYun.LLM._config import get_config
from GYun.LLM.exceptions import APIRequestError, AuthenticationError
from GYun.LLM.base import AudioClassificationResponse, AudioLabel

class AudioAdapter:
    """语音识别与分类适配器 (目前支持硅基流动)"""
    def __init__(self, platform: str = "siliconflow"):
        config = get_config()
        if platform != "siliconflow":
            raise ValueError(f"不支持的语音识别平台: {platform} (当前仅支持 siliconflow)")
        self.transcription_url = "https://api.siliconflow.cn/v1/audio/transcriptions"
        self.api_key = (config.SILICONFLOW_API_KEY or "").strip()
        if not self.api_key:
            raise APIRequestError("硅基流动的 API Key 未配置")
        self._headers = {"Authorization": f"Bearer {self.api_key}"}
        self._client = httpx.Client(timeout=120.0)

    def transcribe(self, audio_path: str, model: str = "FunAudioLLM/SenseVoiceSmall", language: Optional[str] = None) -> str:
        try:
            with open(audio_path, "rb") as f:
                files = {"file": (audio_path, f, "audio/mpeg")}
                data = {"model": model}
                if language: data["language"] = language
                resp = self._client.post(self.transcription_url, headers=self._headers, files=files, data=data)
                
            if resp.status_code == 401: raise AuthenticationError("API Key 无效")
            elif resp.status_code != 200: raise APIRequestError(f"语音识别失败 {resp.status_code}: {resp.text}")
            return resp.json().get("text", "")
        except Exception as e:
            raise APIRequestError(f"音频处理失败: {e}")

    def classify_audio(self, audio_path: str, model: str = "FunAudioLLM/SenseVoiceSmall") -> AudioClassificationResponse:
        """音频分类 (SER/AED) - 复用 ASR 接口并解析 SenseVoice 标签"""
        try:
            # 1. 调用语音转文字
            text = self.transcribe(audio_path, model=model)
            
            # 2. 提取 <|...|> 格式的标签
            pattern = r"<\|(.*?)\|>"
            tags = re.findall(pattern, text)
            
            # 3. 过滤出已知的情感和事件标签
            known_emotions = ["HAPPY", "SAD", "ANGRY", "FEARFUL", "DISGUSTED", "NEUTRAL", "SURPRISED"]
            known_events = ["Speech", "BGM", "Applause", "Laughter", "Cry", "Sneeze", "Breath"]
            
            labels = []
            for tag in tags:
                # 标签可能是语言代码(zh, en)，直接跳过
                if len(tag) <= 3 and tag.lower() in ['zh', 'en', 'ja', 'ko', 'auto']:
                    continue
                # 如果是已知情感或事件，加入结果列表
                if tag.upper() in known_emotions or tag in known_events:
                    labels.append(AudioLabel(label=tag, score=1.0))  # 模型输出是确定的，分数设为 1.0
                    
            if not labels:
                labels.append(AudioLabel(label="UNKNOWN", score=1.0))
                
            return AudioClassificationResponse(labels=labels)
            
        except Exception as e:
            raise APIRequestError(f"音频分类处理失败: {e}")

    def close(self):
        self._client.close()