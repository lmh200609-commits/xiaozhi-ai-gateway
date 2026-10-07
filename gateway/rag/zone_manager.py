"""
Knowledge Zone (知识区) Manager.
Allows partitioning and managing multiple knowledge domains (e.g. "白城火车园区知识区"),
each containing its own text documents, FAQs, and exhibition video assets.
"""
import json
import uuid
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ZONES_FILE = DATA_DIR / "zones.json"

DEFAULT_ZONES = [
    {
        "id": "baicheng_railway",
        "name": "中国·大安机车博览园知识区",
        "icon": "🚂",
        "description": "中国·大安机车博览园（吉林白城大安）专属智慧导览知识区。拥有世界最大规模76台蒸汽机车群、22台内燃机车、3台电力机车、三场两馆一线一平台全景导览、朱德号/毛泽东号/黄继光号英雄机车档案与多媒体展映。",
        "is_default": True,
        "created_at": "2026-09-29 20:00:00"
    }
]


class KnowledgeZoneManager:
    """Manages knowledge zones / domains across documents and videos."""

    def __init__(self, zones_file: Path = ZONES_FILE):
        self.zones_file = zones_file
        self.zones_file.parent.mkdir(parents=True, exist_ok=True)
        self.active_zone_id = "baicheng_railway"
        self._ensure_zones_file()

    def _ensure_zones_file(self):
        if not self.zones_file.exists():
            try:
                with open(self.zones_file, "w", encoding="utf-8") as f:
                    json.dump(DEFAULT_ZONES, f, ensure_ascii=False, indent=2)
                print(f"[ZoneManager] Created initial zones.json at {self.zones_file}")
            except Exception as e:
                print(f"[ZoneManager] Error creating zones.json: {e}")

    def list_zones(self) -> List[Dict[str, Any]]:
        if not self.zones_file.exists():
            return list(DEFAULT_ZONES)
        try:
            with open(self.zones_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[ZoneManager] Error reading zones.json: {e}")
            return list(DEFAULT_ZONES)

    def get_zone(self, zone_id: str) -> Optional[Dict[str, Any]]:
        for z in self.list_zones():
            if z.get("id") == zone_id:
                return z
        return None

    def save_zones(self, zones: List[Dict[str, Any]]):
        with open(self.zones_file, "w", encoding="utf-8") as f:
            json.dump(zones, f, ensure_ascii=False, indent=2)

    def create_zone(self, name: str, description: str = "", icon: str = "🏛️") -> Dict[str, Any]:
        zones = self.list_zones()
        zone_id = f"zone_{uuid.uuid4().hex[:8]}"
        created_at = time.strftime("%Y-%m-%d %H:%M:%S")
        new_zone = {
            "id": zone_id,
            "name": name.strip(),
            "icon": icon.strip() or "🏛️",
            "description": description.strip(),
            "is_default": False,
            "created_at": created_at
        }
        zones.append(new_zone)
        self.save_zones(zones)
        print(f"[ZoneManager] Created new knowledge zone: {new_zone['name']} ({zone_id})")
        return new_zone

    def update_zone(self, zone_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        zones = self.list_zones()
        for z in zones:
            if z.get("id") == zone_id:
                if "name" in updates and updates["name"]:
                    z["name"] = updates["name"].strip()
                if "description" in updates:
                    z["description"] = updates["description"].strip()
                if "icon" in updates and updates["icon"]:
                    z["icon"] = updates["icon"].strip()
                self.save_zones(zones)
                return z
        return None

    def delete_zone(self, zone_id: str) -> bool:
        zones = self.list_zones()
        target = None
        for z in zones:
            if z.get("id") == zone_id:
                target = z
                break
        if not target or target.get("is_default"):
            return False  # Cannot delete default zone
        zones = [z for z in zones if z.get("id") != zone_id]
        self.save_zones(zones)
        if self.active_zone_id == zone_id:
            self.active_zone_id = "baicheng_railway"
        print(f"[ZoneManager] Deleted knowledge zone: {zone_id}")
        return True

    def get_active_zone(self) -> Dict[str, Any]:
        zone = self.get_zone(self.active_zone_id)
        if not zone:
            self.active_zone_id = "baicheng_railway"
            zone = self.get_zone("baicheng_railway") or DEFAULT_ZONES[0]
        return zone

    def set_active_zone(self, zone_id: str) -> bool:
        zone = self.get_zone(zone_id)
        if zone:
            self.active_zone_id = zone_id
            print(f"[ZoneManager] Switched active zone to: {zone['name']} ({zone_id})")
            return True
        return False


zone_manager = KnowledgeZoneManager()
