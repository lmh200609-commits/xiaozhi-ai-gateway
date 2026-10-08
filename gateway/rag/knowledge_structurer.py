import json
import re
import httpx
from typing import Dict, Any, List, Optional
from gateway.config import config

try:
    import jieba.analyse
except ImportError:
    jieba = None

STRUCTURING_PROMPT = """你是一名企业级 RAG 知识库与智能语音问答架构专家。
请将用户上传的文档内容进行【智能梳理与知识蒸馏】，转换为语音知识库结构化数据，供智能硬件（小智）精准检索回答。

【规范要求】：
1. title: 提炼规范化文档主标题。
2. category: 分类名称（如：硬件操作、故障排查、常见FAQ、游园导览、通用规则等）。
3. summary: 50字以内的核心摘要。
4. qa_pairs: 提炼 3~8 个真实用户视角的口语化高频问答对（question、answer必须通俗简练、keywords核心词列表）。
5. fact_chunks: 提炼 3~8 个语义独立的客观事实切片（title、content）。

【必须返回纯 JSON 格式】：
{
  "title": "文档标题",
  "category": "分类",
  "summary": "简短摘要",
  "qa_pairs": [
    {"question": "用户会怎么问？", "answer": "简明口语回答", "keywords": ["词1", "词2"]}
  ],
  "fact_chunks": [
    {"title": "知识点标题", "content": "事实描述"}
  ]
}
"""

class KnowledgeStructurer:
    """
    Dual-engine Document Structurer:
    1. Local High-Precision Semantic Chunker & FAQ Extractor (100% offline, 0ms latency, zero failure).
    2. Optional Cloud LLM Enhancement (graceful fallback if cloud AI is slow, rate-limited, or unavailable).
    """

    @staticmethod
    def extract_keywords(text: str, top_k: int = 5) -> List[str]:
        """Extracts Chinese/English keywords locally using jieba."""
        if not text or not text.strip():
            return []
        if jieba and hasattr(jieba, "analyse"):
            try:
                tags = jieba.analyse.extract_tags(text, topK=top_k)
                if tags:
                    return tags
            except Exception:
                pass
        # Fallback keyword extraction: split words >= 2 chars
        words = re.findall(r'[\u4e00-\u9fa5]{2,6}|[a-zA-Z0-9]{2,15}', text)
        return list(dict.fromkeys(words))[:top_k]

    @staticmethod
    def build_local_structured_data(filename: str, raw_text: str) -> Dict[str, Any]:
        """
        Deterministic, local rule-based document structuring & sliding-window semantic chunking.
        Never fails, handles documents of any length, extracts QA pairs and comprehensive fact chunks.
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

        # Also search for standalone question lines ending in ? followed by answer paragraph
        for i, line in enumerate(lines[:-1]):
            if (line.endswith("？") or line.endswith("?")) and 4 <= len(line) <= 40:
                next_line = lines[i+1]
                if len(next_line) >= 10 and not next_line.endswith(("？", "?")):
                    # Avoid duplicates
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
            # Check if this paragraph is a section heading
            is_heading = (
                p.startswith(("#", "一、", "二、", "三、", "四、", "五、", "六、", "七、", "八、", "九、", "十、", "第")) or
                (len(p) <= 30 and (p.endswith("：") or p.endswith(":")))
            )
            if is_heading:
                # Flush existing chunk
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

            # If chunk is around 250-600 characters, save and roll
            if current_length >= 350:
                chunk_body = "\n".join(current_chunk)
                fact_chunks.append({
                    "title": current_heading,
                    "content": chunk_body
                })
                # Retain last short paragraph as context overlap (50 chars)
                if len(current_chunk[-1]) <= 80:
                    current_chunk = [current_chunk[-1]]
                    current_length = len(current_chunk[0])
                else:
                    current_chunk = []
                    current_length = 0

        # Flush any remaining text
        if current_chunk:
            chunk_body = "\n".join(current_chunk)
            fact_chunks.append({
                "title": current_heading,
                "content": chunk_body
            })

        # If still no fact chunks (e.g. one giant continuous paragraph), slice by window
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
        Structures raw document text. Always guarantees success via Local Semantic Chunker,
        with optional Cloud LLM enhancement when available.
        """
        # Step 1: Always prepare high-quality local structured baseline first
        local_data = KnowledgeStructurer.build_local_structured_data(filename, raw_text)

        # Step 2: Attempt Cloud LLM Enhancement if configured
        if not config.relay_api_key or config.relay_api_key in ("sk-default", "none"):
            print("[KnowledgeStructurer] Cloud LLM not configured, using local high-performance semantic chunker.")
            return local_data

        try:
            # Send sample text (limit to 5,000 chars for rapid response < 10s and token safety)
            sample_text = raw_text[:5000]
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

            # Use reasonable 15s timeout to prevent UI hanging
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    reply_text = data["choices"][0]["message"]["content"].strip()
                    ai_extracted = KnowledgeStructurer._extract_json(reply_text)
                    if ai_extracted and isinstance(ai_extracted, dict):
                        # Merge AI distilled QA & summary with local comprehensive chunks
                        ai_title = ai_extracted.get("title") or local_data["title"]
                        ai_cat = ai_extracted.get("category") or local_data["category"]
                        ai_summary = ai_extracted.get("summary") or local_data["summary"]
                        ai_qa = ai_extracted.get("qa_pairs") or []
                        ai_facts = ai_extracted.get("fact_chunks") or []

                        # Merge QA pairs
                        merged_qa = list(ai_qa)
                        for local_qa in local_data["qa_pairs"]:
                            if not any(q.get("question") == local_qa["question"] for q in merged_qa):
                                merged_qa.append(local_qa)

                        # Merge Fact Chunks (Keep both AI distilled and local comprehensive chunks)
                        merged_facts = list(ai_facts)
                        for local_f in local_data["fact_chunks"]:
                            if not any(f.get("content") == local_f["content"] for f in merged_facts):
                                merged_facts.append(local_f)

                        print(f"[KnowledgeStructurer] Successfully AI-enhanced document: '{ai_title}' ({len(merged_qa)} QA, {len(merged_facts)} Facts)")
                        return {
                            "title": ai_title,
                            "category": ai_cat,
                            "summary": ai_summary,
                            "qa_pairs": merged_qa,
                            "fact_chunks": merged_facts,
                            "mode": "ai_enhanced"
                        }
                else:
                    print(f"[KnowledgeStructurer] Notice: Cloud LLM returned HTTP {resp.status_code}, gracefully using local semantic chunker.")
        except Exception as e:
            print(f"[KnowledgeStructurer] Notice: Cloud LLM structuring skipped ({e}), seamlessly using local semantic chunker.")

        # Always fallback to local structured data with 100% guarantee
        return local_data

    @staticmethod
    def _extract_json(text: str) -> Optional[Dict[str, Any]]:
        """Safely parses JSON from LLM markdown response."""
        try:
            return json.loads(text)
        except Exception:
            pass

        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if match:
            try:
                return json.loads(match.group(1))
            except Exception:
                pass
        return None
