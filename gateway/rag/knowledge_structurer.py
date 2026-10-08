import json
import re
import httpx
from typing import Dict, Any, List, Optional
from gateway.config import config

try:
    import jieba.analyse
except ImportError:
    jieba = None

STRUCTURING_PROMPT = """你是一名企业级 RAG 知识库与智能硬件语音问答架构专家。
请将用户上传的文档内容进行【高精度语义梳理与知识蒸馏】，转换为语音知识库结构化数据，供智能硬件（小智）在接收到用户口语提问时精准检索并播报。

【任务与输出规范】：
1. title: 规范化提炼文档主标题（去除冗余副标，简明准确）。
2. category: 提炼所属业务领域分类（如：硬件操作、故障排查、常见FAQ、产品使用、游园导览、系统规则等）。
3. summary: 100字以内的核心知识摘要。
4. qa_pairs: 提炼 5~15 个真实用户在硬件端会以口语提问的高频问答对：
   - question: 贴近真实口语提问（如："小智，如果喇叭声音卡顿该怎么办？"、"怎么重新配置WiFi？"）。
   - answer: 适合智能硬件语音播报的自然口语回答（2~4句话内直奔要点，语言亲切，严禁使用Markdown表格或代码块）。
   - keywords: 3~6个核心检索关键词列表。
5. fact_chunks: 提炼 5~15 个语义独立、信息密度高的客观事实知识切片：
   - title: 该切片的知识点小标题。
   - content: 事实陈述（消除代词歧义，保持自包含）。

【输出格式要求】：
必须返回纯 JSON 对象格式，不要输出任何额外的思考过程或闲聊：
{
  "title": "文档标题",
  "category": "领域分类",
  "summary": "文档核心摘要",
  "qa_pairs": [
    {
      "question": "用户口语提问？",
      "answer": "亲切自然的口语回答",
      "keywords": ["关键词1", "关键词2"]
    }
  ],
  "fact_chunks": [
    {
      "title": "知识切片标题",
      "content": "独立完整的客观事实描述"
    }
  ]
}
"""

class KnowledgeStructurer:
    """
    Intelligent Document Structurer:
    1. Cloud LLM Knowledge Distillation (Primary & Default):
       Dynamically uses the user's configured model (e.g. DeepSeek-V3 / DeepSeek-R1 / OpenAI compatible)
       to perform deep semantic extraction of QA pairs, fact chunks, and summaries.
    2. Local High-Precision Semantic Chunker:
       Guaranteed fallback safety net if cloud API key is unconfigured or network is unreachable.
    """

    @staticmethod
    def extract_keywords(text: str, top_k: int = 5) -> List[str]:
        """Extracts Chinese/English keywords locally using jieba or regex."""
        if not text or not text.strip():
            return []
        if jieba and hasattr(jieba, "analyse"):
            try:
                tags = jieba.analyse.extract_tags(text, topK=top_k)
                if tags:
                    return tags
            except Exception:
                pass
        words = re.findall(r'[\u4e00-\u9fa5]{2,6}|[a-zA-Z0-9]{2,15}', text)
        return list(dict.fromkeys(words))[:top_k]

    @staticmethod
    def build_local_structured_data(filename: str, raw_text: str) -> Dict[str, Any]:
        """
        Deterministic, local rule-based document structuring & sliding-window semantic chunking.
        Used as guaranteed fallback.
        """
        clean_text = raw_text.strip()
        lines = [line.strip() for line in clean_text.splitlines() if line.strip()]

        # 1. Determine Title
        title = filename
        for ext in [".docx", ".pdf", ".md", ".txt", ".csv", ".json", ".tsv"]:
            if title.lower().endswith(ext):
                title = title[:-len(ext)]

        if lines:
            first_line = re.sub(r'^[#\s一二三四五六七八九十0-9\.\、]+', '', lines[0]).strip()
            if 2 <= len(first_line) <= 35:
                title = first_line

        # 2. Determine Category
        category = "通用知识"
        cat_keywords = {
            "故障排查": ["故障", "报错", "问题", "连接失败", "异常", "无法", "排查", "修复", "破音", "卡顿"],
            "网络配置": ["wifi", "wi-fi", "网络", "热点", "ip", "配网", "蓝牙", "ap"],
            "硬件操作": ["按键", "喇叭", "屏幕", "麦克风", "供电", "type-c", "接口", "引脚", "烧录"],
            "游园导览": ["博览园", "机车", "火车", "门票", "展厅", "导览", "开放时间", "路线", "打卡"],
            "功能指南": ["使用", "指南", "手册", "教程", "操作", "说明", "功能"]
        }
        text_lower = clean_text[:2000].lower()
        for cat, kws in cat_keywords.items():
            if any(k in text_lower for k in kws):
                category = cat
                break

        # 3. Determine Summary
        summary = ""
        for line in lines[1:5]:
            if len(line) >= 15 and not line.startswith(("#", "-", "*", "一、", "1.")):
                summary = line[:120]
                break
        if not summary and lines:
            summary = lines[0][:120]

        # 4. Extract Q&A Pairs from text patterns
        qa_pairs = []
        qa_pattern = re.compile(
            r'(?:^|\n)\s*(?:[【\[]?(?:问|Q|问题|FAQ)[】\]]?|[0-9]+[、\.])\s*[：:]?\s*([^\n\?？]+[\?？]?)\s*\n+\s*(?:[【\[]?(?:答|A|回答|解答)[】\]]?[：:]?)\s*([^\n]+(?:\n(?!(?:[【\[]?(?:问|Q|问题)|[0-9]+[、\.]))[^\n]+)*)',
            re.MULTILINE
        )
        for match in qa_pattern.finditer(clean_text):
            q = match.group(1).strip()
            a = match.group(2).strip()
            if len(q) >= 3 and len(a) >= 3:
                kws = KnowledgeStructurer.extract_keywords(f"{q} {a}", top_k=5)
                qa_pairs.append({
                    "question": q,
                    "answer": a,
                    "keywords": kws
                })

        for i, line in enumerate(lines[:-1]):
            if (line.endswith("？") or line.endswith("?")) and 4 <= len(line) <= 40:
                next_line = lines[i+1]
                if len(next_line) >= 10 and not next_line.endswith(("？", "?")):
                    if not any(qa["question"] == line for qa in qa_pairs):
                        qa_pairs.append({
                            "question": line,
                            "answer": next_line,
                            "keywords": KnowledgeStructurer.extract_keywords(f"{line} {next_line}", top_k=5)
                        })

        # 5. Extract Fact Chunks with Heading Awareness & Sliding Window
        fact_chunks = []
        raw_paragraphs = [p.strip() for p in clean_text.split("\n\n") if p.strip()]

        current_heading = title
        current_chunk = []
        current_length = 0

        for p in raw_paragraphs:
            is_heading = (
                p.startswith(("#", "一、", "二、", "三、", "四、", "五、", "六、", "七、", "八、", "九、", "十、", "第")) or
                (len(p) <= 30 and (p.endswith("：") or p.endswith(":")))
            )
            if is_heading:
                if current_chunk:
                    chunk_body = "\n".join(current_chunk)
                    fact_chunks.append({
                        "title": current_heading,
                        "content": chunk_body
                    })
                    current_chunk = []
                    current_length = 0
                current_heading = re.sub(r'^[#\s]+', '', p).strip()
                continue

            current_chunk.append(p)
            current_length += len(p)

            if current_length >= 350:
                chunk_body = "\n".join(current_chunk)
                fact_chunks.append({
                    "title": current_heading,
                    "content": chunk_body
                })
                if len(current_chunk[-1]) <= 80:
                    current_chunk = [current_chunk[-1]]
                    current_length = len(current_chunk[0])
                else:
                    current_chunk = []
                    current_length = 0

        if current_chunk:
            chunk_body = "\n".join(current_chunk)
            fact_chunks.append({
                "title": current_heading,
                "content": chunk_body
            })

        if not fact_chunks and clean_text:
            chunk_size = 400
            for idx, start_i in enumerate(range(0, len(clean_text), chunk_size - 60)):
                chunk_piece = clean_text[start_i:start_i + chunk_size].strip()
                if chunk_piece:
                    fact_chunks.append({
                        "title": f"{title} (段落 {idx+1})",
                        "content": chunk_piece
                    })

        return {
            "title": title,
            "category": category,
            "summary": summary or f"关于《{title}》的核心知识档案",
            "qa_pairs": qa_pairs,
            "fact_chunks": fact_chunks,
            "mode": "local_semantic"
        }

    @staticmethod
    async def structure_document(filename: str, raw_text: str) -> Dict[str, Any]:
        """
        Structures raw document text into knowledge base entities.
        Primary: Cloud LLM configured by user (DeepSeek / OpenAI compatible).
        Fallback: Local semantic chunker (if API key not configured or API error).
        """
        clean_text = raw_text.strip()
        if not clean_text:
            raise ValueError("文档内容为空")

        # Prepare local baseline chunk data in case fallback or chunk merging is needed
        local_data = KnowledgeStructurer.build_local_structured_data(filename, clean_text)

        # Check API Key configuration
        api_key = (config.relay_api_key or "").strip()
        if not api_key or api_key in ("sk-default", "none"):
            msg = "未配置大模型 API Key。已使用本地高精切片引擎为您完成入库。如需获得最佳 AI 问答蒸馏效果，请前往【网关系统配置】填入您的 DeepSeek API Key。"
            print(f"[KnowledgeStructurer] {msg}")
            local_data["warning"] = msg
            local_data["mode"] = "local_semantic"
            return local_data

        chat_url = config.get_chat_url()
        model_name = config.model_name or "deepseek-chat"

        # Long document strategy: If text > 10,000 characters, chunk and process segments
        segments = []
        if len(clean_text) <= 9000:
            segments.append(clean_text)
        else:
            # Multi-segment distillation for extensive documents
            step = 7000
            for i in range(0, min(len(clean_text), 21000), step):
                segments.append(clean_text[i:i + step])

        accumulated_qa = []
        accumulated_facts = []
        final_title = local_data["title"]
        final_category = local_data["category"]
        final_summary = local_data["summary"]

        for seg_idx, segment in enumerate(segments):
            seg_prefix = f" (第 {seg_idx+1} 部分)" if len(segments) > 1 else ""
            user_content = (
                f"【文件名】：{filename}{seg_prefix}\n\n"
                f"【文档内容】：\n{segment}"
            )

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": STRUCTURING_PROMPT},
                    {"role": "user", "content": user_content}
                ],
                "temperature": 0.2,
                "max_tokens": 4096,
                "response_format": {"type": "json_object"}
            }

            # 60s timeout for thorough LLM distillation
            async with httpx.AsyncClient(timeout=60.0) as client:
                try:
                    resp = await client.post(chat_url, json=payload, headers=headers)
                    # If response_format is rejected by some older proxy, retry without it
                    if resp.status_code == 400 and "response_format" in resp.text:
                        payload.pop("response_format", None)
                        resp = await client.post(chat_url, json=payload, headers=headers)

                    if resp.status_code == 200:
                        res_json = resp.json()
                        reply_content = res_json["choices"][0]["message"]["content"]
                        parsed_llm = KnowledgeStructurer._extract_json(reply_content)

                        if parsed_llm and isinstance(parsed_llm, dict):
                            if seg_idx == 0:
                                if parsed_llm.get("title"):
                                    final_title = str(parsed_llm["title"]).strip()
                                if parsed_llm.get("category"):
                                    final_category = str(parsed_llm["category"]).strip()
                                if parsed_llm.get("summary"):
                                    final_summary = str(parsed_llm["summary"]).strip()

                            qa_list = parsed_llm.get("qa_pairs") or []
                            for qa in qa_list:
                                if isinstance(qa, dict) and qa.get("question") and qa.get("answer"):
                                    # Normalize keywords
                                    if not qa.get("keywords"):
                                        qa["keywords"] = KnowledgeStructurer.extract_keywords(f"{qa['question']} {qa['answer']}", 4)
                                    accumulated_qa.append(qa)

                            fact_list = parsed_llm.get("fact_chunks") or []
                            for fc in fact_list:
                                if isinstance(fc, dict) and fc.get("content"):
                                    if not fc.get("title"):
                                        fc["title"] = final_title
                                    accumulated_facts.append(fc)

                    elif resp.status_code == 401:
                        warn_msg = f"大模型认证失败 (HTTP 401: API Key 无效或未生效)。已切换为本地高精切片引擎保底入库，请在【系统配置】中检查 API Key。"
                        print(f"[KnowledgeStructurer] {warn_msg}")
                        local_data["warning"] = warn_msg
                        return local_data
                    elif resp.status_code == 402:
                        warn_msg = f"大模型账户余额不足 (HTTP 402)。已切换为本地高精切片引擎保底入库，请为您的 API 账户充值。"
                        print(f"[KnowledgeStructurer] {warn_msg}")
                        local_data["warning"] = warn_msg
                        return local_data
                    else:
                        print(f"[KnowledgeStructurer] LLM API returned HTTP {resp.status_code}: {resp.text[:200]}")
                except Exception as ex_call:
                    print(f"[KnowledgeStructurer] LLM call exception: {ex_call}")

        # If LLM successfully distilled data
        if accumulated_qa or accumulated_facts:
            # De-duplicate QA pairs
            unique_qa = []
            seen_q = set()
            for qa in accumulated_qa:
                q_text = qa.get("question", "").strip()
                if q_text and q_text not in seen_q:
                    seen_q.add(q_text)
                    unique_qa.append(qa)

            # De-duplicate Facts
            unique_facts = []
            seen_f = set()
            for fc in accumulated_facts:
                f_text = fc.get("content", "").strip()
                if f_text and f_text not in seen_f:
                    seen_f.add(f_text)
                    unique_facts.append(fc)

            # If document had many sections, also retain any local facts that weren't captured
            for loc_f in local_data["fact_chunks"]:
                if len(unique_facts) < 25 and loc_f["content"] not in seen_f:
                    unique_facts.append(loc_f)
                    seen_f.add(loc_f["content"])

            print(f"[KnowledgeStructurer] ✅ Cloud AI ({model_name}) distilled '{final_title}': {len(unique_qa)} QAs, {len(unique_facts)} Facts")
            return {
                "title": final_title,
                "category": final_category,
                "summary": final_summary,
                "qa_pairs": unique_qa,
                "fact_chunks": unique_facts,
                "mode": "ai_distilled",
                "model": model_name
            }

        # Fallback to local structured data
        print("[KnowledgeStructurer] Cloud LLM extraction produced empty result, safely falling back to local semantic chunker.")
        local_data["warning"] = f"云端大模型未能返回有效知识切片，已使用本地高精切片引擎为您完成入库。"
        return local_data

    @staticmethod
    def _extract_json(text: str) -> Optional[Dict[str, Any]]:
        """
        Ultra-resilient JSON parser:
        1. Strips <think>...</think> reasoning blocks.
        2. Strips markdown fences.
        3. Cleans common JSON syntax issues (trailing commas, unescaped characters).
        4. Auto-repairs truncated JSON objects.
        5. Fallback regex extraction of QA pairs and fact chunks.
        """
        if not text:
            return None

        # 1. Strip reasoning blocks from models like DeepSeek-R1
        cleaned = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE).strip()

        # 2. Extract content from markdown block if present
        md_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
        if md_match:
            candidate = md_match.group(1).strip()
        else:
            candidate = cleaned

        # Try direct parse
        try:
            return json.loads(candidate)
        except Exception:
            pass

        # 3. Locate JSON boundaries between first { and last }
        start_idx = candidate.find('{')
        end_idx = candidate.rfind('}')
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            sub_json = candidate[start_idx:end_idx + 1]
            # Fix trailing commas
            sub_json_fixed = re.sub(r',\s*([}\]])', r'\1', sub_json)
            try:
                return json.loads(sub_json_fixed)
            except Exception:
                pass

        # 4. Auto-repair truncated JSON (e.g. output cut off mid-way)
        if start_idx != -1:
            truncated = candidate[start_idx:]
            # Remove trailing dangling characters
            truncated = re.sub(r',\s*$', '', truncated)
            # Close unclosed strings if dangling quote
            quote_count = truncated.count('"') - truncated.count(r'\"')
            if quote_count % 2 != 0:
                truncated += '"'
            # Close unclosed arrays and objects
            open_braces = truncated.count('{') - truncated.count('}')
            open_brackets = truncated.count('[') - truncated.count(']')
            truncated += (']' * max(0, open_brackets)) + ('}' * max(0, open_braces))
            try:
                truncated_fixed = re.sub(r',\s*([}\]])', r'\1', truncated)
                return json.loads(truncated_fixed)
            except Exception:
                pass

        # 5. Regex rescue extraction: extract QA pairs and fact chunks individually
        res_qa = []
        qa_matches = re.finditer(
            r'\{\s*"question"\s*:\s*"([^"]+)"\s*,\s*"answer"\s*:\s*"([^"]+)"',
            candidate
        )
        for m in qa_matches:
            q = m.group(1).strip()
            a = m.group(2).strip()
            res_qa.append({
                "question": q,
                "answer": a,
                "keywords": KnowledgeStructurer.extract_keywords(f"{q} {a}", 4)
            })

        res_facts = []
        fact_matches = re.finditer(
            r'\{\s*"title"\s*:\s*"([^"]+)"\s*,\s*"content"\s*:\s*"([^"]+)"',
            candidate
        )
        for m in fact_matches:
            res_facts.append({
                "title": m.group(1).strip(),
                "content": m.group(2).strip()
            })

        title_m = re.search(r'"title"\s*:\s*"([^"]+)"', candidate)
        cat_m = re.search(r'"category"\s*:\s*"([^"]+)"', candidate)
        sum_m = re.search(r'"summary"\s*:\s*"([^"]+)"', candidate)

        if res_qa or res_facts or title_m:
            return {
                "title": title_m.group(1) if title_m else "知识文档",
                "category": cat_m.group(1) if cat_m else "通用知识",
                "summary": sum_m.group(1) if sum_m else "",
                "qa_pairs": res_qa,
                "fact_chunks": res_facts
            }

        return None
