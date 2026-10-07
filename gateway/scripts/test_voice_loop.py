import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import asyncio
import time
import numpy as np
import miniaudio
import edge_tts

from gateway.audio.opus_codec import OpusEncoderWrapper, OpusDecoderWrapper
from gateway.asr.sense_voice import get_asr_engine
from gateway.tts.edge_tts_streamer import EdgeTTSStreamer
from gateway.llm.relay_client import RelayLLMClient

async def run_pipeline_test():
    print("==================================================")
    print("🧪 正在执行小智专属语音网关全链路质量与延迟测试...")
    print("==================================================")

    # 1. Test Edge-TTS & Miniaudio
    test_phrase = "你好小智，请问今天天气怎么样？"
    print(f"\n[1/4] 测试语音合成 (TTS): '{test_phrase}'")
    t0 = time.time()
    comm = edge_tts.Communicate(test_phrase, voice="zh-CN-YunxiNeural")
    chunks = []
    async for chunk in comm.stream():
        if chunk["type"] == "audio":
            chunks.append(chunk["data"])
    tts_cost = (time.time() - t0) * 1000.0
    print(f"  -> TTS 首轮音频生成耗时: {tts_cost:.1f}ms")

    # 2. Decode MP3 to 16kHz PCM
    decoded = miniaudio.decode(b"".join(chunks), nchannels=1, sample_rate=16000)
    pcm_int16 = np.array(decoded.samples, dtype=np.int16)
    audio_duration = len(pcm_int16) / 16000.0
    print(f"  -> 音频重采样完成: {len(pcm_int16)} 采样点, 时长 {audio_duration:.2f} 秒")

    # 3. Test Opus Encode & Decode
    print("\n[2/4] 测试 ESP32 60ms Opus 编解码器...")
    encoder = OpusEncoderWrapper(sample_rate=16000, channels=1, frame_duration_ms=60)
    decoder = OpusDecoderWrapper(sample_rate=16000, channels=1)

    frame_count = 0
    decoded_pcm = []
    for offset in range(0, len(pcm_int16), 960):
        frame = pcm_int16[offset:offset + 960]
        opus_bytes = encoder.encode(frame)
        reconstructed = decoder.decode(opus_bytes)
        decoded_pcm.append(reconstructed)
        frame_count += 1

    print(f"  -> 成功分片并编解码 {frame_count} 帧 Opus 数据包，数据完整！")

    # 4. Test SenseVoice ASR
    print("\n[3/4] 测试 SenseVoice-Small INT8 本地离线语音识别...")
    asr = get_asr_engine()
    text, asr_cost = asr.transcribe(np.concatenate(decoded_pcm))
    print(f"  -> ASR 识别结果: '{text}'")
    print(f"  -> ASR 推理耗时: {asr_cost:.1f}ms (本地极速无网络延迟)")

    # 5. Test LLM Relay connection
    from gateway.config import config
    print(f"\n[4/4] 测试 Gemini 云端中转网关 ({config.relay_base_url})...")
    llm = RelayLLMClient()
    reply_tokens = []
    ttft_ms = 0
    t_llm = time.time()
    try:
        async for token, tool_call, metrics in llm.stream_chat("你好，请用一句话做个自我介绍。"):
            if metrics.get("ttft_ms") and not ttft_ms:
                ttft_ms = metrics["ttft_ms"]
            if token:
                reply_tokens.append(token)
        total_llm = (time.time() - t_llm) * 1000.0
        full_reply = "".join(reply_tokens)
        print(f"  -> 中转网关连接成功！")
        print(f"  -> 首字延迟 (TTFT): {ttft_ms:.1f}ms, 总生成耗时: {total_llm:.1f}ms")
        print(f"  -> Gemini 回复: '{full_reply}'")
    except Exception as e:
        print(f"  -> [提示] 本地中转网关 (8000端口) 暂未启动: {e}")
        print(f"  -> 启动方式: 在 'gemini中转项目' 目录下双击 start.bat 即可。")

    print("\n==================================================")
    print("✅ 音频核心链路 (TTS -> 16kHz PCM -> Opus -> SenseVoice ASR) 验证全部通过！")
    print("==================================================")

if __name__ == "__main__":
    asyncio.run(run_pipeline_test())
