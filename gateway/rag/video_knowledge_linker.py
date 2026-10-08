import json
import re
import time
import httpx
from typing import Dict, Any, List, Optional
from gateway.config import config
from gateway.rag.video_manager import video_manager
from gateway.rag.knowledge_store import knowledge_store
from gateway.rag.zone_manager import zone_manager

VIDEO_ANALYSIS_PROMPT = """你是一名中国·大安机车博览园的资深文旅策展人与智能硬件语音知识库架构专家。
用户刚刚导入了一段机车/铁路相关的视频展项文件，并为你提供了一段【简短的视频内容描述】或【视频原声录音/字幕文本】。

你的核心任务是：
1. 【智能识别视频类型与主题分类】：
   - 类别需符合大安机车博览园的展览体系，例如：
     * 历史功勋蒸汽机车（如毛泽东号、朱德号、黄继光号、解放型等）
     * 世界最大规模蒸汽机车方阵（76台蒸汽机车群、前进型等）
     * 内燃机车与绿色干线时代（东风4系列、德制V100等）
     * 现代高速动车组与中国高铁（复兴号、和谐号等）
     * 百年铁路工程与历史遗迹（京张铁路、詹天佑、大安北机务段历史等）
     * 园区全景导览与探秘Vlog（园区全景、三场两馆一线一平台、实地游园等）
     * 互动体验与驾驶模拟（模拟驾驶舱、研学体验等）
2. 【生成规范的视频展项标题（title）】：
   - 提炼出大气、专业、具有文博展映品质的短片标题（如《毛泽东号机车峥嵘岁月与抗美援朝英雄历程》）。
3. 【提炼高频自然口语唤醒口令（voice_aliases）】：
   - 提取 10~20 个游客在硬件端对小铁说出的真实口语指令（如："播放1961年毛泽东号视频"、"我想看抗美援朝毛泽东号"、"看毛泽东号纪录片"、"放一下毛泽东号老视频"）。必须包含全称、常见简称、核心实体词。
4. 【知识库深度联动蒸馏（qa_pairs & fact_chunks）】：
   - 从用户提供的描述或字幕文本中，蒸馏出 2~4 条高质量的【高频 FAQ 问答对】和 2~3 条【核心事实切片】。
   - 问答必须口语化，适合小铁在小智硬件上以亲切、自豪口吻播报（2-3句话直奔重点）。
   - 切片必须事实确凿，消除代词歧义。

【必须输出严格的 JSON 格式，不要包含任何多余文本】：
{
  "title": "规范化展映短片标题",
  "category": "主题分类",
  "summary": "80字以内的视频展映简介",
  "voice_aliases": [
    "口语触发词1", "口语触发词2", "口语触发词3"
  ],
  "qa_pairs": [
    {
      "question": "游客可能会问的口语化问题？",
      "answer": "导览员小铁的亲切口语回答（2-3句内直奔核心要点）",
      "keywords": ["关键词1", "关键词2"]
    }
  ],
  "fact_chunks": [
    {
      "title": "知识切片小标题",
      "content": "独立完整的展项事实阐述"
    }
  ]
}
"""

class VideoKnowledgeLinker:
    """
    Intelligent engine that analyzes video description or ASR transcript,
    classifies the video, extracts rich natural voice triggers, generates
    RAG QA/Fact chunks, and binds them to the knowledge store and video manifest.
    """

    @staticmethod
    async def analyze_and_link(
        video_id: str,
        text_content: str,
        zone_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Takes a video ID and user-provided description or ASR transcript text.
        Invokes LLM to distill knowledge, updates video manifest, and injects RAG chunks.
        """
        # 1. Locate video in manifest
        video_manager.refresh()
        all_videos = video_manager.list_videos()
        target_video = None
        for v in all_videos:
            if v.get("video_id") == video_id or v.get("file_name") == video_id:
                target_video = v
                break

        if not target_video:
            raise ValueError(f"未在视频库中找到 ID 为 '{video_id}' 的视频")

        file_name = target_video.get("file_name", "")
        zone = zone_manager.get_zone(zone_id) or zone_manager.get_active_zone()
        zone_name = zone.get("name", "中国·大安机车博览园知识区")

        sample_text = text_content.strip()[:20000]

        user_content = (
            f"【视频文件名】：{file_name}\n"
            f"【所属知识区】：{zone_name}\n"
            f"【当前已有描述】：{target_video.get('description', '')}\n\n"
            f"【用户提供的视频内容描述 / 录音文字稿】：\n{sample_text}"
        )

        payload = {
            "model": config.model_name,
            "messages": [
                {"role": "system", "content": VIDEO_ANALYSIS_PROMPT},
                {"role": "user", "content": user_content}
            ],
            "temperature": 0.2
        }

        headers = {
            "Authorization": f"Bearer {config.relay_api_key}",
            "Content-Type": "application/json"
        }

        url = f"{config.relay_base_url.rstrip('/')}/chat/completions"

        reply_text = ""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    reply_text = data["choices"][0]["message"]["content"].strip()
                else:
                    print(f"[VideoKnowledgeLinker] Notice: Cloud LLM returned HTTP {resp.status_code}, using local heuristic extraction.")
        except Exception as ex:
            print(f"[VideoKnowledgeLinker] Notice: Cloud LLM skipped ({ex}), using local heuristic extraction.")

        # 2. Extract JSON (has built-in local heuristic fallback when reply_text is empty)
        extracted = VideoKnowledgeLinker._extract_json(reply_text, file_name, sample_text)

        final_title = extracted.get("title") or target_video.get("title") or file_name
        final_category = extracted.get("category") or target_video.get("category") or "智慧园区展项视频"
        final_summary = extracted.get("summary") or target_video.get("description") or ""
        new_aliases = extracted.get("voice_aliases") or []
        qa_pairs = extracted.get("qa_pairs") or []
        fact_chunks = extracted.get("fact_chunks") or []

        # 3. Update Video Manifest with enhanced metadata & aliases
        merged_aliases = set(target_video.get("aliases", []))
        merged_aliases.update([a.strip() for a in new_aliases if a.strip()])
        # Also clean base name
        base_clean = re.sub(r'(_1080p|_720p|_4k|1080p|720p|4k|\.mp4|\.mkv|\.avi)$', '', file_name, flags=re.IGNORECASE).strip()
        merged_aliases.add(base_clean)

        manifest_items = video_manager.load_manifest()
        updated_entry = None
        for item in manifest_items:
            if item.get("video_id") == target_video.get("video_id") or item.get("file_name") == file_name:
                item["title"] = final_title
                item["category"] = final_category
                item["description"] = final_summary
                item["aliases"] = sorted(list(merged_aliases))
                item["has_knowledge_linked"] = True
                item["linked_qa_count"] = len(qa_pairs)
                item["linked_fact_count"] = len(fact_chunks)
                item["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                updated_entry = item
                break

        if updated_entry:
            video_manager.save_manifest(manifest_items)
            video_manager.refresh()

        # 4. Inject Knowledge Document into RAG Knowledge Store
        # Create structured doc format with multimedia tags
        video_id = target_video.get("video_id")
        structured_doc = {
            "title": f"【展项视频知识】{final_title}",
            "category": final_category,
            "summary": final_summary,
            "entity_id": video_id,
            "qa_pairs": qa_pairs,
            "fact_chunks": fact_chunks
        }

        # Dynamically register / link in RailwayEntityGraph
        from gateway.rag.entity_graph import entity_graph, RailwayEntity

        existing_entity = next((e for e in entity_graph.entities if e.entity_id == video_id), None)
        if existing_entity:
            existing_entity.name = final_title
            existing_entity.category = final_category
            existing_entity.aliases = list(set(existing_entity.aliases + [a.lower() for a in merged_aliases]))
            existing_entity.video_id = video_id
            existing_entity.video_title = final_title
            existing_entity.summary = final_summary
            if fact_chunks:
                existing_entity.key_facts = [fc.get("content", "") for fc in fact_chunks[:4]]
        else:
            new_entity = RailwayEntity(
                entity_id=video_id,
                name=final_title,
                category=final_category,
                aliases=list(merged_aliases),
                zone=target_video.get("zone", "展厅大屏幕"),
                location_desc=f"{zone_name} 多媒体大屏幕",
                video_id=video_id,
                video_title=final_title,
                summary=final_summary,
                key_facts=[fc.get("content", "") for fc in fact_chunks[:4]]
            )
            entity_graph.entities.append(new_entity)

        doc_id = knowledge_store.add_structured_document(
            doc_data=structured_doc,
            raw_text=sample_text,
            file_name=f"video_{file_name}.txt",
            file_type="video_transcript",
            zone_id=zone["id"],
            zone_name=zone_name
        )

        print(f"[VideoKnowledgeLinker] Successfully linked video '{file_name}' to knowledge zone '{zone_name}' (doc_id={doc_id}, {len(qa_pairs)} QAs, {len(fact_chunks)} Facts, {len(merged_aliases)} Aliases)")

        return {
            "status": "ok",
            "video_id": target_video.get("video_id"),
            "file_name": file_name,
            "title": final_title,
            "category": final_category,
            "summary": final_summary,
            "aliases": sorted(list(merged_aliases)),
            "qa_pairs": qa_pairs,
            "fact_chunks": fact_chunks,
            "doc_id": doc_id,
            "zone_id": zone["id"],
            "zone_name": zone_name
        }

    @staticmethod
    def _extract_json(text: str, fallback_title: str, raw_text: str) -> Dict[str, Any]:
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

        # Fallback
        base_clean = re.sub(r'(_1080p|_720p|_4k|1080p|720p|4k|\.mp4|\.mkv|\.avi)$', '', fallback_title, flags=re.IGNORECASE).strip()
        return {
            "title": f"《{base_clean}专题展映短片》",
            "category": "智慧园区展项视频",
            "summary": raw_text[:120] if raw_text else "园区专属展播视频",
            "voice_aliases": [base_clean],
            "qa_pairs": [],
            "fact_chunks": [{"title": "展项概要", "content": raw_text[:300]}] if raw_text else []
        }

video_knowledge_linker = VideoKnowledgeLinker()
