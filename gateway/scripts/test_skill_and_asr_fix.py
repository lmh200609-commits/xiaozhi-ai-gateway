#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动化验证脚本：
1. 验证 ASR 防幻觉与静音误触 "我" 的三重拦截机制 (VAD + SenseVoice 门限 + Main ASR Guard)
2. 验证 Agent Skill 文件系统 (SKILL.md 导入解析、导出、仓库管理、角色挂载与 SOP 运作)
3. 验证端到端 HTTP API 闭环
"""
import sys
import os
import io
import time
import numpy as np

# Ensure project root in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from starlette.testclient import TestClient
from gateway.main import app
from gateway.audio.vad import EnergyVAD
from gateway.asr.sense_voice import get_asr_engine
from gateway.roles.skill_manager import skill_manager
from gateway.roles.role_manager import role_manager

def test_asr_phantom_protection():
    print("\n" + "=" * 60)
    print("🚀 [Test 1] 验证 ASR 杂音/静音防误触 '我' 三重防护体系")
    print("=" * 60)

    # 1.1 VAD 测试：模拟环境底噪 (RMS ~100) 与短杂音 (<240ms)
    vad = EnergyVAD(min_energy_threshold=220.0, min_speech_frames=4)
    noise_frame = np.random.randint(-150, 150, size=960, dtype=np.int16)
    is_sp, sp_ended = vad.process_frame(noise_frame)
    assert not vad.speech_started, "VAD 不应对底噪触发 speech_started"
    assert not sp_ended, "VAD 不应对底噪声明 speech_ended"
    print("  ✅ [PASS] 1.1 VAD 成功抵御环境底噪 (RMS < 220)，未触发说话标志")

    # 模拟瞬态爆音 (2帧超标后恢复静音)
    click_frame = np.random.randint(-1000, 1000, size=960, dtype=np.int16)
    silence_frame = np.zeros(960, dtype=np.int16)
    vad.process_frame(click_frame)
    vad.process_frame(click_frame)
    for _ in range(15):
        _, ended = vad.process_frame(silence_frame)
    assert not ended, "瞬态短杂音 (<4帧) 应被 VAD 判定为无效干扰并丢弃"
    print("  ✅ [PASS] 1.2 VAD 成功过滤瞬态点击/呼吸杂音 (<240ms)，未产生误结束信号")

    # 1.2 SenseVoice 门限与幻觉过滤测试
    asr = get_asr_engine()
    # 模拟 500ms 低能量微弱底噪音频
    sub_threshold_pcm = np.random.randint(-80, 80, size=8000, dtype=np.int16)
    text, cost = asr.transcribe(sub_threshold_pcm)
    assert text == "", f"底噪音频应被 ASR 能量门限丢弃，实际得到: '{text}'"
    print("  ✅ [PASS] 1.3 SenseVoice 成功拦截微弱底噪音频 (RMS < 150)，返回空文本")

def test_agent_skill_file_system():
    print("\n" + "=" * 60)
    print("🚀 [Test 2] 验证 Agent Skill 文件系统 (解析、导出、挂载、仓库)")
    print("=" * 60)

    client = TestClient(app)

    # 2.1 获取技能库列表
    res = client.get("/api/skills")
    assert res.status_code == 200, "GET /api/skills 应返回 200"
    skills = res.json().get("skills", [])
    assert len(skills) >= 4, f"技能库中应至少包含4个预设技能，实际为 {len(skills)}"
    print(f"  ✅ [PASS] 2.1 成功获取技能仓库列表: 共 {len(skills)} 个标准技能")

    # 2.2 上传从 GitHub 下载风格的真实 Agent SKILL.md 文件
    sample_github_skill_md = """---
name: 考研复试英语口语指导SOP
description: 专为考研复试打造的三阶段全英文口语模拟面试工作流
version: 1.2.0
author: github-community
---

# 考研复试英语口语指导SOP

> 专为考研复试打造的三阶段全英文口语模拟面试工作流

## 流程阶段 (Stages)

### 阶段 1: 自我介绍与破冰提问 (Self Introduction)
- **核心目标**: 引导考生完成 1-2 分钟英文自我介绍，检测流利度与发音
- **进入下一阶段条件**: 考生完成自我介绍并表达清晰后过渡
- **阶段执行策略**: 扮演主考官热情问候：Welcome! Please give a brief self-introduction about your background.

### 阶段 2: 专业学术热点抽问 (Academic Topic)
- **核心目标**: 针对考生专业进行深入学术提问，考察学术英语表达
- **进入下一阶段条件**: 考生给出专业见解后过渡
- **阶段执行策略**: 提问专业前沿：What do you think is the biggest challenge in your major field today?

### 阶段 3: 面试点评与考场建议 (Feedback & Tips)
- **核心目标**: 给出精准的发音语法建议与心理减压指导
- **进入下一阶段条件**: 完成本轮模拟面试
- **阶段执行策略**: 肯定考生的闪光点，针对语法小疏漏给出 2 点关键提升建议，并送上祝福。
"""

    upload_file = io.BytesIO(sample_github_skill_md.encode("utf-8"))
    res_upload = client.post(
        "/api/skills/upload",
        files={"file": ("kaoyan_english_interview.skill.md", upload_file, "text/markdown")}
    )
    assert res_upload.status_code == 200, f"上传 Skill 失败: {res_upload.text}"
    skill_data = res_upload.json()["skill"]
    assert skill_data["name"] == "考研复试英语口语指导SOP", f"名称解析错误: {skill_data['name']}"
    assert len(skill_data["stages"]) == 3, f"阶段数解析错误: {len(skill_data['stages'])}"
    assert skill_data["stages"][0]["name"] == "自我介绍与破冰提问 (Self Introduction)"
    print("  ✅ [PASS] 2.2 成功上传并解析 GitHub 标准 SKILL.md 文件 (3阶段)")

    # 2.3 验证将该 Skill 绑定到自定义测试角色
    test_role = {
        "id": "test_kaoyan_coach",
        "name": "考研复试主考官",
        "voice": "en-US-JennyNeural",
        "temperature": 0.4,
        "rag_enabled": False,
        "system_prompt": "You are a professional IELTS and postgraduate interview coach.",
        "skill": skill_data
    }
    res_role = client.post("/api/roles", json=test_role)
    assert res_role.status_code == 200
    print("  ✅ [PASS] 2.3 成功将解析出的 Skill 挂载到角色 '考研复试主考官'")

    # 2.4 验证角色 Skill 导出为 .skill.md
    res_export = client.get("/api/roles/test_kaoyan_coach/skill/export")
    assert res_export.status_code == 200
    assert "考研复试英语口语指导SOP" in res_export.text
    assert "阶段 1: 自我介绍与破冰提问" in res_export.text
    print("  ✅ [PASS] 2.4 成功从角色一键导出标准 .skill.md 文本")

    # 2.5 验证从角色卸载 Skill
    res_unbind = client.delete("/api/roles/test_kaoyan_coach/skill")
    assert res_unbind.status_code == 200
    assert res_unbind.json()["role"]["skill"] is None
    print("  ✅ [PASS] 2.5 成功从角色安全卸载 Skill")

    # 清理测试数据
    client.delete("/api/roles/test_kaoyan_coach")
    skill_manager.delete_skill("kaoyan_english_interview.skill.md")
    print("  ✅ [PASS] 2.6 清理测试角色与临时 Skill 文件")

if __name__ == "__main__":
    test_asr_phantom_protection()
    test_agent_skill_file_system()
    print("\n" + "=" * 60)
    print("🎉 所有 ASR 防误触与 Agent Skill 升级验证 100% 通过！")
    print("=" * 60)
