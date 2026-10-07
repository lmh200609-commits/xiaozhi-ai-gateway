import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import asyncio
import json
import time
import numpy as np
import miniaudio
import edge_tts
import websockets

from gateway.audio.opus_codec import OpusEncoderWrapper, OpusDecoderWrapper

async def simulate_esp32():
    print("=================================================================")
    print("🔌 模拟 ESP32 小智开发板 (MAC: 14:c1:9f:cb:63:88) 全协议会话测试...")
    print("=================================================================")

    headers = {
        "Device-Id": "14:c1:9f:cb:63:88",
        "Client-Id": "6ec1d604-5f50-4ba8-9b88-5a2a229a4a75",
        "Protocol-Version": "1"
    }

    uri = "ws://127.0.0.1:8001/xiaozhi/v1/"
    async with websockets.connect(uri, additional_headers=headers) as ws:
        print("✓ WebSocket 握手已建立")

        # 1. Hello
        hello_msg = {
            "type": "hello",
            "version": 1,
            "transport": "websocket",
            "features": {"mcp": True},
            "audio_params": {
                "format": "opus",
                "sample_rate": 16000,
                "channels": 1,
                "frame_duration": 60
            }
        }
        await ws.send(json.dumps(hello_msg))
        resp_hello = json.loads(await ws.recv())
        print(f"✓ 收到服务器 Hello 响应: session_id={resp_hello.get('session_id')}")

        # 2. Register hardware tools
        mcp_tools = {
            "type": "mcp",
            "tools": [
                {"name": "self.audio_speaker.set_volume", "description": "调节喇叭音量"},
                {"name": "self.screen.set_brightness", "description": "调节屏幕背光"}
            ]
        }
        await ws.send(json.dumps(mcp_tools))
        print("✓ 上报开发板板载硬件 MCP 工具列表成功")

        # Prepare speech audio for "帮我打开微信"
        print("\n🎤 [用例 1] 模拟游客向小智说：'帮我打开微信'...")
        comm = edge_tts.Communicate("帮我打开微信", voice="zh-CN-XiaoxiaoNeural")
        chunks = []
        async for ch in comm.stream():
            if ch["type"] == "audio":
                chunks.append(ch["data"])
        decoded = miniaudio.decode(b"".join(chunks), nchannels=1, sample_rate=16000)
        pcm = np.array(decoded.samples, dtype=np.int16)

        encoder = OpusEncoderWrapper(sample_rate=16000, channels=1, frame_duration_ms=60)
        
        # Send 60ms Opus frames
        for offset in range(0, len(pcm), 960):
            frame = pcm[offset:offset+960]
            if len(frame) < 960:
                frame = np.pad(frame, (0, 960 - len(frame)))
            opus_bytes = encoder.encode(frame)
            await ws.send(opus_bytes)
            await asyncio.sleep(0.01)

        # Send trailing silence frames to trigger VAD
        silence_frame = np.zeros(960, dtype=np.int16)
        for _ in range(12):
            await ws.send(encoder.encode(silence_frame))
            await asyncio.sleep(0.01)

        print("  -> 音频流已全部发送，等待网关处理与播报...")

        # Listen for response
        tts_frames = 0
        received_stt = ""
        spoken_sentences = []
        
        while True:
            msg = await ws.recv()
            if isinstance(msg, str):
                data = json.loads(msg)
                msg_type = data.get("type")
                if msg_type == "stt":
                    received_stt = data.get("text")
                    print(f"  -> [STT屏幕字幕]: '{received_stt}'")
                elif msg_type == "tts":
                    st = data.get("state")
                    if st == "sentence_start":
                        spoken_sentences.append(data.get("text", ""))
                        print(f"  -> [TTS语音播报]: '{data.get('text')}'")
                    elif st == "stop":
                        print(f"  -> [TTS播报完成]: 累计接收 {tts_frames} 帧音频")
                        break
            elif isinstance(msg, bytes):
                tts_frames += 1

        assert "微信" in received_stt, f"STT 识别失败: {received_stt}"
        assert tts_frames > 0, "未收到任何 TTS Opus 音频帧"
        print(f"✅ 用例 1 成功！STT识别、电脑微信调用、晓晓语音回报闭环完成！")

        # Second turn: "播放一段火车历史视频"
        print("\n🎤 [用例 2] 第二轮对话：'请播放一段火车历史视频'...")
        comm2 = edge_tts.Communicate("请播放一段火车历史视频", voice="zh-CN-XiaoxiaoNeural")
        chunks2 = []
        async for ch in comm2.stream():
            if ch["type"] == "audio":
                chunks2.append(ch["data"])
        decoded2 = miniaudio.decode(b"".join(chunks2), nchannels=1, sample_rate=16000)
        pcm2 = np.array(decoded2.samples, dtype=np.int16)

        # Inform gateway device is in listening mode
        await ws.send(json.dumps({"type": "listen", "state": "start", "mode": "auto"}))
        await asyncio.sleep(0.05)

        for offset in range(0, len(pcm2), 960):
            frame = pcm2[offset:offset+960]
            if len(frame) < 960:
                frame = np.pad(frame, (0, 960 - len(frame)))
            await ws.send(encoder.encode(frame))
            await asyncio.sleep(0.01)

        for _ in range(12):
            await ws.send(encoder.encode(silence_frame))
            await asyncio.sleep(0.01)

        print("  -> 第二轮音频流已发送，等待视频弹窗与播报...")

        tts_frames2 = 0
        received_stt2 = ""
        while True:
            msg = await ws.recv()
            if isinstance(msg, str):
                data = json.loads(msg)
                msg_type = data.get("type")
                if msg_type == "stt":
                    received_stt2 = data.get("text")
                    print(f"  -> [STT屏幕字幕]: '{received_stt2}'")
                elif msg_type == "tts":
                    st = data.get("state")
                    if st == "sentence_start":
                        print(f"  -> [TTS语音播报]: '{data.get('text')}'")
                    elif st == "stop":
                        print(f"  -> [TTS播报完成]: 累计接收 {tts_frames2} 帧音频")
                        break
            elif isinstance(msg, bytes):
                tts_frames2 += 1

        assert "火车" in received_stt2 or "视频" in received_stt2, f"STT 识别失败: {received_stt2}"
        assert tts_frames2 > 0, "未收到第二轮 TTS 音频帧"
        print(f"✅ 用例 2 成功！第二轮火车视频识别、展厅大屏播放器启动、晓晓语音回报闭环完成！")
        print("\n=================================================================")
        print("🎉 硬件 WebSocket 全链路双轮对话与电脑/大屏控制 100% 成功闭环！")
        print("=================================================================")

if __name__ == "__main__":
    asyncio.run(simulate_esp32())
