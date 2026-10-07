"""
Railway Theme Park Dedicated Video Asset Manager with Knowledge Zone Support.
Manages preloaded and uploaded videos in gateway/data/videos/, provides auto-scanning,
metadata indexing, zone tagging, and semantic matching for AI guide video playback.
"""
import os
import re
import json
import difflib
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

VIDEOS_DIR = Path(__file__).resolve().parent.parent / "data" / "videos"
MANIFEST_FILE = VIDEOS_DIR / "videos_manifest.json"

SUPPORTED_EXTENSIONS = (".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm")

# Default metadata template for core park exhibits
DEFAULT_MANIFEST = [
    {
        "video_id": "mzd_steam",
        "file_name": "毛泽东号.mp4",
        "title": "毛泽东号机车峥嵘岁月与英雄历程",
        "category": "历史功勋蒸汽机车",
        "zone_id": "baicheng_railway",
        "zone_name": "白城火车园区知识区",
        "zone": "1号机车历史展厅",
        "aliases": ["毛泽东号", "毛泽东", "解放304", "解放型", "jf304", "八一号", "英雄机车", "历史蒸汽机车"],
        "description": "1946年诞生于哈尔滨机务段，中国第一台以领袖命名的英雄机车，见证解放战争与抗美援朝。"
    },
    {
        "video_id": "cr400_fuxing",
        "file_name": "复兴号.mp4",
        "title": "复兴号智能动车组与中国高铁新纪元",
        "category": "现代高速动车组",
        "zone_id": "baicheng_railway",
        "zone_name": "白城火车园区知识区",
        "zone": "3号高铁未来馆",
        "aliases": ["复兴号", "中国高铁", "cr400", "cr400af", "cr400bf", "智能动车组", "高铁", "动车", "和谐号", "智能高铁"],
        "description": "商业运营时速350公里世界第一，中国标准全自主研发的智能高铁列车。"
    },
    {
        "video_id": "jingzhang_railway",
        "file_name": "百年京张.mp4",
        "title": "百年京张铁路与詹天佑人字形工程奇迹",
        "category": "铁路历史工程",
        "zone_id": "baicheng_railway",
        "zone_name": "白城火车园区知识区",
        "zone": "历史文化长廊展区",
        "aliases": ["京张铁路", "百年京张", "詹天佑", "人字形铁路", "青龙桥火车站", "八达岭隧道", "之字形铁路"],
        "description": "1909年中国人自主设计修建的第一条干线铁路，独创人字形折返线开创中国工程奇迹。"
    },
    {
        "video_id": "df4_diesel",
        "file_name": "东风4.mp4",
        "title": "东风浩荡·内燃机车与绿色干线时代",
        "category": "经典内燃机车",
        "zone_id": "baicheng_railway",
        "zone_name": "白城火车园区知识区",
        "zone": "2号内燃时代展厅",
        "aliases": ["东风4", "东风", "df4", "内燃机车", "绿皮车", "绿皮火车", "客运内燃机车", "西瓜涂装"],
        "description": "经典东风4型内燃机车，中国铁路干线内燃化主力，承载数十年绿皮火车时代记忆。"
    },
    {
        "video_id": "qianjin_steam",
        "file_name": "前进型.mp4",
        "title": "前进型蒸汽机车·重型工业之光",
        "category": "重载蒸汽机车",
        "zone_id": "baicheng_railway",
        "zone_name": "白城火车园区知识区",
        "zone": "1号机车历史展厅",
        "aliases": ["前进型", "前进号", "前进型机车", "qj", "重载机车", "蒸汽机车货运"],
        "description": "大同机车厂制造的中国重载货运主力蒸汽机车，牵引力大，中国最后一批停产的蒸汽主力。"
    },
    {
        "video_id": "shaoshan1_electric",
        "file_name": "韶山1型.mp4",
        "title": "韶山1型电力机车·中国电气化铁路奠基之作",
        "category": "第一代电力机车",
        "zone_id": "baicheng_railway",
        "zone_name": "白城火车园区知识区",
        "zone": "3号电力时代展区",
        "aliases": ["韶山1型", "韶山1", "韶山号", "ss1", "电力机车", "宝成铁路机车", "电气化机车"],
        "description": "中国第一代交直流电力机车，攻克宝成铁路大坡道，开启中国铁路电气化新纪元。"
    }
]


class VideoAssetManager:
    """Manages railway exhibition videos stored in gateway/data/videos/ with Knowledge Zone support."""

    def __init__(self, videos_dir: Path = VIDEOS_DIR):
        self.videos_dir = videos_dir
        self.videos_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_manifest()
        self._video_cache: List[Dict[str, Any]] = []
        self.refresh()

    def _ensure_manifest(self):
        """Creates default videos_manifest.json if not present."""
        if not MANIFEST_FILE.exists():
            try:
                with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
                    json.dump(DEFAULT_MANIFEST, f, ensure_ascii=False, indent=2)
                print(f"[VideoManager] Created initial videos_manifest.json at {MANIFEST_FILE}")
            except Exception as e:
                print(f"[VideoManager] Warning creating manifest: {e}")

    def load_manifest(self) -> List[Dict[str, Any]]:
        if not MANIFEST_FILE.exists():
            return list(DEFAULT_MANIFEST)
        try:
            with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
                items = json.load(f)
                # Ensure zone_id is present on all items
                for it in items:
                    if not it.get("zone_id"):
                        it["zone_id"] = "baicheng_railway"
                    if not it.get("zone_name"):
                        it["zone_name"] = "白城火车园区知识区"
                return items
        except Exception as e:
            print(f"[VideoManager] Error reading manifest: {e}")
            return list(DEFAULT_MANIFEST)

    def save_manifest(self, items: List[Dict[str, Any]]):
        try:
            with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
                json.dump(items, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[VideoManager] Error saving manifest: {e}")

    def refresh(self):
        """Scan directory, cross-reference with manifest, and index all video assets."""
        manifest_items = self.load_manifest()
        manifest_by_fn = {}
        manifest_by_id = {}
        for item in manifest_items:
            fn = item.get("file_name", "").lower()
            vid = item.get("video_id", "").lower()
            if fn:
                manifest_by_fn[fn] = item
            if vid:
                manifest_by_id[vid] = item

        # Scan physical files in gateway/data/videos/
        physical_files = set()
        if self.videos_dir.exists():
            for f in os.listdir(self.videos_dir):
                if f.lower().endswith(SUPPORTED_EXTENSIONS):
                    physical_files.add(f)

        indexed: List[Dict[str, Any]] = []
        handled_manifest_ids = set()

        # 1. Index physical files
        for fn in sorted(physical_files):
            full_path = str((self.videos_dir / fn).resolve())
            fn_lower = fn.lower()
            base_no_ext = os.path.splitext(fn)[0]

            meta = manifest_by_fn.get(fn_lower) or manifest_by_fn.get(base_no_ext.lower()) or {}
            vid_id = meta.get("video_id") or base_no_ext
            handled_manifest_ids.add(vid_id)

            aliases = list(meta.get("aliases", []))
            if base_no_ext not in aliases:
                aliases.append(base_no_ext)
            clean_name = re.sub(r'(机车|视频|短片|纪录片|全景|展映|\.mp4|\.mkv)$', '', base_no_ext).strip()
            if clean_name and clean_name not in aliases:
                aliases.append(clean_name)

            title = meta.get("title") or f"{base_no_ext}专题科普短片"
            category = meta.get("category") or "园区展项视频"
            zone = meta.get("zone") or "展厅大屏幕"
            zone_id = meta.get("zone_id") or "baicheng_railway"
            zone_name = meta.get("zone_name") or "白城火车园区知识区"
            desc = meta.get("description") or f"智慧火车园区精选视频《{title}》。"

            indexed.append({
                "video_id": vid_id,
                "file_name": fn,
                "file_path": full_path,
                "title": title,
                "category": category,
                "zone": zone,
                "zone_id": zone_id,
                "zone_name": zone_name,
                "aliases": [a.lower() for a in set(aliases) if a],
                "description": desc,
                "file_size": os.path.getsize(full_path),
                "is_present": True
            })

        # 2. Also keep manifest items whose physical files are not yet in directory
        for item in manifest_items:
            vid_id = item.get("video_id", "")
            fn = item.get("file_name", "")
            if vid_id not in handled_manifest_ids and fn not in physical_files:
                indexed.append({
                    "video_id": vid_id,
                    "file_name": fn,
                    "file_path": str((self.videos_dir / fn).resolve()),
                    "title": item.get("title", fn),
                    "category": item.get("category", "园区展项视频"),
                    "zone": item.get("zone", "展厅大屏幕"),
                    "zone_id": item.get("zone_id", "baicheng_railway"),
                    "zone_name": item.get("zone_name", "白城火车园区知识区"),
                    "aliases": [a.lower() for a in item.get("aliases", []) if a],
                    "description": item.get("description", ""),
                    "file_size": 0,
                    "is_present": False
                })

        self._video_cache = indexed
        present_count = sum(1 for v in indexed if v["is_present"])
        print(f"[VideoManager] Refreshed video asset index: {present_count}/{len(indexed)} videos physically present.")

    def list_videos(self, zone_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if not self._video_cache:
            self.refresh()
        if not zone_id or zone_id == "all":
            return list(self._video_cache)
        return [v for v in self._video_cache if v.get("zone_id") == zone_id]

    def register_uploaded_video(
        self,
        file_name: str,
        file_size: int,
        zone_id: str = "baicheng_railway",
        zone_name: str = "白城火车园区知识区",
        title: Optional[str] = None,
        aliases: Optional[List[str]] = None,
        category: Optional[str] = None,
        description: Optional[str] = None
    ) -> Dict[str, Any]:
        """Registers a newly uploaded video into the manifest and re-indexes."""
        base_no_ext = os.path.splitext(file_name)[0]
        manifest_items = self.load_manifest()

        # Find existing or create new
        existing = None
        for item in manifest_items:
            if item.get("file_name", "").lower() == file_name.lower():
                existing = item
                break

        final_title = title.strip() if title else (existing.get("title") if existing else f"{base_no_ext}专题科普短片")
        final_category = category.strip() if category else (existing.get("category") if existing else "智慧园区展项视频")
        final_desc = description.strip() if description else (existing.get("description") if existing else f"【{zone_name}】专属展播视频《{final_title}》。")

        alias_list = set()
        if existing and "aliases" in existing:
            alias_list.update(existing["aliases"])
        alias_list.add(base_no_ext)
        alias_list.add(base_no_ext.lower())

        # Clean noise tags like _1080p, _720p, 1080P
        clean_name = re.sub(r'(_1080p|_720p|_4k|1080p|720p|4k|\.mp4|\.mkv|\.avi)$', '', base_no_ext, flags=re.IGNORECASE).strip()
        if clean_name:
            alias_list.add(clean_name)
            alias_list.add(clean_name.lower())

        # Split on common title punctuation: ——, —, _, -, 、, |, 空格
        segments = re.split(r'[—_\-、\s|~·]+', clean_name)
        for seg in segments:
            seg_s = seg.strip()
            if len(seg_s) >= 2:
                alias_list.add(seg_s)
                alias_list.add(seg_s.lower())

        # Domain-specific intelligent semantic aliases:
        base_lower = base_no_ext.lower()
        if any(k in base_lower for k in ["博览园", "大安", "园区", "火车园"]):
            alias_list.update([
                "整个园区", "介绍整个园区", "园区介绍", "介绍园区", "大安机车博览园",
                "中国大安机车博览园", "大安博览园", "机车博览园", "大安机车园",
                "博览园vlog", "园区vlog", "大安vlog", "园区导览", "全园导览", "全景视频", "宣传片"
            ])
        if "毛泽东" in base_lower:
            alias_list.update(["毛泽东号", "毛泽东", "毛泽东号机车", "解放304", "jf304"])
        if "复兴" in base_lower or "高铁" in base_lower:
            alias_list.update(["复兴号", "中国高铁", "智能动车组", "高铁", "动车"])
        if "京张" in base_lower or "詹天佑" in base_lower:
            alias_list.update(["京张铁路", "百年京张", "詹天佑", "人字形铁路"])
        if "东风" in base_lower:
            alias_list.update(["东风4", "东风", "df4", "内燃机车", "绿皮车"])
        if "前进" in base_lower or "76台" in base_lower:
            alias_list.update(["前进型", "前进号", "76台", "76台蒸汽机车", "蒸汽机车群"])

        if aliases:
            for a in aliases:
                a_clean = a.strip()
                if a_clean:
                    alias_list.add(a_clean)
                    alias_list.add(a_clean.lower())

        entry = {
            "video_id": existing.get("video_id") if existing else base_no_ext.lower().replace(" ", "_"),
            "file_name": file_name,
            "title": final_title,
            "category": final_category,
            "zone_id": zone_id,
            "zone_name": zone_name,
            "zone": existing.get("zone", "展厅大屏幕") if existing else "展厅大屏幕",
            "aliases": sorted(list(alias_list)),
            "description": final_desc,
            "file_size": file_size,
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }

        if existing:
            manifest_items = [entry if it.get("file_name", "").lower() == file_name.lower() else it for it in manifest_items]
        else:
            manifest_items.append(entry)

        self.save_manifest(manifest_items)
        self.refresh()
        print(f"[VideoManager] Registered uploaded video '{file_name}' for zone '{zone_name}' ({zone_id})")
        return entry

    def update_video_meta(self, video_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        manifest_items = self.load_manifest()
        target = None
        for it in manifest_items:
            if it.get("video_id") == video_id or it.get("file_name", "").lower() == video_id.lower():
                target = it
                break

        if not target:
            return None

        if "title" in updates and updates["title"]:
            target["title"] = updates["title"].strip()
        if "category" in updates and updates["category"]:
            target["category"] = updates["category"].strip()
        if "description" in updates:
            target["description"] = updates["description"].strip()
        if "zone_id" in updates and updates["zone_id"]:
            target["zone_id"] = updates["zone_id"].strip()
        if "zone_name" in updates and updates["zone_name"]:
            target["zone_name"] = updates["zone_name"].strip()
        if "aliases" in updates:
            if isinstance(updates["aliases"], list):
                target["aliases"] = [a.strip() for a in updates["aliases"] if a.strip()]
            elif isinstance(updates["aliases"], str):
                target["aliases"] = [a.strip() for a in updates["aliases"].replace("，", ",").split(",") if a.strip()]

        self.save_manifest(manifest_items)
        self.refresh()
        return target

    def delete_video(self, video_id: str, delete_file: bool = True) -> bool:
        manifest_items = self.load_manifest()
        target_fn = None
        new_manifest = []
        for it in manifest_items:
            if it.get("video_id") == video_id or it.get("file_name", "").lower() == video_id.lower():
                target_fn = it.get("file_name")
            else:
                new_manifest.append(it)

        self.save_manifest(new_manifest)

        # Remove physical file if requested
        if delete_file and target_fn:
            fpath = self.videos_dir / target_fn
            if fpath.exists():
                try:
                    os.remove(fpath)
                    print(f"[VideoManager] Removed physical file: {fpath}")
                except Exception as e:
                    print(f"[VideoManager] Error removing file: {e}")

        self.refresh()
        return True

    def find_video(self, keyword: str, zone_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Smart resolution matching visitor's query to a local video asset:
        1. Exact alias/filename match (highest priority, score 1000)
        2. Substring match (score 800)
        3. Fuzzy match via SequenceMatcher (score 500+)
        """
        if not self._video_cache:
            self.refresh()
        if not self._video_cache:
            return None

        kw_clean = keyword.lower().strip()
        # Strip quotes and brackets
        kw_clean = re.sub(r'[“”"\'「」『』《》【】\[\]()（）]', '', kw_clean).strip()

        # 1. Strip common oral request prefixes
        prefixes = [
            "请为我播放一下", "请帮我播放一下", "请为我播放", "请帮我播放", "请为我放一下", "请帮我放一下",
            "为我播放一下", "帮我播放一下", "为我播放", "帮我播放", "为我放一下", "帮我放一下",
            "我想看一下", "我想看下", "我想看看", "我想看", "我想了解", "我要看", "我想了解下",
            "我桌面上的", "桌面上的", "桌面的", "桌面",
            "我电脑上的", "电脑上的", "电脑里的", "本地的", "本地",
            "请播放", "播放", "打开", "看一下", "看下", "看", "放一个", "放一下", "放下", "放"
        ]
        for p in sorted(prefixes, key=len, reverse=True):
            if kw_clean.startswith(p):
                kw_clean = kw_clean[len(p):].strip()
                break

        # 2. Strip punctuation at boundary
        kw_clean = re.sub(r'^[，,。！!？?\s]+|[，,。！!？?\s]+$', '', kw_clean)

        # 3. Strip oral suffixes
        suffixes = [
            "的一个那个视频", "的一个视频", "的一个短片", "的一个那个短片", "的那个视频", "的那个短片",
            "的那个片子", "的那个录像", "的那个vlog", "的视频文件", "的短片", "的录像", "的视频",
            "视频文件", "视频", "短片", "纪录片", "录像", "录像带", "片子", "影片"
        ]
        for s in sorted(suffixes, key=len, reverse=True):
            if kw_clean.endswith(s):
                kw_clean = kw_clean[:-len(s)].strip()
                break

        # 4. Strip oral fillers at start: e.g. "介绍整个园区" -> "整个园区"
        for filler in ["介绍一下", "介绍下", "介绍", "关于", "展示一下", "展示下", "展示"]:
            if kw_clean.startswith(filler) and len(kw_clean) > len(filler):
                kw_clean = kw_clean[len(filler):].strip()
                break

        scored = []
        candidates = self._video_cache
        if zone_id and zone_id != "all":
            candidates = [v for v in self._video_cache if v.get("zone_id") == zone_id]

        for vid in candidates:
            # Only consider videos that are physically present for actual playback
            if not vid.get("is_present"):
                continue

            score = 0
            base_no_ext = os.path.splitext(vid["file_name"])[0].lower()

            # Exact match
            if kw_clean == base_no_ext or kw_clean == vid["file_name"].lower() or kw_clean == vid["video_id"].lower():
                score = 1000
            elif any(kw_clean == a for a in vid["aliases"]):
                score = 950
            # Keyword in aliases
            elif any(kw_clean in a for a in vid["aliases"]):
                score = 800
            # Alias in keyword (e.g. user said "我想看东风4绿皮车跑起来的视频", alias "东风4")
            elif any(a in kw_clean for a in vid["aliases"] if len(a) >= 2):
                score = 750
            # Title match
            elif kw_clean in vid["title"].lower():
                score = 700
            else:
                # Fuzzy ratio
                for a in vid["aliases"]:
                    ratio = difflib.SequenceMatcher(None, kw_clean, a).ratio()
                    if ratio >= 0.6:
                        score = max(score, int(500 * ratio))

            if score > 0:
                scored.append((score, vid))

        if scored:
            scored.sort(key=lambda x: x[0], reverse=True)
            best = scored[0][1]
            print(f"[VideoManager] Matched video for '{keyword}' -> '{best['file_name']}' (score: {scored[0][0]})")
            return best

        return None


# Global singleton instance
video_manager = VideoAssetManager()
