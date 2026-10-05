import asyncio
import aiohttp
import json
import struct
import gzip
import uuid
import logging
import os
import subprocess
from typing import Optional, List, Dict, Any, Tuple, AsyncGenerator
from GYun.LLM._config import get_config
from GYun.LLM.exceptions import APIRequestError

logger = logging.getLogger(__name__)

DEFAULT_SAMPLE_RATE = 16000

class ProtocolVersion:
    V1 = 0b0001

class MessageType:
    CLIENT_FULL_REQUEST = 0b0001
    CLIENT_AUDIO_ONLY_REQUEST = 0b0010
    SERVER_FULL_RESPONSE = 0b1001
    SERVER_ERROR_RESPONSE = 0b1111

class MessageTypeSpecificFlags:
    NO_SEQUENCE = 0b0000
    POS_SEQUENCE = 0b0001
    NEG_SEQUENCE = 0b0010
    NEG_WITH_SEQUENCE = 0b0011

class SerializationType:
    NO_SERIALIZATION = 0b0000
    JSON = 0b0001

class CompressionType:
    GZIP = 0b0001

class CommonUtils:
    @staticmethod
    def gzip_compress(data: bytes) -> bytes:
        return gzip.compress(data)

    @staticmethod
    def gzip_decompress(data: bytes) -> bytes:
        return gzip.decompress(data)

    @staticmethod
    def judge_wav(data: bytes) -> bool:
        if len(data) < 44: return False
        return data[:4] == b'RIFF' and data[8:12] == b'WAVE'

    @staticmethod
    def convert_wav_with_path(audio_path: str, sample_rate: int = DEFAULT_SAMPLE_RATE) -> bytes:
        try:
            cmd = ["ffmpeg", "-v", "quiet", "-y", "-i", audio_path, "-acodec", "pcm_s16le", "-ac", "1", "-ar", str(sample_rate), "-f", "wav", "-"]
            result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try: os.remove(audio_path)
            except OSError: pass
            return result.stdout
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Audio conversion failed: {e.stderr.decode()}")

    @staticmethod
    def read_wav_info(data: bytes) -> Tuple[int, int, int, int, bytes]:
        if len(data) < 44: raise ValueError("Invalid WAV file: too short")
        chunk_id = data[:4]
        if chunk_id != b'RIFF': raise ValueError("Invalid WAV file: not RIFF format")
        format_ = data[8:12]
        if format_ != b'WAVE': raise ValueError("Invalid WAV file: not WAVE format")
        audio_format = struct.unpack('<H', data[20:22])[0]
        num_channels = struct.unpack('<H', data[22:24])[0]
        sample_rate = struct.unpack('<I', data[24:28])[0]
        bits_per_sample = struct.unpack('<H', data[34:36])[0]
        pos = 36
        while pos < len(data) - 8:
            subchunk_id = data[pos:pos+4]
            subchunk_size = struct.unpack('<I', data[pos+4:pos+8])[0]
            if subchunk_id == b'data':
                wave_data = data[pos+8:pos+8+subchunk_size]
                return (num_channels, bits_per_sample // 8, sample_rate, subchunk_size // (num_channels * (bits_per_sample // 8)), wave_data)
            pos += 8 + subchunk_size
        raise ValueError("Invalid WAV file: no data subchunk found")

class AsrRequestHeader:
    def __init__(self):
        self.message_type = MessageType.CLIENT_FULL_REQUEST
        self.message_type_specific_flags = MessageTypeSpecificFlags.POS_SEQUENCE
        self.serialization_type = SerializationType.JSON
        self.compression_type = CompressionType.GZIP
        self.reserved_data = bytes([0x00])

    def with_message_type(self, message_type: int) -> 'AsrRequestHeader':
        self.message_type = message_type; return self

    def with_message_type_specific_flags(self, flags: int) -> 'AsrRequestHeader':
        self.message_type_specific_flags = flags; return self

    def with_serialization_type(self, serialization_type: int) -> 'AsrRequestHeader':
        self.serialization_type = serialization_type; return self

    def with_compression_type(self, compression_type: int) -> 'AsrRequestHeader':
        self.compression_type = compression_type; return self

    def with_reserved_data(self, reserved_data: bytes) -> 'AsrRequestHeader':
        self.reserved_data = reserved_data; return self

    def to_bytes(self) -> bytes:
        header = bytearray()
        header.append((ProtocolVersion.V1 << 4) | 1)
        header.append((self.message_type << 4) | self.message_type_specific_flags)
        header.append((self.serialization_type << 4) | self.compression_type)
        header.extend(self.reserved_data)
        return bytes(header)

    @staticmethod
    def default_header() -> 'AsrRequestHeader':
        return AsrRequestHeader()

class RequestBuilder:
    @staticmethod
    def new_auth_headers(app_key: str, access_key: str) -> Dict[str, str]:
        return {
            "X-Api-Resource-Id": "volc.bigasr.sauc.duration",
            "X-Api-Request-Id": str(uuid.uuid4()),
            "X-Api-Access-Key": access_key,
            "X-Api-App-Key": app_key
        }

    @staticmethod
    def new_full_client_request(seq: int) -> bytes:
        header = AsrRequestHeader.default_header().with_message_type_specific_flags(MessageTypeSpecificFlags.POS_SEQUENCE)
        payload = {
            "user": {"uid": "gyun_llm_user"},
            "audio": {"format": "wav", "codec": "raw", "rate": 16000, "bits": 16, "channel": 1},
            "request": {"model_name": "bigmodel", "enable_itn": True, "enable_punc": True, "enable_ddc": True, "show_utterances": True, "enable_nonstream": False}
        }
        payload_bytes = json.dumps(payload).encode('utf-8')
        compressed_payload = CommonUtils.gzip_compress(payload_bytes)
        request = bytearray()
        request.extend(header.to_bytes())
        request.extend(struct.pack('>i', seq))
        request.extend(struct.pack('>I', len(compressed_payload)))
        request.extend(compressed_payload)
        return bytes(request)

    @staticmethod
    def new_audio_only_request(seq: int, segment: bytes, is_last: bool = False) -> bytes:
        header = AsrRequestHeader.default_header()
        if is_last:
            header.with_message_type_specific_flags(MessageTypeSpecificFlags.NEG_WITH_SEQUENCE)
            seq = -seq
        else:
            header.with_message_type_specific_flags(MessageTypeSpecificFlags.POS_SEQUENCE)
        header.with_message_type(MessageType.CLIENT_AUDIO_ONLY_REQUEST)
        request = bytearray()
        request.extend(header.to_bytes())
        request.extend(struct.pack('>i', seq))
        compressed_segment = CommonUtils.gzip_compress(segment)
        request.extend(struct.pack('>I', len(compressed_segment)))
        request.extend(compressed_segment)
        return bytes(request)

class AsrResponse:
    def __init__(self):
        self.code = 0; self.event = 0; self.is_last_package = False
        self.payload_sequence = 0; self.payload_size = 0; self.payload_msg = None

class ResponseParser:
    @staticmethod
    def parse_response(msg: bytes) -> AsrResponse:
        response = AsrResponse()
        header_size = msg[0] & 0x0f
        message_type = msg[1] >> 4
        message_type_specific_flags = msg[1] & 0x0f
        serialization_method = msg[2] >> 4
        message_compression = msg[2] & 0x0f
        payload = msg[header_size*4:]

        if message_type_specific_flags & 0x01:
            response.payload_sequence = struct.unpack('>i', payload[:4])[0]
            payload = payload[4:]
        if message_type_specific_flags & 0x02:
            response.is_last_package = True
        if message_type_specific_flags & 0x04:
            response.event = struct.unpack('>i', payload[:4])[0]
            payload = payload[4:]

        if message_type == MessageType.SERVER_FULL_RESPONSE:
            response.payload_size = struct.unpack('>I', payload[:4])[0]
            payload = payload[4:]
        elif message_type == MessageType.SERVER_ERROR_RESPONSE:
            response.code = struct.unpack('>i', payload[:4])[0]
            response.payload_size = struct.unpack('>I', payload[4:8])[0]
            payload = payload[8:]

        if not payload: return response
        if message_compression == CompressionType.GZIP:
            try: payload = CommonUtils.gzip_decompress(payload)
            except Exception: return response
        try:
            if serialization_method == SerializationType.JSON:
                response.payload_msg = json.loads(payload.decode('utf-8'))
        except Exception: pass
        return response

class VolcStreamingAsrClient:
    def __init__(self, url: str = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_nostream", segment_duration: int = 200):
        config = get_config()
        self.app_key = (config.VOLC_APP_ID or "").strip()
        self.access_key = (config.VOLC_TOKEN or "").strip()
        if not all([self.app_key, self.access_key]):
            raise APIRequestError("火山语音配置缺失，请检查 VOLC_APP_ID 和 VOLC_TOKEN")
        
        self.seq = 1
        self.url = url
        self.segment_duration = segment_duration
        self.conn = None
        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc, tb):
        if self.conn and not self.conn.closed: await self.conn.close()
        if self.session and not self.session.closed: await self.session.close()
        
    async def read_audio_data(self, file_path: str) -> bytes:
        try:
            with open(file_path, 'rb') as f: content = f.read()
            if not CommonUtils.judge_wav(content):
                content = CommonUtils.convert_wav_with_path(file_path, DEFAULT_SAMPLE_RATE)
            return content
        except Exception as e:
            raise APIRequestError(f"读取音频失败: {e}")
            
    def get_segment_size(self, content: bytes) -> int:
        try:
            channel_num, samp_width, frame_rate, _, _ = CommonUtils.read_wav_info(content)[:5]
            size_per_sec = channel_num * samp_width * frame_rate
            return size_per_sec * self.segment_duration // 1000
        except Exception as e:
            raise APIRequestError(f"计算分段大小失败: {e}")
            
    async def create_connection(self) -> None:
        headers = RequestBuilder.new_auth_headers(self.app_key, self.access_key)
        try:
            self.conn = await self.session.ws_connect(self.url, headers=headers)
        except Exception as e:
            raise APIRequestError(f"WebSocket 连接失败: {e}")
            
    async def send_full_client_request(self) -> None:
        request = RequestBuilder.new_full_client_request(self.seq)
        self.seq += 1
        try:
            await self.conn.send_bytes(request)
            msg = await self.conn.receive()
            if msg.type != aiohttp.WSMsgType.BINARY:
                raise APIRequestError("非预期的握手响应类型")
        except Exception as e:
            raise APIRequestError(f"发送握手请求失败: {e}")
            
    async def send_messages(self, segment_size: int, content: bytes) -> AsyncGenerator[None, None]:
        audio_segments = self.split_audio(content, segment_size)
        total_segments = len(audio_segments)
        for i, segment in enumerate(audio_segments):
            is_last = (i == total_segments - 1)
            request = RequestBuilder.new_audio_only_request(self.seq, segment, is_last=is_last)
            await self.conn.send_bytes(request)
            if not is_last: self.seq += 1
            await asyncio.sleep(self.segment_duration / 1000)
            yield
            
    async def recv_messages(self) -> AsyncGenerator[AsrResponse, None]:
        try:
            async for msg in self.conn:
                if msg.type == aiohttp.WSMsgType.BINARY:
                    response = ResponseParser.parse_response(msg.data)
                    yield response
                    if response.is_last_package or response.code != 0: break
                elif msg.type in [aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSED]: break
        except Exception as e:
            raise APIRequestError(f"接收消息失败: {e}")
            
    async def start_audio_stream(self, segment_size: int, content: bytes) -> AsyncGenerator[AsrResponse, None]:
        async def sender():
            async for _ in self.send_messages(segment_size, content): pass
        sender_task = asyncio.create_task(sender())
        try:
            async for response in self.recv_messages(): yield response
        finally:
            sender_task.cancel()
            try: await sender_task
            except asyncio.CancelledError: pass
                
    @staticmethod
    def split_audio(data: bytes, segment_size: int) -> List[bytes]:
        if segment_size <= 0: return []
        segments = []
        for i in range(0, len(data), segment_size):
            end = i + segment_size
            if end > len(data): end = len(data)
            segments.append(data[i:end])
        return segments
        
    async def execute(self, file_path: str) -> AsyncGenerator[AsrResponse, None]:
        self.seq = 1
        content = await self.read_audio_data(file_path)
        segment_size = self.get_segment_size(content)
        await self.create_connection()
        await self.send_full_client_request()
        async for response in self.start_audio_stream(segment_size, content):
            yield response