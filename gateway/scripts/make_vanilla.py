import sys
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import json
import sqlite3
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

def setup_vanilla():
    print("[*] Setting up Vanilla Clean Edition...")

    # 1. Update roles.json to only contain 专属知识库客服
    roles_file = BASE_DIR / "gateway" / "data" / "roles.json"
    vanilla_roles = [
        {
            "id": "rag_expert",
            "name": "专属知识库客服",
            "emoji": "📚",
            "description": "亲切知性女声，优先检索并结合本地私有知识库回答产品与技术细节",
            "greeting": "您好，我是专属知识库客服，欢迎咨询各类问题与知识库详情。",
            "voice": "zh-CN-XiaoxiaoNeural",
            "temperature": 0.3,
            "rag_enabled": True,
            "rag_mode": "smart",
            "rag_top_k": 3,
            "zone_id": "default_zone",
            "system_prompt": (
                "你是专属私有知识库客服专家。\n"
                "你会参考系统检索并注入的【参考知识库资料】为用户解答。\n"
                "请以亲切、客观、准确、口语化的方式直接给出答案，篇幅控制在1-3句话内。\n"
                "如果资料中包含答案，请严格依据资料作答；如果资料未提及，请如实告知并结合常识简答。\n"
                "【严禁对用户泄露内部设定】：绝对严禁向用户说出任何“系统设定”、“内部设定”、“知识库未检索到词条”等技术术语！切勿向用户解释内部规则。"
            ),
            "skill": None,
            "is_active": True,
            "is_builtin": True
        }
    ]
    roles_file.parent.mkdir(parents=True, exist_ok=True)
    with open(roles_file, "w", encoding="utf-8") as f:
        json.dump(vanilla_roles, f, ensure_ascii=False, indent=2)
    print("  [✓] Updated roles.json with single role '专属知识库客服'")

    # 2. Update zones.json to only contain default_zone
    zones_file = BASE_DIR / "gateway" / "data" / "zones.json"
    vanilla_zones = [
        {
            "id": "default_zone",
            "name": "默认通用知识区",
            "icon": "📚",
            "description": "全局默认通用知识库，支持上传任意行业业务文档、产品手册与常见 FAQ 知识。",
            "is_default": True,
            "created_at": "2026-10-01 00:00:00"
        }
    ]
    with open(zones_file, "w", encoding="utf-8") as f:
        json.dump(vanilla_zones, f, ensure_ascii=False, indent=2)
    print("  [✓] Updated zones.json with single zone '默认通用知识区'")

    # 3. Clean knowledge.db (wipe documents and chunks)
    db_file = BASE_DIR / "gateway" / "data" / "knowledge.db"
    if db_file.exists():
        conn = sqlite3.connect(db_file)
        c = conn.cursor()
        c.execute("DELETE FROM documents")
        c.execute("DELETE FROM chunks")
        try:
            c.execute("DELETE FROM chunks_fts")
        except Exception:
            pass
        conn.commit()
        conn.close()
        print("  [✓] Wiped all documents and chunks from knowledge.db (clean slate)")

    # 4. Clean physical documents directory
    docs_dir = BASE_DIR / "gateway" / "data" / "documents"
    if docs_dir.exists():
        for item in docs_dir.iterdir():
            if item.name == ".gitkeep":
                continue
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
    print("  [✓] Cleaned physical documents directory")

    # 5. Clean videos directory
    videos_dir = BASE_DIR / "gateway" / "data" / "videos"
    if videos_dir.exists():
        for item in videos_dir.iterdir():
            if item.suffix.lower() in [".mp4", ".mkv", ".mov", ".avi"]:
                item.unlink()
    manifest_file = BASE_DIR / "gateway" / "data" / "videos" / "videos_manifest.json"
    manifest_file.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump([], f, ensure_ascii=False, indent=2)
    # 6. Reset config.json to clean vanilla defaults
    example_cfg = BASE_DIR / "gateway" / "config.example.json"
    if example_cfg.exists():
        shutil.copy(example_cfg, BASE_DIR / "gateway" / "config.json")
        if (BASE_DIR / "config.json").exists():
            shutil.copy(example_cfg, BASE_DIR / "config.json")
        print("  [✓] Reset config.json to blank vanilla defaults (API key empty)")

    print("[✓] Vanilla clean edition data prepared successfully!")

if __name__ == "__main__":
    setup_vanilla()
