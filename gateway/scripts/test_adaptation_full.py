import asyncio
import sys
import os
import json
from pathlib import Path

# Ensure utf-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from gateway.config import config, GatewayConfig
from gateway.rag.document_parser import DocumentParser
from gateway.rag.knowledge_structurer import KnowledgeStructurer
from gateway.rag.knowledge_store import knowledge_store
from gateway.rag.zone_manager import zone_manager
from gateway.roles.role_manager import role_manager

async def run_full_adaptation_test():
    print("==================================================")
    print("🧪 正在运行小智通用化与个体化适配全流程验证套件...")
    print("==================================================")

    # 1. Verify URL normalization across various formats
    print("\n[测试 1] 验证 URL 自动化归一化逻辑 (config.get_chat_url):")
    test_urls = [
        ("https://api.deepseek.com", "https://api.deepseek.com/chat/completions"),
        ("https://api.deepseek.com/v1", "https://api.deepseek.com/v1/chat/completions"),
        ("https://api.deepseek.com/v1/", "https://api.deepseek.com/v1/chat/completions"),
        ("https://api.deepseek.com/v1/chat/completions", "https://api.deepseek.com/v1/chat/completions"),
        ("https://api.siliconflow.cn/v1", "https://api.siliconflow.cn/v1/chat/completions"),
    ]
    for input_url, expected in test_urls:
        cfg = GatewayConfig(relay_base_url=input_url)
        actual = cfg.get_chat_url()
        assert actual == expected, f"URL 归一化失败: 输入 {input_url} -> 实际 {actual} != 期望 {expected}"
        print(f"  ✓ {input_url} -> {actual}")
    print("  -> 测试 1 全部通过！")

    # 2. Verify Ultra-resilient JSON parser (_extract_json)
    print("\n[测试 2] 验证 JSON 深度容错与自愈修复能力 (_extract_json):")
    # Case A: DeepSeek-R1 <think> tags + markdown fences
    case_a = """<think>
思考中：用户上传了一篇关于WiFi和供电的排查文档。
我需要提炼出核心FAQ和事实切片。
</think>
```json
{
  "title": "小智硬件排查手册",
  "category": "硬件运维",
  "summary": "关于供电与WiFi的常见故障排查",
  "qa_pairs": [
    {"question": "小智扬声器破音怎么办？", "answer": "请使用5V/2A以上独立电源供电。", "keywords": ["扬声器", "破音", "供电"]}
  ],
  "fact_chunks": [
    {"title": "供电要求", "content": "ESP32-S3峰值电流可达1.5A以上。"}
  ]
}
```
"""
    parsed_a = KnowledgeStructurer._extract_json(case_a)
    assert parsed_a and parsed_a["title"] == "小智硬件排查手册", "Case A 解析失败"
    assert len(parsed_a["qa_pairs"]) == 1
    print("  ✓ Case A (DeepSeek-R1 <think> + Markdown 包裹) 完美解析")

    # Case B: Trailing comma error (common in LLM output)
    case_b = """{
  "title": "测试文档",
  "category": "通用",
  "summary": "摘要",
  "qa_pairs": [
    {"question": "怎么开机？", "answer": "长按电源键2秒。", "keywords": ["开机", "电源"],},
  ],
  "fact_chunks": [
    {"title": "开机方式", "content": "电源键位于右侧。",},
  ],
}"""
    parsed_b = KnowledgeStructurer._extract_json(case_b)
    assert parsed_b and parsed_b["title"] == "测试文档", "Case B 尾逗号解析失败"
    print("  ✓ Case B (JSON 结尾非法逗号自愈修复) 完美解析")

    # Case C: Truncated JSON (output cut off by token limit)
    case_c = """{
  "title": "截断测试",
  "category": "系统",
  "summary": "文档被截断测试",
  "qa_pairs": [
    {"question": "问题1？", "answer": "回答1。", "keywords": ["词1"]}
  ],
  "fact_chunks": [
    {"title": "切片1", "content": "内容1完整段落。"}
  """
    parsed_c = KnowledgeStructurer._extract_json(case_c)
    assert parsed_c and (parsed_c.get("title") == "截断测试" or len(parsed_c.get("qa_pairs", [])) >= 1), "Case C 截断修复失败"
    print("  ✓ Case C (LLM Token 超限导致未闭合的截断 JSON 自动补齐修复) 完美解析")

    # 3. Verify Multi-format document parser
    print("\n[测试 3] 验证多格式文档解析器 (DocumentParser):")
    sample_text = (
        "【问】小智如何更换WiFi？\n"
        "【答】开机时长按BOOT按键5秒进入AP配网模式，手机连接热点后打开192.168.4.1即可。\n\n"
        "一、供电规格说明\n"
        "推荐使用5V 2A适配器供电，避免USB供电不足导致喇叭破音。\n"
    )
    # Test TXT
    res_txt = DocumentParser.parse_file("manual.txt", sample_text.encode("utf-8"))
    assert res_txt["file_type"] == "txt" and "开机时长按BOOT按键" in res_txt["raw_text"]
    print("  ✓ TXT 文件解析通过")

    # Test Markdown
    res_md = DocumentParser.parse_file("guide.md", sample_text.encode("utf-8"))
    assert res_md["file_type"] == "md"
    print("  ✓ Markdown 文件解析通过")

    # Test CSV
    csv_bytes = "问题,解答\n小智怎么唤醒,呼叫你好小智即可\n".encode("utf-8-sig")
    res_csv = DocumentParser.parse_file("faq.csv", csv_bytes)
    assert res_csv["file_type"] == "csv" and "你好小智" in res_csv["raw_text"]
    print("  ✓ CSV 文件解析通过")

    # 4. Verify Local fallback & Cloud structure pipeline
    print("\n[测试 4] 验证高精知识切片与智能入库流程 (structure_document):")
    struct_res = await KnowledgeStructurer.structure_document("wifi_guide.txt", sample_text)
    assert struct_res["title"]
    assert len(struct_res["qa_pairs"]) >= 1
    assert len(struct_res["fact_chunks"]) >= 1
    print(f"  ✓ 成功提炼: 标题=《{struct_res['title']}》, 分类={struct_res['category']}")
    print(f"  ✓ QA问答数: {len(struct_res['qa_pairs'])}, 事实切片数: {len(struct_res['fact_chunks'])}, 模式: {struct_res.get('mode')}")

    # 4.1 Verify Cloud AI distillation when API Key is active
    print("\n[测试 4.1] 验证云端大模型 (DeepSeek 仿真) 知识蒸馏全流程:")
    import unittest.mock
    mock_llm_json = {
        "title": "小智开发板高级维护手册",
        "category": "硬件运维",
        "summary": "详细说明了供电与配网规范",
        "qa_pairs": [
            {"question": "小智扬声器破音怎么办？", "answer": "请更换5V/2A独立电源供电。", "keywords": ["扬声器", "破音"]},
            {"question": "如何进入配网模式？", "answer": "长按BOOT按键5秒即可。", "keywords": ["配网", "BOOT"]}
        ],
        "fact_chunks": [
            {"title": "功耗参数", "content": "全负荷工作峰值电流1.5A。"}
        ]
    }
    mock_reply_text = f"以下是提取的JSON：\n```json\n{json.dumps(mock_llm_json, ensure_ascii=False)}\n```"

    orig_key = config.relay_api_key
    try:
        config.relay_api_key = "sk-test-valid-key"
        with unittest.mock.patch("httpx.AsyncClient.post") as mock_post:
            mock_resp = unittest.mock.MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "choices": [{"message": {"content": mock_reply_text}}]
            }
            mock_post.return_value = mock_resp

            cloud_struct = await KnowledgeStructurer.structure_document("maintenance.docx", sample_text)
            assert cloud_struct["mode"] == "ai_distilled", f"Expected ai_distilled, got {cloud_struct['mode']}"
            assert cloud_struct["title"] == "小智开发板高级维护手册"
            assert len(cloud_struct["qa_pairs"]) == 2
            assert cloud_struct["qa_pairs"][0]["question"] == "小智扬声器破音怎么办？"
            print(f"  ✓ 云端 AI 深度蒸馏成功: 标题=《{cloud_struct['title']}》, 模式={cloud_struct['mode']}, QA={len(cloud_struct['qa_pairs'])}对")
    finally:
        config.relay_api_key = orig_key

    # 5. Verify Knowledge Zones & Active Roles
    print("\n[测试 5] 验证通用知识区与角色隔离体系:")
    active_zone = zone_manager.get_active_zone()
    assert active_zone and active_zone["id"]
    print(f"  ✓ 当前激活知识区: {active_zone['name']} ({active_zone['id']})")

    active_role = role_manager.get_active_role()
    assert active_role and active_role["id"]
    print(f"  ✓ 当前激活人设: {active_role['name']} (Voice: {active_role['voice']})")

    print("\n==================================================")
    print("🎉 适配全流程验证套件全部 100% 成功通过！零 Bug！")
    print("==================================================")

if __name__ == "__main__":
    asyncio.run(run_full_adaptation_test())
