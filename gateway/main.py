import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import asyncio
import json
import time
import numpy as np
from pathlib import Path
from typing import Optional

import os
import urllib.parse
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from gateway.config import config
from gateway.audio.opus_codec import OpusDecoderWrapper
from gateway.audio.vad import EnergyVAD
from gateway.asr.sense_voice import get_asr_engine
from gateway.tts.edge_tts_streamer import EdgeTTSStreamer, split_sentences, clean_speech_text
from gateway.llm.relay_client import RelayLLMClient
from gateway.rag.knowledge_store import knowledge_store
from gateway.rag.document_parser import DocumentParser
from gateway.rag.knowledge_structurer import KnowledgeStructurer
from gateway.rag.zone_manager import zone_manager
from gateway.rag.video_manager import video_manager
from gateway.roles.role_manager import role_manager
from gateway.agent.pc_tools import PC_TOOLS_DEFINITIONS, execute_pc_tool, execute_play_video, filter_tools_for_query

app = FastAPI(title="Xiaozhi Hardware Gateway", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_no_cache_header(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.endswith((".html", ".js", ".css")):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# In-memory device tracker and conversation logs for Web Console
active_devices = {}
recent_logs = []
MAX_LOGS = 100
current_active_video = None
kiosk_websockets = set()

async def broadcast_kiosk_event(event: dict):
    if not kiosk_websockets:
        return
    msg = json.dumps(event, ensure_ascii=False)
    dead = []
    for ws in list(kiosk_websockets):
        try:
            await ws.send_text(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        kiosk_websockets.discard(ws)

def add_log(entry: dict):
    entry["timestamp"] = time.strftime("%H:%M:%S")
    recent_logs.insert(0, entry)
    if len(recent_logs) > MAX_LOGS:
        recent_logs.pop()

@app.on_event("startup")
async def startup_event():
    print("==================================================")
    print("🚀 小智 AI 硬件专属语音中转网关已启动!")
    print(f"📡 监听地址: http://{config.host}:{config.port}")
    print(f"🔗 WebSocket 端点: ws://{config.host}:{config.port}/xiaozhi/v1/")
    print(f"🖥️ 展厅大屏 WebSocket: ws://{config.host}:{config.port}/ws/kiosk")
    print(f"🤖 大模型中转目标: {config.relay_base_url} (模型: {config.model_name})")
    print(f"🎙️ ASR 引擎: SenseVoice-Small (本地极速 INT8)")
    print(f"🔊 TTS 引擎: Edge-TTS ({config.tts_voice})")
    print("==================================================")
    # Pre-warm ASR engine in background
    asyncio.get_event_loop().run_in_executor(None, get_asr_engine)

# ----------------- REST API for Console -----------------

@app.get("/api/status")
async def get_status():
    safe_devices = []
    for d in active_devices.values():
        dev_copy = dict(d)
        dev_copy.pop("ws", None)
        safe_devices.append(dev_copy)

    return {
        "devices_online": len(safe_devices),
        "devices": safe_devices,
        "config": config.model_dump(),
        "active_role": role_manager.get_active_role(),
        "active_zone": zone_manager.get_active_zone(),
        "knowledge_count": len(knowledge_store.list_documents()),
        "video_count": len(video_manager.list_videos()),
        "active_video": current_active_video,
    }

@app.websocket("/ws/kiosk")
async def kiosk_ws_endpoint(websocket: WebSocket):
    global current_active_video
    await websocket.accept()
    kiosk_websockets.add(websocket)
    print(f"[Kiosk WS] 展厅大屏客户端已建立低延迟长连接 (在线屏数: {len(kiosk_websockets)})")
    try:
        # Send initial status snapshot
        safe_devices = []
        for d in active_devices.values():
            dev_copy = dict(d)
            dev_copy.pop("ws", None)
            safe_devices.append(dev_copy)
        await websocket.send_text(json.dumps({
            "type": "init",
            "active_video": current_active_video,
            "devices_online": len(safe_devices),
            "devices": safe_devices
        }, ensure_ascii=False))

        while True:
            msg = await websocket.receive_text()
            try:
                data = json.loads(msg)
                action = data.get("type")
                if action == "close_video":
                    current_active_video = None
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, execute_pc_tool, "close_video", {})
                    await broadcast_kiosk_event({"type": "close_video"})
                elif action == "play_video":
                    vid = data.get("video_id")
                    title = data.get("title", "")
                    if vid:
                        v = video_manager.find_video(vid)
                        if v:
                            res = {
                                "status": "success",
                                "video_id": v["video_id"],
                                "title": v["title"],
                                "path": v["file_path"],
                                "keyword": v["title"]
                            }
                            current_active_video = res
                            await broadcast_kiosk_event({
                                "type": "play_video",
                                "video_id": v["video_id"],
                                "title": v["title"]
                            })
            except Exception:
                pass
    except WebSocketDisconnect:
        kiosk_websockets.discard(websocket)
        print(f"[Kiosk WS] 展厅大屏客户端断开 (剩余在线: {len(kiosk_websockets)})")
    except Exception as e:
        kiosk_websockets.discard(websocket)
        print(f"[Kiosk WS] 连接异常: {e}")

@app.get("/kiosk")
async def get_kiosk():
    kiosk_path = Path(__file__).parent / "web" / "kiosk.html"
    if kiosk_path.exists():
        return FileResponse(str(kiosk_path), media_type="text/html; charset=utf-8")
    return JSONResponse(status_code=404, content={"error": "kiosk.html not found"})

@app.post("/api/video/close")
async def close_active_video():
    global current_active_video
    current_active_video = None
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, execute_pc_tool, "close_video", {})
    await broadcast_kiosk_event({"type": "close_video"})
    return {"status": "ok", "message": "展厅大屏幕视频展映已关闭"}

@app.get("/api/videos/stream")
async def stream_local_video(path: Optional[str] = None, video_id: Optional[str] = None):
    from gateway.rag.video_manager import VIDEOS_DIR
    target_path = None
    if video_id:
        # 1. Video manager smart match
        v = video_manager.find_video(video_id)
        if v and os.path.exists(v.get("file_path", "")):
            target_path = v["file_path"]
        else:
            # 2. Check direct filename match in VIDEOS_DIR
            cand_p1 = VIDEOS_DIR / video_id
            if cand_p1.exists() and cand_p1.is_file():
                target_path = str(cand_p1)
            else:
                cand_p2 = VIDEOS_DIR / f"{video_id}.mp4"
                if cand_p2.exists() and cand_p2.is_file():
                    target_path = str(cand_p2)

    if not target_path and path:
        decoded_path = urllib.parse.unquote(path)
        if os.path.exists(decoded_path) and os.path.isfile(decoded_path):
            target_path = decoded_path
        else:
            cand1 = VIDEOS_DIR / decoded_path
            if cand1.exists() and cand1.is_file():
                target_path = str(cand1)
            else:
                cand2 = VIDEOS_DIR / os.path.basename(decoded_path)
                if cand2.exists() and cand2.is_file():
                    target_path = str(cand2)
                else:
                    v = video_manager.find_video(decoded_path)
                    if v and os.path.exists(v.get("file_path", "")):
                        target_path = v["file_path"]

    if target_path and os.path.exists(target_path) and os.path.isfile(target_path):
        target_path = os.path.normpath(target_path)
        return FileResponse(
            target_path,
            media_type="video/mp4",
            headers={
                "Accept-Ranges": "bytes",
                "Cache-Control": "public, max-age=86400"
            }
        )
    return JSONResponse(status_code=404, content={"error": f"Video not found: path={path}, id={video_id}"})

@app.get("/api/logs")
async def get_logs():
    return recent_logs

@app.post("/api/config")
async def update_config(req: Request):
    data = await req.json()
    for k, v in data.items():
        if hasattr(config, k):
            setattr(config, k, v)
    config.save()
    return {"status": "ok", "config": config.model_dump()}

# ----------------- Roles & Personas API -----------------

@app.get("/api/roles")
async def get_roles():
    return {
        "roles": role_manager.get_roles(),
        "active_role": role_manager.get_active_role()
    }

@app.post("/api/roles/active")
async def set_active_role(req: Request):
    data = await req.json()
    role_id = data.get("role_id")
    if not role_id:
        return JSONResponse(status_code=400, content={"error": "Missing role_id"})
    success = role_manager.set_active_role(role_id)
    if success:
        active = role_manager.get_active_role()
        if active.get("zone_id"):
            zone_manager.set_active_zone(active["zone_id"])
        print(f"[Role] Switched active role to: {active['name']} ({active['id']}) [zone: {active.get('zone_id')}]")
        await broadcast_kiosk_event({
            "type": "role_switch",
            "role": active
        })
        return {"status": "ok", "active_role": active, "active_zone": zone_manager.get_active_zone()}
    return JSONResponse(status_code=404, content={"error": "Role not found"})

@app.post("/api/roles")
async def save_role(req: Request):
    data = await req.json()
    role_id = data.get("id")
    if role_id:
        updated = role_manager.update_role(role_id, data)
        if updated:
            return {"status": "ok", "role": updated}
    new_role = role_manager.add_role(data)
    return {"status": "ok", "role": new_role}

@app.delete("/api/roles/{role_id}")
async def delete_role(role_id: str):
    success = role_manager.delete_role(role_id)
    if success:
        return {"status": "ok"}
    return JSONResponse(status_code=400, content={"error": "预设角色不可删除或角色不存在"})

# ----------------- Knowledge Zones (知识区) API -----------------

@app.get("/api/zones")
async def get_zones():
    zones = zone_manager.list_zones()
    all_docs = knowledge_store.list_documents()
    all_vids = video_manager.list_videos()

    enriched = []
    for z in zones:
        zid = z["id"]
        z_docs = [d for d in all_docs if d.get("zone_id") == zid]
        z_vids = [v for v in all_vids if v.get("zone_id") == zid]
        z_vids_ready = [v for v in z_vids if v.get("is_present")]
        enriched.append({
            **z,
            "doc_count": len(z_docs),
            "video_count": len(z_vids),
            "video_ready_count": len(z_vids_ready),
            "is_active": (zid == zone_manager.active_zone_id)
        })
    return {
        "status": "ok",
        "zones": enriched,
        "active_zone": zone_manager.get_active_zone()
    }

@app.post("/api/zones")
async def create_zone(req: Request):
    data = await req.json()
    name = data.get("name", "").strip()
    if not name:
        return JSONResponse(status_code=400, content={"error": "知识区名称不能为空"})
    description = data.get("description", "").strip()
    icon = data.get("icon", "🏛️").strip()
    new_zone = zone_manager.create_zone(name=name, description=description, icon=icon)
    return {"status": "ok", "zone": new_zone}

@app.post("/api/zones/active")
async def set_active_zone(req: Request):
    data = await req.json()
    zone_id = data.get("zone_id")
    if not zone_id:
        return JSONResponse(status_code=400, content={"error": "Missing zone_id"})
    if zone_manager.set_active_zone(zone_id):
        return {"status": "ok", "active_zone": zone_manager.get_active_zone()}
    return JSONResponse(status_code=404, content={"error": "知识区不存在"})

@app.delete("/api/zones/{zone_id}")
async def delete_zone(zone_id: str):
    success = zone_manager.delete_zone(zone_id)
    if success:
        return {"status": "ok"}
    return JSONResponse(status_code=400, content={"error": "默认知识区不可删除或知识区不存在"})

# ----------------- Knowledge Base (RAG) API -----------------

@app.get("/api/knowledge")
async def get_knowledge(zone_id: Optional[str] = None):
    return {"documents": knowledge_store.list_documents(zone_id=zone_id)}

@app.get("/api/knowledge/{doc_id}")
async def get_knowledge_doc(doc_id: str):
    doc = knowledge_store.get_document_details(doc_id)
    if not doc:
        return JSONResponse(status_code=404, content={"error": "文档不存在"})
    return {"document": doc}

@app.post("/api/knowledge/upload")
async def upload_knowledge_file(
    file: UploadFile = File(...),
    zone_id: str = Form("baicheng_railway")
):
    try:
        filename = file.filename or "upload.txt"
        content_bytes = await file.read()
        if not content_bytes:
            return JSONResponse(status_code=400, content={"error": "上传的文件为空"})

        parsed = DocumentParser.parse_file(filename, content_bytes)
        raw_text = parsed["raw_text"]
        if not raw_text.strip():
            return JSONResponse(status_code=400, content={"error": "未能从文件中解析出有效文本内容"})

        target_zone = zone_manager.get_zone(zone_id) or zone_manager.get_active_zone()
        zone_name = target_zone.get("name", "白城火车园区知识区")

        print(f"[RAG Upload] Starting document structuring for: {filename} in zone: {zone_name}...")
        try:
            structured_data = await KnowledgeStructurer.structure_document(filename, raw_text)
        except Exception as ex_struct:
            print(f"[RAG Upload] Cloud structuring exception: {ex_struct}, falling back to local semantic chunker")
            structured_data = KnowledgeStructurer.build_local_structured_data(filename, raw_text)

        doc_id = knowledge_store.add_structured_document(
            doc_data=structured_data,
            raw_text=raw_text,
            file_name=filename,
            file_type=parsed["file_type"],
            zone_id=target_zone["id"],
            zone_name=zone_name
        )
        return {
            "status": "ok",
            "doc_id": doc_id,
            "title": structured_data.get("title", filename),
            "category": structured_data.get("category", "通用"),
            "summary": structured_data.get("summary", ""),
            "zone_id": target_zone["id"],
            "zone_name": zone_name,
            "qa_count": len(structured_data.get("qa_pairs", [])),
            "fact_count": len(structured_data.get("fact_chunks", [])),
            "mode": structured_data.get("mode", "local_semantic")
        }
    except Exception as e:
        print(f"[RAG Upload] Error: {e}")
        return JSONResponse(status_code=500, content={"error": f"文档处理失败: {str(e)}"})

@app.post("/api/knowledge")
async def add_knowledge(req: Request):
    data = await req.json()
    title = data.get("title", "").strip()
    content = data.get("content", "").strip()
    category = data.get("category", "通用").strip()
    zone_id = data.get("zone_id") or zone_manager.active_zone_id
    target_zone = zone_manager.get_zone(zone_id) or zone_manager.get_active_zone()

    if not title or not content:
        return JSONResponse(status_code=400, content={"error": "标题和内容不能为空"})
    doc_id = knowledge_store.add_document(
        title=title,
        content=content,
        category=category,
        zone_id=target_zone["id"],
        zone_name=target_zone.get("name", "白城火车园区知识区")
    )
    return {"status": "ok", "doc_id": doc_id}

@app.delete("/api/knowledge/{doc_id}")
async def delete_knowledge(doc_id: str):
    knowledge_store.delete_document(doc_id)
    return {"status": "ok"}

@app.post("/api/knowledge/search")
async def search_knowledge(req: Request):
    data = await req.json()
    query = data.get("query", "").strip()
    top_k = int(data.get("top_k", 3))
    min_score = float(data.get("min_score", 0.3))
    t0 = time.time()
    results = knowledge_store.search(query, top_k=top_k, min_score=min_score)
    cost_ms = (time.time() - t0) * 1000.0
    return {"query": query, "results": results, "cost_ms": round(cost_ms, 1)}

# ----------------- Video Assets & Knowledge Zone Videos API -----------------

@app.get("/api/videos")
async def get_videos(zone_id: Optional[str] = None):
    try:
        video_manager.refresh()
        videos = video_manager.list_videos(zone_id=zone_id)
        return {
            "status": "ok",
            "count": len(videos),
            "videos": videos,
            "videos_dir": str(video_manager.videos_dir)
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/videos/upload")
async def upload_video_file(
    file: UploadFile = File(...),
    zone_id: str = Form("baicheng_railway"),
    title: Optional[str] = Form(None),
    aliases: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    transcript_text: Optional[str] = Form(None)
):
    try:
        filename = file.filename or "video.mp4"
        ext = os.path.splitext(filename)[1].lower()
        if ext not in (".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm"):
            return JSONResponse(status_code=400, content={"error": f"不支持的视频格式: {ext}，请上传 mp4/mkv/avi/mov 视频"})

        target_zone = zone_manager.get_zone(zone_id) or zone_manager.get_active_zone()
        zone_name = target_zone.get("name", "中国·大安机车博览园知识区")

        save_path = video_manager.videos_dir / filename
        content = await file.read()
        with open(save_path, "wb") as f:
            f.write(content)

        file_size = len(content)

        alias_list = []
        if aliases:
            alias_list = [a.strip() for a in aliases.replace("，", ",").split(",") if a.strip()]

        registered = video_manager.register_uploaded_video(
            file_name=filename,
            file_size=file_size,
            zone_id=target_zone["id"],
            zone_name=zone_name,
            title=title,
            aliases=alias_list,
            category=category,
            description=description
        )

        # If user provided description or ASR transcript, automatically run AI knowledge linkage!
        ai_link_res = None
        if transcript_text and transcript_text.strip():
            from gateway.rag.video_knowledge_linker import video_knowledge_linker
            try:
                ai_link_res = await video_knowledge_linker.analyze_and_link(
                    video_id=registered["video_id"],
                    text_content=transcript_text.strip(),
                    zone_id=target_zone["id"]
                )
            except Exception as ex:
                print(f"[Video Upload] Warning: AI link failed: {ex}")

        return {
            "status": "ok",
            "message": f"视频《{filename}》已成功存入【{zone_name}】并建立口令检索！",
            "video": registered,
            "ai_link": ai_link_res
        }
    except Exception as e:
        print(f"[Video Upload] Error: {e}")
        return JSONResponse(status_code=500, content={"error": f"视频上传处理失败: {str(e)}"})

@app.post("/api/videos/ai-link")
async def ai_link_video(req: Request):
    """
    Analyzes video description or ASR speech transcript text, automatically
    identifies video category, extracts natural voice aliases, and generates
    FAQ / Fact chunks into the active knowledge zone.
    """
    data = await req.json()
    video_id = data.get("video_id")
    text = data.get("text", "").strip()
    zone_id = data.get("zone_id") or zone_manager.active_zone_id

    if not video_id or not text:
        return JSONResponse(status_code=400, content={"error": "请提供有效的 video_id 和视频描述/原声文字内容"})

    from gateway.rag.video_knowledge_linker import video_knowledge_linker
    try:
        result = await video_knowledge_linker.analyze_and_link(video_id, text, zone_id)
        return {"status": "ok", "result": result}
    except Exception as e:
        print(f"[AI Video Link] Error: {e}")
        return JSONResponse(status_code=500, content={"error": f"AI 智能识别与知识库联动失败: {str(e)}"})

@app.post("/api/videos/play_test")
async def play_video_test(req: Request):
    global current_active_video
    data = {}
    try:
        data = await req.json()
    except Exception:
        try:
            body = await req.body()
            data = json.loads(body.decode("utf-8", errors="ignore"))
        except Exception:
            data = {}
    keyword = data.get("keyword") or data.get("file_name") or data.get("title") or ""
    if not keyword:
        return JSONResponse(status_code=400, content={"error": "请指定要测试播放的视频名称或口令"})

    loop = asyncio.get_event_loop()
    res = await loop.run_in_executor(None, execute_play_video, keyword)
    if res.get("status") == "success":
        current_active_video = res
        return {"status": "ok", "result": res}
    return JSONResponse(status_code=404, content={"error": res.get("message", "未找到可播放视频")})

@app.put("/api/videos/{video_id}")
async def update_video_meta(video_id: str, req: Request):
    data = await req.json()
    updated = video_manager.update_video_meta(video_id, data)
    if updated:
        return {"status": "ok", "video": updated}
    return JSONResponse(status_code=404, content={"error": "视频展项不存在"})

@app.delete("/api/videos/{video_id}")
async def delete_video(video_id: str, delete_file: bool = True):
    success = video_manager.delete_video(video_id, delete_file=delete_file)
    if success:
        return {"status": "ok", "message": "视频展项已删除"}
    return JSONResponse(status_code=404, content={"error": "视频不存在"})

def build_effective_prompt(role: dict, user_text: str, rag_matched: list) -> str:
    """
    Builds the complete dynamic system prompt taking into account:
    - Active role persona & voice constraints
    - Preschool teacher vs railway guide vs general assistant
    - Storytelling / Bedtime accompaniment mode (long-form continuous warm speech)
    - Everyday Q&A mode (concise 2-4 sentences)
    - Strict prohibition of Markdown asterisks (* and **) for speech output
    """
    effective_prompt = role.get("system_prompt", config.system_prompt)
    is_railway_role = (
        role.get("id") == "railway_guide" or 
        "小铁" in role.get("name", "") or 
        "博览园" in role.get("name", "")
    )
    is_preschool_role = (
        role.get("id") == "custom_46589c60" or 
        "幼教" in role.get("name", "") or 
        "儿童" in role.get("name", "") or
        "宝宝" in role.get("name", "")
    )

    story_keywords = ["故事", "睡前", "哄睡", "童话", "晚安", "睡觉", "睡不着", "摇篮", "寓言", "讲个", "讲一篇", "陪伴"]
    is_story_intent = any(k in user_text for k in story_keywords)

    target_zone_id = role.get("zone_id") or zone_manager.active_zone_id
    zone_obj = zone_manager.get_zone(target_zone_id)
    zone_title = zone_obj.get("name", "专属知识库") if zone_obj else "专属知识库"

    if rag_matched:
        docs_text = "\n\n".join([f"[{i+1}] 《{c['title']}》: {c['content']}" for i, c in enumerate(rag_matched)])
        if is_railway_role:
            effective_prompt += (
                f"\n\n【中国·大安机车博览园 权威参考资料】：\n{docs_text}\n"
                f"【解说规范】：请结合以上资料，以大安机车博览园智慧导览员小铁的亲切自豪口吻为游客生动解说，篇幅2-3句话直奔核心要点，热情自然。严禁输出任何星号（*或**）或加粗符号！"
            )
            first_hit = rag_matched[0]
            if first_hit.get("entity", {}).get("has_multimedia"):
                ent = first_hit["entity"]
                effective_prompt += (
                    f"\n【展项专题视频资源】：本展项在后台配有展映短片《{ent['video_title']}》（对应关键词: '{ent['name']}'）。\n"
                    f"【视频交互规范（核心原则）】：\n"
                    f"1. 仅当游客发出明确播放指令（如“播放视频”、“我想看视频”、“放一下毛泽东号短片”、“大屏播放”）时，才可调用 play_video(keyword='{ent['name']}')。\n"
                    f"2. 若游客只是询问“需要看什么视频”、“有什么视频推荐”、“能看什么片子”等咨询探索类问题，绝对禁止直接调用 play_video！你应以小铁的亲切口吻热情介绍博览园有哪些精彩短片（如毛泽东号峥嵘岁月、复兴号智能动车组、百年京张等），并主动询问游客想先看哪一部。"
                )
        elif is_story_intent or (is_preschool_role and any("故事" in c.get("title", "") for c in rag_matched)):
            effective_prompt += (
                f"\n\n【{zone_title} 睡前故事与陪伴参考资料】：\n{docs_text}\n"
                f"【长篇睡前故事与声音陪伴规范】：\n"
                f"1. 当前处于讲故事与睡前陪伴场景！请以充满爱心、温柔甜美、娓娓道来的幼教老师口吻展开讲述。\n"
                f"2. 结合上述故事素材，讲述一个生动完整、意境优美、画面感丰富的睡前童话（描绘安静美好的夜色、可爱的小动物入睡过程等），篇幅充实详尽（建议300-500字），提供充足舒适的声音陪伴时长。\n"
                f"3. 故事结尾请送上温馨甜美的晚安入睡祝福。\n"
                f"4. 绝不敷衍截断，严禁输出任何Markdown标记、星号（*或**）、井号（#）或小标题，直接输出适合语音播报的纯口语故事文本！"
            )
        elif is_preschool_role:
            effective_prompt += (
                f"\n\n【{zone_title} 幼教百科参考资料】：\n{docs_text}\n"
                f"【幼教教学回答规范】：请以温柔可亲的幼教老师口吻，结合参考资料用童趣易懂的语言解答，篇幅2-4句话生动解答，鼓励孩子的好奇心。严禁输出任何星号（*或**）符号，直接输出纯文本口语！"
            )
        else:
            effective_prompt += (
                f"\n\n【{zone_title} 权威参考资料】：\n{docs_text}\n"
                f"【回答规范】：请严格保持【{role['name']}】的身份与语气，结合上述参考资料口语化解答，篇幅控制在2-3句话内直奔要点。严禁输出任何星号（*或**）或加粗符号，直接输出纯文本口语！"
            )
    else:
        # No RAG match
        if is_railway_role:
            effective_prompt += (
                f"\n\n【智慧导览解说提示】：当前提问在本地库中无完全对应的单条词条。请以中国·大安机车博览园导览员小铁的亲切身份，"
                f"运用中国铁路与机车历史常识通俗生动作答，并自然结合大安博览园现场的展项（三场两馆一线一平台、76台蒸汽机车群、记忆馆等）热情指引，切忌死板机械地推脱拒答！严禁输出任何星号（*或**）符号！"
            )
        elif is_story_intent or (is_preschool_role and any(k in user_text for k in ["睡", "故事", "陪"])):
            effective_prompt += (
                f"\n\n【长篇故事与睡前温暖陪伴指令】：\n"
                f"1. 小朋友正在请求听故事或睡前哄睡陪伴！请发挥丰富的想象力，讲述一个生动温暖、情节完整、充满童趣与安全感的温馨童话（如森林小动物、月亮星空或梦境探险）。\n"
                f"2. 语言请极尽温柔、语调舒缓自然，篇幅充实（建议300-500字左右），让温暖的声音长效陪伴孩子。\n"
                f"3. 故事结尾送上一句轻柔温暖的晚安祝福（例如祝宝贝做个香甜美梦）。\n"
                f"4. 绝不要用一两句话草率了事！严禁输出任何星号（*或**）、井号（#）或Markdown符号，直接输出纯文本口语！"
            )
        elif is_preschool_role:
            effective_prompt += (
                f"\n\n【幼教互动提示】：请以充满爱心、亲切温柔、启发式的幼教老师口吻与小朋友交流，用通俗生动的语言解答，篇幅控制在2-4句话内。严禁输出任何星号（*或**）符号，直接输出纯文本口语！"
            )
        else:
            effective_prompt += (
                f"\n\n【交互提示】：请严格遵循【{role['name']}】的人设与语气，自然亲切地与用户口语交流，篇幅控制在1-3句话内。严禁输出任何星号（*或**）符号，直接输出纯文本口语！"
            )

    return effective_prompt

# ----------------- Web Chat Simulator API -----------------

@app.post("/api/chat/simulate")
@app.post("/api/chat/stream")
async def chat_simulate(req: Request):
    data = await req.json()
    user_text = data.get("text", "").strip()
    if not user_text:
        return JSONResponse(status_code=400, content={"error": "消息内容不能为空"})

    role_id = data.get("role_id")
    role = None
    if role_id:
        for r in role_manager.get_roles():
            if r["id"] == role_id:
                role = r
                break
    if not role:
        role = role_manager.get_active_role()

    # Fast-Path for Close Video Command
    clean_text = user_text.strip().lower()
    is_close_video_cmd = (
        any(k in clean_text for k in [
            "关视频", "关闭视频", "关掉视频", "退出视频", "停止视频", "不要看视频", 
            "退出播放", "停止播放", "别放了", "不要放了", "关闭展映", "退出展映",
            "关了这个视频", "关闭这个视频", "关掉这个视频"
        ]) or
        ("关闭" in clean_text and "视频" in clean_text) or
        ("关" in clean_text and "视频" in clean_text)
    )
    if is_close_video_cmd:
        global current_active_video
        current_active_video = None
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, execute_pc_tool, "close_video", {})
        await broadcast_kiosk_event({"type": "close_video"})
        is_railway_role = (role.get("id") == "railway_guide" or "小铁" in role.get("name", "") or "博览园" in role.get("name", ""))
        reply_text = "好的，已为您关闭展映，继续为您导览大安机车博览园！" if is_railway_role else "好的，已为您关闭播放！"
        await broadcast_kiosk_event({
            "type": "ai_done",
            "user_text": user_text,
            "assistant_reply": reply_text,
            "rag": []
        })
        log_entry = {
            "type": "conversation",
            "device": "网页控制台仿真",
            "role_name": role["name"],
            "user_text": user_text,
            "assistant_reply": reply_text,
            "executed_tools": [{"tool": "close_video", "args": {}, "result": {"status": "success"}}],
            "asr_ms": 0.0,
            "rag_ms": 0.0,
            "rag_matched": [],
            "ttft_ms": 5.0,
            "total_ms": 10.0,
            "audio_seconds": 0.0
        }
        add_log(log_entry)
        return {
            "user_text": user_text,
            "assistant_reply": reply_text,
            "role": role,
            "rag_matched": [],
            "executed_tools": [{"tool": "close_video", "args": {}, "result": {"status": "success"}}],
            "metrics": {"rag_ms": 0.0, "ttft_ms": 5.0, "total_ms": 10.0}
        }

    # 1. RAG search if enabled with precise Zone isolation & story intent detection
    rag_matched = []
    rag_ms = 0.0
    story_keywords = ["故事", "睡前", "哄睡", "童话", "晚安", "睡觉", "睡不着", "摇篮", "寓言", "讲个", "讲一篇", "陪伴"]
    is_story_intent = any(k in user_text for k in story_keywords)

    if role.get("rag_enabled", False):
        t0 = time.time()
        target_zone_id = role.get("zone_id") or zone_manager.active_zone_id
        top_k = max(role.get("rag_top_k", 2), 3) if is_story_intent else role.get("rag_top_k", 2)
        rag_matched = knowledge_store.search(user_text, top_k=top_k, zone_id=target_zone_id)
        rag_ms = (time.time() - t0) * 1000.0

    effective_prompt = build_effective_prompt(role, user_text, rag_matched)
    effective_temp = 0.70 if is_story_intent else role.get("temperature", config.temperature)
    is_railway_role = (role.get("id") == "railway_guide" or "小铁" in role.get("name", "") or "博览园" in role.get("name", ""))

    # 2. LLM Stream with PC Agent Tools
    t_start = time.time()
    llm = RelayLLMClient()
    assistant_reply = ""
    ttft_ms = 0.0
    executed_tools = []

    base_tools = list(PC_TOOLS_DEFINITIONS)
    if not is_railway_role and not any(k in user_text for k in ["视频", "影片", "短片", "大屏"]):
        base_tools = [t for t in base_tools if t.get("name") != "play_video"]
    active_tools = filter_tools_for_query(user_text, base_tools)
    async for token, tool_call, metrics in llm.stream_chat(
        user_text,
        device_tools=active_tools,
        system_prompt=effective_prompt,
        temperature=role.get("temperature", config.temperature)
    ):
        if metrics.get("ttft_ms") and ttft_ms == 0.0:
            ttft_ms = metrics["ttft_ms"]
        if token:
            assistant_reply += token
            await broadcast_kiosk_event({
                "type": "ai_stream",
                "token": token,
                "full_text": assistant_reply,
                "rag": rag_matched
            })
        if tool_call:
            tool_name = tool_call.get("name")
            tool_args = tool_call.get("arguments", {})
            print(f"[Console Tool Call] Invoking: {tool_name} with {tool_args}")
            loop = asyncio.get_event_loop()
            tool_result = await loop.run_in_executor(None, execute_pc_tool, tool_name, tool_args)
            if tool_name == "close_video" or "close" in tool_name:
                current_active_video = None
                await broadcast_kiosk_event({"type": "close_video"})
            elif tool_name == "play_video" or ("video" in tool_name and "close" not in tool_name) or (tool_result.get("video_id") and tool_name != "close_video"):
                if tool_result.get("status") == "success" and tool_result.get("video_id"):
                    current_active_video = tool_result
                    await broadcast_kiosk_event({
                        "type": "play_video",
                        "video_id": tool_result.get("video_id"),
                        "title": tool_result.get("title")
                    })
            executed_tools.append({"tool": tool_name, "args": tool_args, "result": tool_result})
            if not assistant_reply.strip():
                assistant_reply = tool_result.get("message", f"已成功执行操作: {tool_name}")

    total_ms = (time.time() - t_start) * 1000.0
    assistant_reply = clean_speech_text(assistant_reply)

    await broadcast_kiosk_event({
        "type": "ai_done",
        "user_text": user_text,
        "assistant_reply": assistant_reply,
        "rag": rag_matched
    })

    log_entry = {
        "type": "conversation",
        "device": "网页控制台仿真",
        "role_name": role["name"],
        "user_text": user_text,
        "assistant_reply": assistant_reply,
        "executed_tools": executed_tools,
        "asr_ms": 0.0,
        "rag_ms": round(rag_ms, 1),
        "rag_matched": rag_matched,
        "ttft_ms": round(ttft_ms, 1),
        "total_ms": round(total_ms, 1),
        "audio_seconds": 0.0
    }
    add_log(log_entry)

    return {
        "user_text": user_text,
        "assistant_reply": assistant_reply,
        "role": role,
        "rag_matched": rag_matched,
        "executed_tools": executed_tools,
        "metrics": {
            "rag_ms": round(rag_ms, 1),
            "ttft_ms": round(ttft_ms, 1),
            "total_ms": round(total_ms, 1)
        }
    }

@app.post("/api/device/control")
async def control_device(req: Request):
    data = await req.json()
    device_id = data.get("device_id")
    action = data.get("action")
    val = data.get("value")

    dev = active_devices.get(device_id)
    if not dev:
        dev = {
            "device_id": device_id,
            "client_id": "Xiaozhi-Client",
            "ip": "10.90.169.42",
            "connected_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "last_active": time.strftime("%H:%M:%S"),
            "status": "standby",
            "ws": None,
            "tools": [
                {"name": "self.audio_speaker.set_volume", "description": "调节喇叭音量"},
                {"name": "self.screen.set_brightness", "description": "调节屏幕背光"},
                {"name": "self.screen.set_theme", "description": "切换主题"},
                {"name": "self.reboot", "description": "重启设备"}
            ]
        }
        active_devices[device_id] = dev

    if "settings" not in dev:
        dev["settings"] = {}
    dev["settings"][action] = val

    ws: Optional[WebSocket] = dev.get("ws")
    if ws:
        def_mcp = lambda name, args: {
            "type": "mcp",
            "payload": {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": name, "arguments": args}
            }
        }
        if action == "volume":
            val_int = max(0, min(100, int(val)))
            dev["volume"] = val_int
            await ws.send_text(json.dumps(def_mcp("self.audio_speaker.set_volume", {"volume": val_int})))
            print(f"[Device Control] Web UI set volume to {val_int}% for {device_id}")
        elif action == "brightness":
            await ws.send_text(json.dumps(def_mcp("self.screen.set_brightness", {"brightness": int(val)})))
        elif action == "theme":
            await ws.send_text(json.dumps(def_mcp("self.screen.set_theme", {"theme": str(val)})))
        elif action == "reboot":
            await ws.send_text(json.dumps(def_mcp("self.reboot", {})))
        return {"status": "ok", "mode": "immediate", "message": "指令已下发至硬件并即时生效"}
    else:
        # Save pending commands when device is in Standby mode
        if "pending_commands" not in dev:
            dev["pending_commands"] = []
        dev["pending_commands"].append({"action": action, "value": val})
        return {
            "status": "queued",
            "mode": "queued",
            "message": f"硬件目前处于低功耗待机中，{action} 设置已暂存，将在下次语音唤醒时自动生效"
        }

@app.get("/api/devices")
async def get_devices():
    """Returns list of connected and registered devices for Web Console."""
    result = []
    for mac, dev in active_devices.items():
        dev_copy = dict(dev)
        if "ws" in dev_copy:
            dev_copy["ws"] = True if dev_copy["ws"] is not None else False
        result.append(dev_copy)
    return result

# ----------------- OTA Server Endpoint -----------------

@app.api_route("/ota/", methods=["GET", "POST"])
@app.api_route("/ota", methods=["GET", "POST"])
@app.api_route("/api/ota", methods=["GET", "POST"])
async def ota_endpoint(req: Request):
    """
    Xiaozhi OTA check endpoint.
    Directs the board to connect via WebSocket to our custom gateway instead of MQTT.
    """
    client_host = req.headers.get("host", f"10.90.169.206:{config.port}")
    host_only = client_host.split(":")[0]
    ws_url = f"ws://{host_only}:{config.port}/xiaozhi/v1/"
    client_ip = req.client.host if req.client else "unknown"
    device_mac = req.headers.get("device-id") or "14:c1:9f:cb:63:88"

    print(f"[OTA] Device queried OTA from {client_ip} (MAC: {device_mac}). Returning ws_url: {ws_url}")

    active_devices[device_mac] = {
        "device_id": device_mac,
        "client_id": req.headers.get("client-id", "Xiaozhi-Client"),
        "ip": client_ip,
        "connected_at": active_devices.get(device_mac, {}).get("connected_at") or time.strftime("%Y-%m-%d %H:%M:%S"),
        "last_active": time.strftime("%H:%M:%S"),
        "status": "online",
        "ws": None,
        "tools": [
            {"name": "self.audio_speaker.set_volume", "description": "调节喇叭音量"},
            {"name": "self.screen.set_brightness", "description": "调节屏幕背光"},
            {"name": "self.screen.set_theme", "description": "切换主题"},
            {"name": "self.reboot", "description": "重启设备"}
        ]
    }

    return {
        "server_time": {
            "timestamp": int(time.time() * 1000),
            "timezone_offset": 480
        },
        "websocket": {
            "url": ws_url,
            "version": 1,
            "token": "test-token"
        }
    }

# ----------------- WebSocket for Xiaozhi Hardware -----------------

@app.websocket("/xiaozhi/v1/")
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    headers = dict(websocket.headers)
    device_mac = headers.get("device-id", "Unknown-MAC")
    client_id = headers.get("client-id", "Unknown-Client")
    client_ip = websocket.client.host if websocket.client else "unknown"

    device_info = {
        "device_id": device_mac,
        "client_id": client_id,
        "ip": client_ip,
        "connected_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "last_active": time.strftime("%H:%M:%S"),
        "ws": websocket,
        "volume": 70,
        "tools": []
    }
    active_devices[device_mac] = device_info
    print(f"[WS] Device connected: {device_mac} from {client_ip}")

    decoder = OpusDecoderWrapper(sample_rate=16000, channels=1)
    tts_streamer = EdgeTTSStreamer()
    asr = get_asr_engine()
    llm = RelayLLMClient()
    vad = EnergyVAD()
    abort_event = asyncio.Event()

    session_id = f"sess-{int(time.time())}"
    is_tts_playing = False
    speech_task = None
    audio_buffer = []

    def make_mcp_call(tool_name: str, tool_args: dict, call_id: int = 1) -> dict:
        return {
            "session_id": session_id,
            "type": "mcp",
            "payload": {
                "jsonrpc": "2.0",
                "id": call_id,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": tool_args
                }
            }
        }

    async def process_user_speech(frames):
        global current_active_video
        nonlocal is_tts_playing
        if not frames:
            return

        pcm_all = np.concatenate(frames)
        if len(pcm_all) < 2400:  # < 150ms
            return

        abort_event.clear()
        t_start = time.time()
        # 1. ASR
        user_text, asr_cost_ms = asr.transcribe(pcm_all)
        if not user_text:
            return

        # Filter out noise frames (e.g. single dots '.', commas, pure punctuation or breath)
        import re
        pure_speech = re.sub(r'[\s。，、？！?!.,\-_~`]', '', user_text)
        if not pure_speech:
            print(f"[ASR] Discarded noise/dot utterance: '{user_text}'")
            return

        print(f"[ASR] User said ({asr_cost_ms:.1f}ms): {user_text}")
        is_tts_playing = True

        # Broadcast visitor speech to kiosk screen IMMEDIATELY (0ms delay)
        await broadcast_kiosk_event({
            "type": "user_text",
            "text": user_text
        })

        # Fast-Path for Close Video Command (Instant hardware responsiveness)
        clean_text = user_text.strip().lower()
        is_close_video_cmd = (
            any(k in clean_text for k in [
                "关视频", "关闭视频", "关掉视频", "退出视频", "停止视频", "不要看视频", 
                "退出播放", "停止播放", "别放了", "不要放了", "关闭展映", "退出展映", 
                "关了这个视频", "关闭这个视频", "关掉这个视频"
            ]) or
            ("关闭" in clean_text and "视频" in clean_text) or
            ("关" in clean_text and "视频" in clean_text)
        )
        active_role = role_manager.get_active_role()
        is_railway_role = (active_role.get("id") == "railway_guide" or "小铁" in active_role.get("name", "") or "博览园" in active_role.get("name", ""))

        if is_close_video_cmd:
            print(f"[FastPath] Immediate close video triggered by user command: '{user_text}'")
            current_active_video = None
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, execute_pc_tool, "close_video", {})
            await broadcast_kiosk_event({"type": "close_video"})
            reply_text = "好的，已为您关闭展映，继续为您导览大安机车博览园！" if is_railway_role else "好的，已为您关闭播放！"
            await broadcast_kiosk_event({
                "type": "ai_done",
                "user_text": user_text,
                "assistant_reply": reply_text,
                "rag": []
            })
            effective_voice = active_role.get("voice", config.tts_voice)
            await websocket.send_text(json.dumps({"session_id": session_id, "type": "stt", "text": user_text}))
            await websocket.send_text(json.dumps({"session_id": session_id, "type": "tts", "state": "start"}))
            await websocket.send_text(json.dumps({"session_id": session_id, "type": "tts", "state": "sentence_start", "text": reply_text}))
            async for opus_frame, is_last in tts_streamer.text_to_opus_stream(reply_text, voice=effective_voice):
                await websocket.send_bytes(opus_frame)
            await websocket.send_text(json.dumps({"session_id": session_id, "type": "tts", "state": "stop"}))
            add_log({
                "type": "conversation",
                "device": device_mac,
                "role_name": active_role["name"],
                "user_text": user_text,
                "assistant_reply": reply_text,
                "asr_ms": round(asr_cost_ms, 1),
                "rag_ms": 0.0,
                "rag_matched": [],
                "ttft_ms": 5.0,
                "total_ms": round((time.time() - t_start) * 1000.0, 1),
            })
            return

        try:
            # Notify display with recognized text
            await websocket.send_text(json.dumps({"session_id": session_id, "type": "stt", "text": user_text}))
            await websocket.send_text(json.dumps({"session_id": session_id, "type": "tts", "state": "start"}))

            # Check active persona/role
            effective_voice = active_role.get("voice", config.tts_voice)
            story_keywords = ["故事", "睡前", "哄睡", "童话", "晚安", "睡觉", "睡不着", "摇篮", "寓言", "讲个", "讲一篇", "陪伴"]
            is_story_intent = any(k in user_text for k in story_keywords)
            effective_temp = 0.70 if is_story_intent else active_role.get("temperature", config.temperature)

            # 2. Knowledge Base (RAG) Lookup with strict Zone physical isolation
            rag_matched = []
            rag_ms = 0.0
            if active_role.get("rag_enabled", False):
                t_rag_start = time.time()
                target_zone_id = active_role.get("zone_id") or zone_manager.active_zone_id
                top_k = max(active_role.get("rag_top_k", 2), 3) if is_story_intent else active_role.get("rag_top_k", 2)
                rag_matched = knowledge_store.search(
                    user_text,
                    top_k=top_k,
                    zone_id=target_zone_id,
                    history=llm.history
                )
                rag_ms = (time.time() - t_rag_start) * 1000.0
                if rag_matched:
                    print(f"[RAG] Hybrid retrieved {len(rag_matched)} relevant chunks ({rag_ms:.1f}ms) in zone '{target_zone_id}'")

            effective_prompt = build_effective_prompt(active_role, user_text, rag_matched)

            # 3. Combine ESP32 hardware tools and PC Agent tools with strict Intent Gating
            base_tools = list(PC_TOOLS_DEFINITIONS)
            if not is_railway_role and not any(k in user_text for k in ["视频", "影片", "短片", "大屏"]):
                base_tools = [t for t in base_tools if t.get("name") != "play_video"]
            if device_info.get("tools"):
                base_tools.extend(device_info["tools"])
            all_tools = filter_tools_for_query(user_text, base_tools)

            # 4. LLM + Streaming TTS + Tool Execution
            stream_buffer = ""
            full_assistant_reply = ""
            t_llm_start = time.time()
            ttft_ms = 0.0

            async for token, tool_call, metrics in llm.stream_chat(
                user_text,
                device_tools=all_tools,
                system_prompt=effective_prompt,
                temperature=effective_temp
            ):
                if abort_event.is_set():
                    print(f"[WS] TTS aborted due to user interruption: {device_mac}")
                    break

                if metrics.get("ttft_ms"):
                    ttft_ms = metrics["ttft_ms"]

                if token:
                    stream_buffer += token
                    full_assistant_reply += token
                    await broadcast_kiosk_event({
                        "type": "ai_stream",
                        "token": token,
                        "full_text": full_assistant_reply,
                        "rag": rag_matched
                    })

                    sentences, remainder = split_sentences(stream_buffer)
                    if sentences:
                        stream_buffer = remainder
                        frame_index = 0
                        for sent in sentences:
                            clean_sent = clean_speech_text(sent)
                            if not clean_sent:
                                continue
                            if abort_event.is_set():
                                break
                            await websocket.send_text(json.dumps({"session_id": session_id, "type": "tts", "state": "sentence_start", "text": clean_sent}))
                            async for opus_frame, is_last in tts_streamer.text_to_opus_stream(clean_sent, voice=effective_voice):
                                if abort_event.is_set():
                                    break
                                await websocket.send_bytes(opus_frame)
                                frame_index += 1
                                if frame_index > 3:
                                    await asyncio.sleep(0.052)

                if tool_call:
                    tool_name = tool_call.get("name")
                    tool_args = tool_call.get("arguments", {})
                    print(f"[Tool Call] Invoking: {tool_name} with {tool_args}")

                    # 1. Volume Control (Hardware Speaker + Optional PC Volume)
                    is_volume_tool = (
                        tool_name in ["set_volume", "set_speaker_volume", "self.audio_speaker.set_volume"] or
                        ("volume" in tool_name.lower()) or
                        (tool_name == "system_control" and any(k in str(tool_args).lower() for k in ["vol", "mute", "音量", "声音"]))
                    )

                    if is_volume_tool:
                        current_vol = device_info.get("volume", 70)
                        act = str(tool_args.get("action", "")).lower()
                        vol_val = tool_args.get("volume")

                        if vol_val is not None:
                            try:
                                target_vol = max(0, min(100, int(vol_val)))
                            except (ValueError, TypeError):
                                target_vol = current_vol
                        elif "down" in act or "小" in act:
                            target_vol = max(0, current_vol - 20)
                        elif "mute" in act or "静音" in act:
                            target_vol = 0
                        elif "up" in act or "大" in act:
                            target_vol = min(100, current_vol + 20)
                        else:
                            target_vol = min(100, current_vol + 20)

                        device_info["volume"] = target_vol

                        # Send hardware MCP command to Xiaozhi ESP32 speaker
                        mcp_cmd = {
                            "session_id": session_id,
                            "type": "mcp",
                            "payload": {
                                "jsonrpc": "2.0",
                                "id": 1,
                                "method": "tools/call",
                                "params": {
                                    "name": "self.audio_speaker.set_volume",
                                    "arguments": {
                                        "volume": target_vol
                                    }
                                }
                            }
                        }
                        await websocket.send_text(json.dumps(mcp_cmd))
                        print(f"[Volume Control] Set hardware speaker volume to {target_vol}% for {device_mac}")

                        # If user also mentioned PC / 电脑, adjust Windows volume too
                        if "电脑" in user_text:
                            from gateway.agent.pc_tools import adjust_windows_volume
                            adjust_windows_volume("up" if target_vol > current_vol else ("down" if target_vol < current_vol else "mute"))

                        if target_vol == 0:
                            reply_text = "好的，已为您开启静音。"
                        else:
                            reply_text = f"好的，已为您将喇叭音量调整为 {target_vol}%。"

                        full_assistant_reply = reply_text
                        await websocket.send_text(json.dumps({"session_id": session_id, "type": "tts", "state": "sentence_start", "text": reply_text}))
                        async for opus_frame, is_last in tts_streamer.text_to_opus_stream(reply_text, voice=effective_voice):
                            if abort_event.is_set():
                                break
                            await websocket.send_bytes(opus_frame)
                            await asyncio.sleep(0.052)

                        add_log({
                            "type": "volume_control",
                            "device": device_mac,
                            "volume": target_vol,
                            "reply": reply_text
                        })

                    # 2. PC Agent Tools — run in thread pool
                    elif tool_name in ["open_software", "play_video", "close_video", "system_control", "get_pc_status"] or any(k in tool_name.lower() for k in ["video", "open", "status", "system"]):
                        loop = asyncio.get_event_loop()
                        result = await loop.run_in_executor(None, execute_pc_tool, tool_name, tool_args)
                        if tool_name == "close_video" or "close" in tool_name:
                            current_active_video = None
                            await broadcast_kiosk_event({"type": "close_video"})
                        elif tool_name == "play_video" or ("video" in tool_name and "close" not in tool_name) or (result.get("video_id") and tool_name != "close_video"):
                            if result.get("status") == "success" and result.get("video_id"):
                                current_active_video = result
                                await broadcast_kiosk_event({
                                    "type": "play_video",
                                    "video_id": result.get("video_id"),
                                    "title": result.get("title")
                                })
                        add_log({
                            "type": "pc_tool",
                            "device": device_mac,
                            "tool": tool_name,
                            "args": tool_args,
                            "result": result
                        })
                        # If model didn't stream any voice text yet, provide verbal confirmation to the visitor
                        if not full_assistant_reply.strip():
                            reply_text = result.get("message", "好的，已为您执行操作。")
                            full_assistant_reply = reply_text
                            await websocket.send_text(json.dumps({"session_id": session_id, "type": "tts", "state": "sentence_start", "text": reply_text}))
                            async for opus_frame, is_last in tts_streamer.text_to_opus_stream(reply_text, voice=effective_voice):
                                if abort_event.is_set():
                                    break
                                await websocket.send_bytes(opus_frame)
                                await asyncio.sleep(0.052)
                    else:
                        # 3. ESP32 Hardware MCP Tools
                        mcp_cmd = make_mcp_call(tool_name, tool_args)
                        await websocket.send_text(json.dumps(mcp_cmd))
                        add_log({
                            "type": "mcp",
                            "device": device_mac,
                            "tool": tool_name,
                            "args": tool_args
                        })
                        if not full_assistant_reply.strip():
                            reply_text = "好的，已为您执行硬件控制。"
                            full_assistant_reply = reply_text
                            await websocket.send_text(json.dumps({"session_id": session_id, "type": "tts", "state": "sentence_start", "text": reply_text}))
                            async for opus_frame, is_last in tts_streamer.text_to_opus_stream(reply_text, voice=effective_voice):
                                if abort_event.is_set():
                                    break
                                await websocket.send_bytes(opus_frame)
                                await asyncio.sleep(0.052)

            # Process any remaining text in stream_buffer
            if not abort_event.is_set() and stream_buffer.strip():
                clean_sent = clean_speech_text(stream_buffer.strip())
                if clean_sent:
                    await websocket.send_text(json.dumps({"session_id": session_id, "type": "tts", "state": "sentence_start", "text": clean_sent}))
                    frame_index = 0
                    async for opus_frame, is_last in tts_streamer.text_to_opus_stream(clean_sent, voice=effective_voice):
                        if abort_event.is_set():
                            break
                        await websocket.send_bytes(opus_frame)
                        frame_index += 1
                        if frame_index > 3:
                            await asyncio.sleep(0.052)

            total_time_ms = (time.time() - t_start) * 1000.0

            # Synchronize spoken reply into LLM history for multi-turn dialogue
            if full_assistant_reply:
                if llm.history and llm.history[-1].get("role") == "assistant":
                    llm.history[-1]["content"] = full_assistant_reply
                else:
                    llm.add_message("assistant", full_assistant_reply)

            # Broadcast completion event to Kiosk
            await broadcast_kiosk_event({
                "type": "ai_done",
                "user_text": user_text,
                "assistant_reply": full_assistant_reply,
                "rag": rag_matched
            })

            # Log conversation to Web Console
            add_log({
                "type": "conversation",
                "device": device_mac,
                "role_name": active_role["name"],
                "user_text": user_text,
                "assistant_reply": full_assistant_reply,
                "asr_ms": round(asr_cost_ms, 1),
                "rag_ms": round(rag_ms, 1),
                "rag_matched": rag_matched,
                "ttft_ms": round(ttft_ms, 1),
                "total_ms": round(total_time_ms, 1),
                "audio_seconds": round(len(pcm_all) / 16000.0, 1)
            })

        except asyncio.CancelledError:
            print(f"[WS] Speech task cancelled for {device_mac}")
        except Exception as e:
            print(f"[WS] Error in process_user_speech: {e}")
        finally:
            if not abort_event.is_set():
                await websocket.send_text(json.dumps({"session_id": session_id, "type": "tts", "state": "stop"}))
            is_tts_playing = False
            vad.reset()

    try:
        while True:
            msg = await websocket.receive()
            device_info["last_active"] = time.strftime("%H:%M:%S")

            # Binary Opus audio frame from ESP32
            if "bytes" in msg and msg["bytes"]:
                # If TTS is actively playing to the ESP32, ignore mic audio (acoustic echo prevention)
                if is_tts_playing:
                    continue

                opus_data = msg["bytes"]
                pcm_chunk = decoder.decode(opus_data)
                if len(pcm_chunk) > 0:
                    audio_buffer.append(pcm_chunk)
                    _, speech_ended = vad.process_frame(pcm_chunk)

                    # Retain 8 rolling pre-buffer frames (480ms) to preserve soft consonants before speech onset
                    if not vad.speech_started and len(audio_buffer) > 8:
                        audio_buffer.pop(0)

                    if speech_ended and len(audio_buffer) > 0:
                        vad.reset()
                        frames_to_process = list(audio_buffer)
                        audio_buffer = []
                        if speech_task and not speech_task.done():
                            speech_task.cancel()
                        speech_task = asyncio.create_task(process_user_speech(frames_to_process))

            # Text JSON frame from ESP32
            elif "text" in msg and msg["text"]:
                try:
                    data = json.loads(msg["text"])
                    msg_type = data.get("type")

                    # Abort / Interruption from hardware
                    if msg_type == "abort":
                        reason = data.get("reason", "manual")
                        print(f"[WS] Abort received from {device_mac}: reason={reason}")
                        abort_event.set()
                        if speech_task and not speech_task.done():
                            speech_task.cancel()
                        await websocket.send_text(json.dumps({"session_id": session_id, "type": "tts", "state": "stop"}))
                        vad.reset()
                        audio_buffer = []
                        is_tts_playing = False

                    # Handshake hello
                    elif msg_type == "hello":
                        print(f"[WS] Received hello from {device_mac}: {data}")
                        hello_resp = {
                            "type": "hello",
                            "transport": "websocket",
                            "session_id": session_id,
                            "audio_params": {
                                "format": "opus",
                                "sample_rate": 24000,
                                "channels": 1,
                                "frame_duration": 60
                            }
                        }
                        await websocket.send_text(json.dumps(hello_resp))

                        # Dispatch any queued settings while device was in standby
                        pending = device_info.get("pending_commands", [])
                        while pending:
                            item = pending.pop(0)
                            act = item.get("action")
                            v = item.get("value")
                            print(f"[WS] Applying queued pending command: {act}={v}")
                            if act == "volume":
                                val_int = max(0, min(100, int(v)))
                                device_info["volume"] = val_int
                                await websocket.send_text(json.dumps(make_mcp_call("self.audio_speaker.set_volume", {"volume": val_int})))
                            elif act == "brightness":
                                await websocket.send_text(json.dumps(make_mcp_call("self.screen.set_brightness", {"brightness": int(v)})))
                            elif act == "theme":
                                await websocket.send_text(json.dumps(make_mcp_call("self.screen.set_theme", {"theme": str(v)})))

                    # MCP tool registration from ESP32
                    elif msg_type == "mcp" or "tools" in data:
                        tools = data.get("tools") or data.get("params", {}).get("tools", [])
                        if tools:
                            device_info["tools"] = tools
                            print(f"[WS] Device registered {len(tools)} MCP tools")

                    # Device listening state change
                    elif msg_type == "listen":
                        state = data.get("state")
                        if state == "start":
                            # Device has entered listening state
                            if is_tts_playing:
                                abort_event.set()
                                if speech_task and not speech_task.done():
                                    speech_task.cancel()
                                await websocket.send_text(json.dumps({"session_id": session_id, "type": "tts", "state": "stop"}))
                                is_tts_playing = False
                            vad.reset()
                            if len(audio_buffer) > 8:
                                audio_buffer = audio_buffer[-8:]
                        elif state == "stop":
                            # Push-to-talk button released
                            if len(audio_buffer) > 0:
                                vad.reset()
                                frames_to_process = list(audio_buffer)
                                audio_buffer = []
                                if speech_task and not speech_task.done():
                                    speech_task.cancel()
                                speech_task = asyncio.create_task(process_user_speech(frames_to_process))

                    # Device status report
                    elif msg_type == "status":
                        device_info.update(data)

                except Exception as e:
                    print(f"[WS] Error parsing JSON: {e}")

    except WebSocketDisconnect:
        print(f"[WS] Device disconnected from session: {device_mac}")
    except Exception as e:
        print(f"[WS] Error: {e}")
    finally:
        if speech_task and not speech_task.done():
            speech_task.cancel()
        if device_mac in active_devices:
            active_devices[device_mac]["ws"] = None
            active_devices[device_mac]["status"] = "standby"
            active_devices[device_mac]["last_active"] = time.strftime("%H:%M:%S")

# Mount Web Console static files
web_dir = Path(__file__).parent / "web"
app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="web")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config.host, port=config.port)
