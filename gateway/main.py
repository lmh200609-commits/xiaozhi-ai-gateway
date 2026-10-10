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
import re
import uuid
import urllib.parse
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, Response
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
from gateway.roles.skill_manager import skill_manager
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

async def broadcast_role_greeting_to_device(dev: dict, role: dict):
    """
    Sends an immediate TTS voice & display message to a connected ESP32 hardware device
    announcing the active role persona and greeting.
    """
    ws = dev.get("ws")
    if not ws:
        return

    lock = dev.get("tts_lock")
    if lock:
        try:
            await asyncio.wait_for(lock.acquire(), timeout=2.0)
        except (asyncio.TimeoutError, Exception):
            print(f"[WS Role Sync] Device {dev.get('device_id')} busy with TTS, skipping greeting broadcast")
            return

    try:
        session_id = dev.get("session_id") or f"sess-{int(time.time())}"
        role_name = role.get("name", "小智")
        greeting = role.get("greeting")
        if not greeting:
            if "招生" in role_name or "高校" in role_name:
                greeting = f"您好！已切换为：{role_name}。欢迎咨询高校专业建设与培养方案！"
            elif "导览" in role_name or "小铁" in role_name:
                greeting = f"游客朋友好！已切换为：{role_name}，很高兴为您解说！"
            elif "心理" in role_name:
                greeting = f"您好，我是心语老师。生活里有什么想聊聊的，我都在这里陪伴您。"
            elif "幼教" in role_name:
                greeting = f"小朋友你好呀！我是小智老师，今天想听什么好听的故事呢？"
            else:
                greeting = f"您好！已为您切换为人设：{role_name}。"

        voice = role.get("voice", config.tts_voice)
        tts_streamer = EdgeTTSStreamer()
        await ws.send_text(json.dumps({"session_id": session_id, "type": "tts", "state": "start"}))
        await ws.send_text(json.dumps({"session_id": session_id, "type": "tts", "state": "sentence_start", "text": greeting}))

        frame_count = 0
        async for opus_frame, is_last in tts_streamer.text_to_opus_stream(greeting, voice=voice):
            await ws.send_bytes(opus_frame)
            frame_count += 1
            if frame_count > 3:
                await asyncio.sleep(0.045)

        await ws.send_text(json.dumps({"session_id": session_id, "type": "tts", "state": "stop"}))
        print(f"[WS Role Sync] Pushed role greeting to device {dev.get('device_id')}: '{greeting}' (voice: {voice})")
    except Exception as e:
        print(f"[WS Role Sync] Failed to send role greeting to device {dev.get('device_id')}: {e}")
    finally:
        if lock and lock.locked():
            lock.release()

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
        
        # 1. Reset stage tracking for all sessions so new role starts at Stage 1
        session_skill_tracker.clear()

        # 2. Broadcast role switch to Kiosk
        await broadcast_kiosk_event({
            "type": "role_switch",
            "role": active
        })

        # 3. Synchronize connected hardware devices: reset conversation history & push role greeting
        for mac, dev in active_devices.items():
            if dev.get("ws") is not None:
                if "llm" in dev and dev["llm"] is not None:
                    dev["llm"].reset_history()
                asyncio.create_task(broadcast_role_greeting_to_device(dev, active))

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

# ----------------- Agent Skills (技能库与文件管理) API -----------------

@app.get("/api/skills")
async def list_skills():
    """获取技能仓库中所有已安装/上传的 Skill 列表"""
    return {
        "status": "ok",
        "skills": skill_manager.list_skills()
    }

@app.post("/api/skills/upload")
async def upload_skill_file(file: UploadFile = File(...)):
    """上传任意 Agent Skill 文件 (.md, .skill.md, .json) 到技能库"""
    try:
        content = await file.read()
        parsed = skill_manager.import_skill_file(file.filename, content)
        return {
            "status": "ok",
            "skill": parsed,
            "filename": parsed.get("filename")
        }
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": f"解析 Skill 文件失败: {str(e)}"})

@app.get("/api/skills/{filename}/download")
async def download_skill_file(filename: str):
    """下载特定 Skill 文件"""
    content = skill_manager.get_skill_content(filename)
    if content is None:
        return JSONResponse(status_code=404, content={"error": "Skill 文件不存在"})
    encoded_name = urllib.parse.quote(filename.encode("utf-8"))
    return Response(
        content=content.encode("utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"}
    )

@app.delete("/api/skills/{filename}")
async def delete_skill_file(filename: str):
    """从技能库中删除指定 Skill 文件"""
    success = skill_manager.delete_skill(filename)
    if success:
        return {"status": "ok"}
    return JSONResponse(status_code=404, content={"error": "文件不存在"})

@app.post("/api/roles/{role_id}/skill/upload")
async def upload_skill_to_role(role_id: str, file: UploadFile = File(...)):
    """直接为指定角色上传并挂载 Skill 文件"""
    try:
        content = await file.read()
        parsed = skill_manager.import_skill_file(file.filename, content)
        role = role_manager.update_role(role_id, {"skill": parsed})
        if not role:
            return JSONResponse(status_code=404, content={"error": "角色不存在"})
        return {"status": "ok", "role": role, "skill": parsed}
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": f"上传并挂载 Skill 失败: {str(e)}"})

@app.post("/api/roles/{role_id}/skill/bind")
async def bind_skill_to_role(role_id: str, req: Request):
    """从技能库选择已有 Skill 文件挂载到角色"""
    data = await req.json()
    filename = data.get("filename")
    if not filename:
        return JSONResponse(status_code=400, content={"error": "缺少 filename 参数"})
    content = skill_manager.get_skill_content(filename)
    if content is None:
        return JSONResponse(status_code=404, content={"error": "指定的 Skill 文件不存在"})
    if filename.endswith(".json"):
        parsed = skill_manager.parse_json(content, filename=filename)
    else:
        parsed = skill_manager.parse_markdown(content, filename=filename)
    role = role_manager.update_role(role_id, {"skill": parsed})
    if not role:
        return JSONResponse(status_code=404, content={"error": "角色不存在"})
    return {"status": "ok", "role": role, "skill": parsed}

@app.delete("/api/roles/{role_id}/skill")
async def unbind_skill_from_role(role_id: str):
    """卸载角色的 Skill 技能"""
    role = role_manager.update_role(role_id, {"skill": None})
    if not role:
        return JSONResponse(status_code=404, content={"error": "角色不存在"})
    return {"status": "ok", "role": role}

@app.get("/api/roles/{role_id}/skill/export")
async def export_role_skill(role_id: str):
    """导出角色当前绑定的 Skill 为 Markdown 文件"""
    target = None
    for r in role_manager.get_roles():
        if r["id"] == role_id:
            target = r
            break
    if not target or not target.get("skill"):
        return JSONResponse(status_code=404, content={"error": "该角色未挂载任何 Skill"})
    skill_data = target["skill"]
    md = skill_manager.export_to_markdown(skill_data)
    safe_name = f"{target.get('id', 'role')}_skill.md"
    encoded_name = urllib.parse.quote(safe_name.encode("utf-8"))
    return Response(
        content=md.encode("utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"}
    )

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

# ----------------- Knowledge Base (RAG) & File Management API -----------------

DOCUMENTS_DIR = Path(__file__).resolve().parent / "data" / "documents"
DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)

@app.get("/api/knowledge")
@app.get("/api/documents")
async def get_knowledge(zone_id: Optional[str] = None):
    return {"documents": knowledge_store.list_documents(zone_id=zone_id)}

@app.get("/api/knowledge/chunks")
@app.get("/api/documents/chunks")
async def get_knowledge_chunks(
    zone_id: Optional[str] = None,
    doc_id: Optional[str] = None,
    limit: int = 200
):
    chunks = knowledge_store.list_chunks(zone_id=zone_id, doc_id=doc_id, limit=limit)
    return {"status": "ok", "chunks": chunks, "count": len(chunks)}

@app.get("/api/knowledge/{doc_id}")
@app.get("/api/documents/{doc_id}")
async def get_knowledge_doc(doc_id: str):
    doc = knowledge_store.get_document_details(doc_id)
    if not doc:
        return JSONResponse(status_code=404, content={"error": "文档不存在"})
    return {"document": doc}

@app.get("/api/documents/{doc_id}/download")
@app.get("/api/knowledge/{doc_id}/download")
async def download_knowledge_file(doc_id: str):
    doc = knowledge_store.get_document_details(doc_id)
    if not doc:
        return JSONResponse(status_code=404, content={"error": "文档不存在"})

    file_path = doc.get("file_path")
    filename = doc.get("file_name") or f"{doc.get('title', 'knowledge_doc')}.txt"

    # If physical file exists on disk, send it directly as attachment
    if file_path and Path(file_path).is_file():
        p = Path(file_path)
        encoded_name = urllib.parse.quote(filename.encode('utf-8'))
        headers = {
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"
        }
        return FileResponse(path=str(p), filename=filename, headers=headers)

    # Fallback for manual or preset document: dynamically stream as markdown file
    raw_content = doc.get("raw_content") or doc.get("summary") or doc.get("title", "")
    md_filename = f"{doc.get('title', 'document')}.md"
    encoded_name = urllib.parse.quote(md_filename.encode('utf-8'))
    return Response(
        content=raw_content.encode("utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"}
    )

@app.post("/api/knowledge/upload")
async def upload_knowledge_file(
    file: UploadFile = File(...),
    zone_id: Optional[str] = Form(None)
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

        target_zone = (zone_manager.get_zone(zone_id) if zone_id else None) or zone_manager.get_active_zone()
        zone_name = target_zone.get("name", "默认通用知识区")

        # Save physical archive file safely
        zone_folder = DOCUMENTS_DIR / target_zone["id"]
        zone_folder.mkdir(parents=True, exist_ok=True)

        doc_id = str(uuid.uuid4())
        ext = Path(filename).suffix
        safe_stem = re.sub(r'[\\/*?:"<>|]', "_", Path(filename).stem)[:64]
        safe_file_name = f"{doc_id}_{safe_stem}{ext}"
        saved_file_path = zone_folder / safe_file_name
        saved_file_path.write_bytes(content_bytes)
        file_size = len(content_bytes)

        print(f"[RAG Upload] Saved physical archive: {saved_file_path} ({file_size} bytes)")
        print(f"[RAG Upload] Starting document structuring for: {filename} in zone: {zone_name}...")
        try:
            structured_data = await KnowledgeStructurer.structure_document(filename, raw_text)
        except Exception as ex_struct:
            print(f"[RAG Upload] Structuring exception: {ex_struct}, falling back to local semantic chunker")
            structured_data = KnowledgeStructurer.build_local_structured_data(filename, raw_text)
            structured_data["warning"] = f"解析过程发生异常 ({str(ex_struct)})，已自动启用本地高精切片引擎为您完成入库。"

        doc_id = knowledge_store.add_structured_document(
            doc_data=structured_data,
            raw_text=raw_text,
            file_name=filename,
            file_type=parsed["file_type"],
            zone_id=target_zone["id"],
            zone_name=zone_name,
            doc_id=doc_id,
            file_size=file_size,
            file_path=str(saved_file_path)
        )
        return {
            "status": "ok",
            "doc_id": doc_id,
            "title": structured_data.get("title", filename),
            "file_name": filename,
            "file_size": file_size,
            "has_physical_file": True,
            "download_url": f"/api/documents/{doc_id}/download",
            "category": structured_data.get("category", "通用"),
            "summary": structured_data.get("summary", ""),
            "zone_id": target_zone["id"],
            "zone_name": zone_name,
            "qa_count": len(structured_data.get("qa_pairs", [])),
            "fact_count": len(structured_data.get("fact_chunks", [])),
            "mode": structured_data.get("mode", "local_semantic"),
            "model": structured_data.get("model", config.model_name),
            "warning": structured_data.get("warning", "")
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
        zone_name=target_zone.get("name", "默认通用知识区")
    )
    return {"status": "ok", "doc_id": doc_id}

@app.delete("/api/knowledge/{doc_id}")
@app.delete("/api/documents/{doc_id}")
async def delete_knowledge(doc_id: str):
    knowledge_store.delete_document(doc_id)
    return {"status": "ok"}

@app.post("/api/knowledge/search")
async def search_knowledge(req: Request):
    data = await req.json()
    query = data.get("query", "").strip()
    top_k = int(data.get("top_k", 3))
    min_score = float(data.get("min_score", 0.01))
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

session_skill_tracker = {}

def get_session_stage(session_id: str, role: dict, requested_stage_id: Optional[int] = None) -> Optional[dict]:
    skill = role.get("skill")
    if not skill or not isinstance(skill, dict) or not skill.get("enabled"):
        return None
    stages = skill.get("stages", [])
    if not stages:
        return None

    target_stage = None
    if requested_stage_id is not None:
        for s in stages:
            if s.get("stage_id") == requested_stage_id:
                target_stage = s
                break

    if not target_stage and session_id and session_id in session_skill_tracker:
        tracked = session_skill_tracker[session_id]
        if tracked.get("role_id") == role.get("id"):
            tid = tracked.get("stage_id")
            for s in stages:
                if s.get("stage_id") == tid:
                    target_stage = s
                    break

    if not target_stage:
        target_stage = stages[0]

    if session_id:
        session_skill_tracker[session_id] = {
            "role_id": role.get("id"),
            "stage_id": target_stage.get("stage_id", 1),
            "updated_at": time.time()
        }

    return target_stage

def is_identity_or_greeting_intent(user_text: str, role: dict) -> bool:
    """
    Determines if the user's input is a persona inquiry, role confirmation,
    greeting, ice-breaker, or general capability inquiry, as opposed to a domain factual question.
    """
    clean = re.sub(r'[^\w\s\u4e00-\u9fff]', '', user_text).strip().lower()
    if not clean:
        return False

    role_name = role.get("name", "").lower()
    role_desc = role.get("description", "").lower()

    # 1. Direct Greetings & Ice-breakers (short utterances)
    greeting_exact = {
        "你好", "您好", "你好啊", "你好呀", "嗨", "哈喽", "hello", "hi", "hey",
        "早上好", "上午好", "中午好", "下午好", "晚上好", "早安", "晚安",
        "在吗", "在不在", "有人吗", "听得到吗", "听到吗", "喂"
    }
    if clean in greeting_exact:
        return True

    # 2. Identity & Role Confirmation Patterns
    # "你不是...吗", "你是不是...", "你是...对吧", "你是谁", "你叫什么"
    identity_regexes = [
        r"^你不是.*(吗|吧|啊)?$",
        r"^你是不是.*(吗|吧|啊)?$",
        r"^你是.*(吗|吧|啊|呢|对吧|对不对)$",
        r"你是谁",
        r"你叫什么",
        r"怎么称呼",
        r"自我介绍",
        r"介绍(一下)?你(自己)?",
        r"介绍(一下)?你的身份",
        r"你的身份是",
        r"你是什么(身份|角色|顾问|人|导览员|老师|医生|管家|助手)",
        r"你(是|能)干(什么|嘛|啥)",
        r"你能做(什么|啥)",
        r"你有什么(功能|本领|作用)",
        r"你能帮我(做什么|干什么|啥)",
        r"怎么(向你)?咨询",
        r"我想咨询(一下)?$",
        r"咨询流程(是什么)?$",
        r"你可以帮我什么"
    ]
    for pattern in identity_regexes:
        if re.search(pattern, clean):
            return True

    # 3. Mentioning current role keywords in identity questions
    role_keywords = set()
    for token in ["招生", "高校", "专业建设", "顾问", "小铁", "博览园", "导览", "心理", "心语", "幼教", "智能管家", "星奈", "极客"]:
        if token in role_name or token in role_desc:
            role_keywords.add(token)

    if any(k in clean for k in role_keywords):
        if any(q in clean for q in ["你", "谁", "吗", "吧", "对吧", "对吗", "是不是", "做个介绍", "咨询"]):
            domain_fact_markers = ["介绍学校", "建设情况", "培养方案", "课程设置", "学费", "录取线", "分数线", "机车展项", "展品", "几点开门", "门票"]
            if not any(df in clean for df in domain_fact_markers):
                return True

    return False

def build_effective_prompt(role: dict, user_text: str, rag_matched: list, stage: Optional[dict] = None) -> str:
    """
    Builds the complete dynamic system prompt taking into account:
    - Active role persona & voice constraints
    - RAG Mode: 'exact' (verbatim reproduction without modification) vs 'smart' (AI synthesis & paraphrasing)
    - Persona & greeting intent recognition (preventing rigid RAG refusal on identity/greetings)
    - Role Skill: Multi-stage guided SOP workflows (psychologist, admissions advisor, etc.)
    - Bedtime accompaniment / storytelling mode
    - Strict prohibition of Markdown asterisks (* and **) for speech output
    """
    effective_prompt = role.get("system_prompt", config.system_prompt)
    rag_mode = role.get("rag_mode", "smart")
    is_identity_query = is_identity_or_greeting_intent(user_text, role)
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

    # 1. RAG Knowledge Injection Logic
    if rag_mode == "exact":
        if is_identity_query:
            # Identity confirmation, greeting, or conversational ice-breaker (Bypass blunt unhit refusal!)
            stage_hint = ""
            if stage and stage.get("instruction"):
                stage_hint = f"并遵循当前SOP阶段指引：{stage.get('instruction')}"
            effective_prompt += (
                f"\n\n=======================================================\n"
                f"【角色身份确认与开场引导交互指令】\n"
                f"1. 用户正在向你确认身份（例如询问你是否是招生顾问/导览员/专家）、打招呼或询问如何咨询。\n"
                f"2. 请务必以【{role['name']}】的官方专业身份，亲切、自然、自信地正面回应并确认自己的身份（例如：'是的，我是高校官方专业建设与招生咨询顾问...'）！\n"
                f"3. 绝对严禁输出任何拒答模板（绝对严禁输出'抱歉，知识库暂未收录'等话术）！绝对严禁声称自己只是普通AI或智能管家！\n"
                f"4. 请以极具亲和力的口吻向用户介绍自己的服务范围，{stage_hint}，主动且热情地引导用户开启第一步咨询探讨。\n"
                f"5. 输出要求：使用自然流畅口语，篇幅控制在2-3句话内直奔要点，严禁输出任何Markdown标记或星号（*或**）！\n"
                f"=======================================================\n"
            )
        elif rag_matched:
            # Strict Verbatim Mode: 100% faithful reproduction, zero self-expansion, zero web search
            docs_text = "\n\n".join([f"【官方权威档案记录 {i+1}】\n{c['content']}" for i, c in enumerate(rag_matched)])
            effective_prompt += (
                f"\n\n=======================================================\n"
                f"【最高优先级执行指令：官方权威档案忠实复述】\n"
                f"1. 针对用户提问，你必须 100% 完整、准确地复述下方官方权威档案内容！\n"
                f"2. 绝对严禁自行总结、精简、概括、改写句子或利用外部常识自主发挥！\n"
                f"3. 绝对严禁添加任何开场客套话或结尾套话（例如：'好的，为您介绍如下'、'希望对您有所帮助'等）！\n"
                f"4. 【严禁泄露内部设定与出戏】：绝对严禁对用户说出“需要我按官方原文复述”、“知识库收录的资料”、“内部设定”等话语，直接输出资料中的正文文字！\n"
                f"5. 严格格式：严禁输出任何Markdown星号(*或**)。\n"
                f"=======================================================\n\n"
                f"【官方权威档案内容】：\n{docs_text}\n"
            )
        else:
            effective_prompt += (
                f"\n\n=======================================================\n"
                f"【咨询未收录档案应答指令】\n"
                f"1. 针对用户当前咨询的主题/专业/高校，后台官方档案库中暂未收录相关资料。\n"
                f"2. 【严禁自相矛盾与左右互搏】：绝对严禁先答应介绍（例如绝对禁止说“好的，那我这就为你详细介绍...”、“我这就为你完整介绍...”），紧接着又说无法介绍！禁止出现前后矛盾的话语！\n"
                f"3. 【严禁泄露内部设定与出戏】：绝对严禁向用户说出任何“系统设定”、“内部设定”、“严格原文复述模式”、“需要按官方原文一字不差为你复述”、“知识库未检索到”、“怕误导你”等技术术语或规则解释！\n"
                f"4. 请用自然、真诚、沉稳的官方顾问口吻简短回应（1-2句话内），直接礼貌说明暂未掌握该专业的官方档案资料，并自然引导考生咨询其他专业或关注学校官方发布，例如：\n"
                f"   “抱歉同学，我手头目前暂未掌握该专业的官方建设方案与培养资料。您可以咨询我其他学科专业，或者关注学校招生网的最新发布哦。”\n"
                f"=======================================================\n"
            )
    else:
        # Smart Mode: AI synthesis, paraphrasing, conversational adaptation
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
            # No RAG match in Smart Mode
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

    # 2. Role Skill Multi-Stage SOP Workflow Injection
    skill = role.get("skill")
    if skill and isinstance(skill, dict) and skill.get("enabled"):
        stages = skill.get("stages", [])
        if stages:
            curr_stage = stage if stage else stages[0]
            stages_overview = "\n".join([
                f"  {idx+1}. 阶段 {s.get('stage_id', idx+1)}【{s.get('name', '')}】：目标: {s.get('goal', '')}（流转判定: {s.get('exit_condition', '')}）"
                for idx, s in enumerate(stages)
            ])
            skill_prompt = (
                f"\n\n=======================================================\n"
                f"【角色专属 Skill 引导式工作流：{skill.get('name', '多阶段SOP工作流')}】\n"
                f"【流程定位】：{skill.get('description', '')}\n"
                f"【完整SOP流程全景】：\n{stages_overview}\n\n"
                f"👉 【当前执行阶段】：阶段 {curr_stage.get('stage_id')} - 【{curr_stage.get('name')}】\n"
                f"🎯 【本阶段核心目标】：{curr_stage.get('goal')}\n"
                f"📝 【本阶段执行指令与策略】：{curr_stage.get('instruction')}\n"
                f"🔄 【进入下一阶段的流转判定】：{curr_stage.get('exit_condition')}\n"
                f"【SOP执行铁律】：\n"
                f"1. 你当前轮次的所有对话沟通、提问或解说，必须严格遵循【当前执行阶段】的目标与指令进行！\n"
                f"2. 严禁超前抢答后续阶段的内容，保持循序渐进的专业引导节奏。\n"
                f"3. 【严禁出戏与泄露SOP内部词汇】：绝对禁止向用户念出阶段名称（如“阶段一”、“严格原文”）、或者向用户解释“根据系统流程需要先了解您的意向”、“需要按官方原文复述”等技术性话术！你必须自然地融入对话，以专业角色身份引导。\n"
                f"4. 阶段流转指示：当您在对话中确认本阶段的核心目标与流转判定条件已达成、并向用户发出了承上启下的过渡语句时，请在回答正文最后附带标记 [NEXT_STAGE]（该标记系统会自动隐蔽处理，语音不会读出，用来通知系统将流程推入下一阶段）。若本阶段交流尚未充分或仍需进一步引导，切勿附带该标记。\n"
                f"=======================================================\n"
            )
            effective_prompt += skill_prompt

    # 3. Universal Voice, Display & Persona Immersion Guardrail
    effective_prompt += (
        "\n\n=======================================================\n"
        "【语音播报、屏幕显示与人设沉浸铁律 (Universal Guardrail)】\n"
        "1. 【严禁出戏与泄露系统内部设定】：绝对严禁向用户提及“知识库”、“系统设定”、“内部设定”、“严格原文复述模式”、“需要按官方原文一字不差为你复述”、“未检索到词条”、“怕误导你所以不能发挥”等任何底层技术概念或后台规则！你是一个真实、专业的官方顾问，切勿向用户解释运行机制！\n"
        "2. 【严禁前后矛盾与左右互搏】：若手头没有相关专业档案，直接礼貌说明暂未收录即可，绝对严禁前一句答应介绍（如“好的，那我这就为你详细介绍……”）、后一句又说没有资料不能介绍！\n"
        "3. 【绝对严禁Emoji表情】：严禁在回答中夹带任何 Emoji 表情符号（例如 👍, 😊, 🎉, 🎓, 🏫, 🤖, 🌸, 👏 等），避免语音引擎读出“拇指向上”“羞涩微笑”及硬件屏幕方块乱码！\n"
        "4. 【绝对严禁动作文字描写】：严禁在回答中夹带任何表情或动作文字描写（例如 [微笑]、[鼓掌]、（笑）、(点点头) 等括号注释）！\n"
        "5. 【纯中文口语输出】：回答必须全部使用流畅、纯净、自然的中文纯文本口语，篇幅控制在2-3句话内直奔要点。\n"
        "=======================================================\n"
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

    session_id = data.get("session_id", "web_simulator")
    requested_stage_id = data.get("stage_id")
    advance_stage = bool(data.get("advance_stage", False))

    current_stage = get_session_stage(session_id, role, requested_stage_id)
    skill_obj = role.get("skill")
    stages = skill_obj.get("stages", []) if (skill_obj and isinstance(skill_obj, dict) and skill_obj.get("enabled")) else []

    if advance_stage and current_stage and stages:
        curr_idx = -1
        for idx, s in enumerate(stages):
            if s.get("stage_id") == current_stage.get("stage_id"):
                curr_idx = idx
                break
        if curr_idx != -1 and curr_idx + 1 < len(stages):
            current_stage = stages[curr_idx + 1]
            session_skill_tracker[session_id] = {
                "role_id": role.get("id"),
                "stage_id": current_stage.get("stage_id"),
                "updated_at": time.time()
            }

    next_stage_id = None
    if current_stage and stages:
        curr_idx = -1
        for idx, s in enumerate(stages):
            if s.get("stage_id") == current_stage.get("stage_id"):
                curr_idx = idx
                break
        if curr_idx != -1 and curr_idx + 1 < len(stages):
            next_stage_id = stages[curr_idx + 1].get("stage_id")

    is_identity_query = is_identity_or_greeting_intent(user_text, role)
    effective_prompt = build_effective_prompt(role, user_text, rag_matched, stage=current_stage)

    rag_mode = role.get("rag_mode", "smart")
    if rag_mode == "exact":
        effective_temp = 0.2 if is_identity_query else 0.0
    elif is_story_intent:
        effective_temp = 0.70
    else:
        effective_temp = role.get("temperature", config.temperature)

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
        temperature=effective_temp
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

    # Check if LLM signaled completion of current stage via [NEXT_STAGE]
    has_next_tag = bool(re.search(r'\[NEXT_STAGE\]', assistant_reply, re.IGNORECASE))
    assistant_reply = re.sub(r'\[NEXT_STAGE\]', '', assistant_reply, flags=re.IGNORECASE).strip()
    assistant_reply = clean_speech_text(assistant_reply)

    if has_next_tag and current_stage and stages:
        curr_idx = -1
        for idx, s in enumerate(stages):
            if s.get("stage_id") == current_stage.get("stage_id"):
                curr_idx = idx
                break
        if curr_idx != -1 and curr_idx + 1 < len(stages):
            current_stage = stages[curr_idx + 1]
            session_skill_tracker[session_id] = {
                "role_id": role.get("id"),
                "stage_id": current_stage.get("stage_id"),
                "updated_at": time.time()
            }
            # Recalculate next_stage_id
            if curr_idx + 2 < len(stages):
                next_stage_id = stages[curr_idx + 2].get("stage_id")
            else:
                next_stage_id = None

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

    skill_info = None
    if skill_obj and skill_obj.get("enabled") and current_stage:
        skill_info = {
            "enabled": True,
            "name": skill_obj.get("name", "SOP 工作流"),
            "description": skill_obj.get("description", ""),
            "current_stage_id": current_stage.get("stage_id"),
            "current_stage_name": current_stage.get("name"),
            "current_stage_goal": current_stage.get("goal"),
            "stages": stages,
            "next_stage_id": next_stage_id,
            "auto_advanced": has_next_tag
        }

    return {
        "user_text": user_text,
        "assistant_reply": assistant_reply,
        "role": role,
        "rag_mode": rag_mode,
        "skill_info": skill_info,
        "rag_matched": rag_matched,
        "executed_tools": executed_tools,
        "metrics": {
            "rag_ms": round(rag_ms, 1),
            "ttft_ms": round(ttft_ms, 1),
            "total_ms": round(total_ms, 1)
        }
    }

@app.get("/api/roles/session_stage")
async def get_role_session_stage(session_id: str = "web_simulator", role_id: Optional[str] = None):
    target_role = None
    if role_id:
        for r in role_manager.get_roles():
            if r["id"] == role_id:
                target_role = r
                break
    if not target_role:
        target_role = role_manager.get_active_role()

    stage = get_session_stage(session_id, target_role)
    skill_obj = target_role.get("skill")
    stages = skill_obj.get("stages", []) if (skill_obj and isinstance(skill_obj, dict) and skill_obj.get("enabled")) else []
    return {
        "session_id": session_id,
        "role_id": target_role.get("id"),
        "stage": stage,
        "stages": stages,
        "enabled": bool(skill_obj and skill_obj.get("enabled"))
    }

@app.post("/api/roles/session_stage")
async def set_role_session_stage(req: Request):
    data = await req.json()
    session_id = data.get("session_id", "web_simulator")
    role_id = data.get("role_id")
    stage_id = data.get("stage_id", 1)

    target_role = None
    if role_id:
        for r in role_manager.get_roles():
            if r["id"] == role_id:
                target_role = r
                break
    if not target_role:
        target_role = role_manager.get_active_role()

    stage = get_session_stage(session_id, target_role, requested_stage_id=stage_id)
    return {"status": "ok", "stage": stage}

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

    session_id = f"sess-{int(time.time())}"
    tts_lock = asyncio.Lock()
    decoder = OpusDecoderWrapper(sample_rate=16000, channels=1)
    tts_streamer = EdgeTTSStreamer()
    asr = get_asr_engine()
    llm = RelayLLMClient()
    vad = EnergyVAD()
    abort_event = asyncio.Event()

    device_info = {
        "device_id": device_mac,
        "client_id": client_id,
        "ip": client_ip,
        "connected_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "last_active": time.strftime("%H:%M:%S"),
        "ws": websocket,
        "session_id": session_id,
        "llm": llm,
        "tts_lock": tts_lock,
        "volume": 70,
        "tools": []
    }
    active_devices[device_mac] = device_info
    print(f"[WS] Device connected: {device_mac} from {client_ip}")

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
        # Pre-ASR Energy & Duration Gate (Filter out sub-threshold noise & ambient clicks)
        duration_sec = len(pcm_all) / 16000.0
        if duration_sec < 0.35:
            return
        rms = float(np.sqrt(np.mean(pcm_all.astype(np.float32) ** 2)))
        if rms < 160.0:
            return

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

        # Guard against phantom triggers ("我", "啊", "嗯", etc.) on ambient silence/short frames
        PHANTOM_GUARD_TOKENS = {"我", "啊", "嗯", "呃", "哦", "欸", "呀", "吧", "呢", "哈", "呵", "你", "对", "是", "我我", "啊啊"}
        if pure_speech in PHANTOM_GUARD_TOKENS and (duration_sec < 1.1 or rms < 450.0):
            print(f"[ASR Guard] Filtered phantom noise token '{user_text}' (dur={duration_sec:.2f}s, rms={rms:.1f})")
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
            is_identity_query = is_identity_or_greeting_intent(user_text, active_role)
            rag_mode = active_role.get("rag_mode", "smart")
            if rag_mode == "exact":
                effective_temp = 0.2 if is_identity_query else 0.0
            elif is_story_intent:
                effective_temp = 0.70
            else:
                effective_temp = active_role.get("temperature", config.temperature)

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

            device_stage = get_session_stage(device_mac, active_role)
            effective_prompt = build_effective_prompt(active_role, user_text, rag_matched, stage=device_stage)

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

            # Check if LLM signaled completion of current stage via [NEXT_STAGE]
            has_next_tag = bool(re.search(r'\[NEXT_STAGE\]', full_assistant_reply, re.IGNORECASE))
            full_assistant_reply = re.sub(r'\[NEXT_STAGE\]', '', full_assistant_reply, flags=re.IGNORECASE).strip()

            skill_obj = active_role.get("skill")
            if has_next_tag and skill_obj and skill_obj.get("enabled"):
                stages = skill_obj.get("stages", [])
                if device_stage and stages:
                    curr_idx = -1
                    for idx, s in enumerate(stages):
                        if s.get("stage_id") == device_stage.get("stage_id"):
                            curr_idx = idx
                            break
                    if curr_idx != -1 and curr_idx + 1 < len(stages):
                        next_stage_obj = stages[curr_idx + 1]
                        session_skill_tracker[device_mac] = {
                            "role_id": active_role.get("id"),
                            "stage_id": next_stage_obj.get("stage_id"),
                            "updated_at": time.time()
                        }
                        print(f"[WS Hardware Skill] Advanced device {device_mac} to Stage {next_stage_obj.get('stage_id')} ({next_stage_obj.get('name')})")

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

                        # Synchronize active role greeting to device upon handshake
                        active_role = role_manager.get_active_role()
                        asyncio.create_task(broadcast_role_greeting_to_device(device_info, active_role))

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
