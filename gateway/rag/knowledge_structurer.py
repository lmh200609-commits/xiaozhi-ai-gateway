import json
import re
import httpx
from typing import Dict, Any, Optional
from gateway.config import config

STRUCTURING_PROMPT = """你是一名企业级标准 RAG 知识库与智能硬件语音问答架构专家。
你的任务是将用户上传的原始文档内容进行【智能梳理与知识蒸馏】，将其转换为符合标准语音知识库规范的结构化数据，以便智能硬件助手（小智）能够以最高命中率、最低延迟检索并回答用户。

【梳理规范要求】：
1. 提炼核心标题（title）与分类（category，如：硬件控制、功能说明、故障排查、常见FAQ、通用规则等）。
2. 生成一段简明扼要的摘要（summary，50字以内）。
3. 重点提取【高频 FAQ 问答对（qa_pairs）】：
   - question：必须站在普通用户视角，模拟真实、自然的口语化提问（如“怎么调节屏幕亮度？”、“连不上WiFi怎么办？”）。
   - answer：回答必须客观准确、简明干练、非常适合语音直接播报（1-3句话，避免Markdown表格或复杂代码）。
   - keywords：提取该问答对应的核心检索实体与同义词列表（如 ["亮度", "屏幕", "太暗", "调亮"]）。
4. 提取【核心事实知识切片（fact_chunks）】：
   - 每个切片必须是语义独立的完整段落，消除代词歧义（把“它”、“这个功能”替换为具体名称）。

【必须返回纯 JSON 格式】，结构如下：
{
  "title": "规范化文档标题",
  "category": "分类名称",
  "summary": "简短摘要",
  "qa_pairs": [
    {
      "question": "用户可能会怎么问？",
      "answer": "口语化标准回答",
      "keywords": ["关键词1", "关键词2"]
    }
  ],
  "fact_chunks": [
    {
      "title": "小知识点标题",
      "content": "独立完整的事实阐述"
    }
  ]
}
"""

class KnowledgeStructurer:
    """
    Uses Gemini 3.8 Flash to distill raw unstructured documents into standardized RAG QA pairs & facts.
    """
    @staticmethod
    async def structure_document(filename: str, raw_text: str) -> Dict[str, Any]:
        # Truncate text if excessively large to protect token limits (e.g. up to 30,000 characters)
        sample_text = raw_text[:30000]

        user_content = f"【文件名】：{filename}\n\n【原始文档内容】：\n{sample_text}"

        payload = {
            "model": config.model_name,
            "messages": [
                {"role": "system", "content": STRUCTURING_PROMPT},
                {"role": "user", "content": user_content}
            ],
            "temperature": 0.2
        }

        headers = {
            "Authorization": f"Bearer {config.relay_api_key}",
            "Content-Type": "application/json"
        }

        url = f"{config.relay_base_url.rstrip('/')}/chat/completions"

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code != 200:
                raise RuntimeError(f"大模型中转请求失败 (HTTP {resp.status_code}): {resp.text}")
            
            data = resp.json()
            reply_text = data["choices"][0]["message"]["content"].strip()

        # Parse JSON from reply
        return KnowledgeStructurer._extract_json(reply_text, filename, raw_text)

    @staticmethod
    def _extract_json(text: str, fallback_title: str, raw_text: str) -> Dict[str, Any]:
        # Try direct JSON parse
        try:
            return json.loads(text)
        except Exception:
            pass

        # Match markdown ```json ... ```
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if match:
            try:
                return json.loads(match.group(1))
            except Exception:
                pass

        # Fallback if LLM didn't return valid JSON
        print("[Structurer] Warning: Failed to parse LLM JSON, generating fallback structure.")
        paragraphs = [p.strip() for p in raw_text.split("\n\n") if p.strip()]
        return {
            "title": fallback_title,
            "category": "通用文档",
            "summary": "自动录入的本地知识文档",
            "qa_pairs": [],
            "fact_chunks": [
                {"title": f"切片 {i+1}", "content": p} for i, p in enumerate(paragraphs[:10])
            ]
        }
