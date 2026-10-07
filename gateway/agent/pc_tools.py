import os
import glob
import time
import re
import difflib
import urllib.parse
import subprocess
import threading
import ctypes
import ctypes.wintypes
from typing import Dict, Any, List, Optional

SW_SHOWNORMAL = 1
SW_MAXIMIZE = 3
SW_RESTORE = 9

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

user32 = ctypes.windll.user32

try:
    from gateway.rag.video_manager import video_manager
except Exception:
    video_manager = None

PC_TOOLS_DEFINITIONS = [
    {
        "name": "open_software",
        "description": "在用户的电脑上打开指定的本地软件应用程序，例如微信(WeChat)、QQ、网页浏览器(Edge/Chrome)、记事本(Notepad)、计算器(Calculator)等。",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "要打开的软件或应用名称，例如'微信'、'wechat'、'浏览器'、'chrome'、'计算器'、'记事本'等"
                }
            },
            "required": ["name"]
        }
    },
    {
        "name": "play_video",
        "description": "【必须严格满足条件才可调用】在电脑大屏幕上全屏播放指定视频。仅当游客发出明确的播放指令（如‘播放毛泽东号’、‘放一下视频’、‘我想看复兴号短片’、‘播放桌面上的首页.mp4’）时，才调用此工具。若游客只是咨询‘有什么视频’、‘需要看什么视频’、询问机车历史或闲聊，绝对禁止调用此工具！此时应口头热情介绍博览园视频，并询问对方想看哪一部。",
        "parameters": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "视频文件名或关键词，例如'毛泽东号'、'复兴号'、'首页.mp4'等"
                }
            },
            "required": ["keyword"]
        }
    },
    {
        "name": "close_video",
        "description": "关闭电脑上当前正在播放的视频或媒体播放器窗口。",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "get_pc_status",
        "description": "获取当前电脑运行状态与桌面信息，包括当前正在前台运行的应用软件、正在播放的视频、电脑音量状态或桌面上的视频文件列表。",
        "parameters": {
            "type": "object",
            "properties": {
                "query_type": {
                    "type": "string",
                    "description": "查询类型: 'all'(综合状态), 'videos'(桌面与本地视频文件列表), 'apps'(当前运行的软件应用)"
                }
            }
        }
    },
    {
        "name": "set_volume",
        "description": "调节小智硬件喇叭音量或电脑音量。当用户要求调大声音、调小音量、声音太小/太大了、设置指定音量百分比(0-100)或静音时，必须调用此工具。",
        "parameters": {
            "type": "object",
            "properties": {
                "volume": {
                    "type": "integer",
                    "description": "目标音量数值 (0-100)。如调大音量可设为当前+20(如80)，调小设为当前-20(如40)，静音设为0，最大音量设为100。"
                },
                "action": {
                    "type": "string",
                    "description": "音量调节动作类型: 'up'(调大), 'down'(调小), 'mute'(静音), 'set'(设为指定值)"
                }
            }
        }
    },
    {
        "name": "system_control",
        "description": "控制电脑桌面与屏幕显示: 'show_desktop'(显示桌面), 'lock_screen'(锁定电脑屏幕)。",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "动作类型: show_desktop, lock_screen"
                }
            },
            "required": ["action"]
        }
    }
]


PLAYBACK_INTENT_KEYWORDS = (
    "放", "播", "看", "瞧", "观赏", "观看", "播放", "放映", "放一下", "放个", "放段", "播一下", "播个",
    "大屏", "投屏", "屏幕", "大屏幕", "全屏", "展映", "视频", "短片", "纪录片", "vlog", "片子", "电影", "影像", "演示", "片段",
    "play", "video", "movie"
)

def filter_tools_for_query(user_text: str, base_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Strict Intent-Gating: Only supply 'play_video' tool to LLM if the user actually
    expressed an intention to watch/play/view/screen a video.
    Prevents false-positive video playback on pure informational or greeting queries.
    """
    text_lower = (user_text or "").lower()
    has_play_intent = any(k in text_lower for k in PLAYBACK_INTENT_KEYWORDS)

    filtered = []
    for t in base_tools:
        name = t.get("name", "")
        if name == "play_video":
            if has_play_intent:
                filtered.append(t)
            else:
                # Omit play_video from tool definitions for this turn
                pass
        else:
            filtered.append(t)
    return filtered


def _make_si() -> subprocess.STARTUPINFO:
    """Create STARTUPINFO targeting WinSta0\\Default — the user's physical screen."""
    si = subprocess.STARTUPINFO()
    si.lpDesktop = r"WinSta0\Default"
    si.wShowWindow = SW_SHOWNORMAL
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return si


def launch_on_user_desktop(exe_path: str, args: List[str] = None, cwd: str = None) -> bool:
    """Launch a process on WinSta0\\Default regardless of current sandbox desktop."""
    cmd_list = [exe_path] + (args or [])
    try:
        proc = subprocess.Popen(
            cmd_list,
            cwd=cwd or (os.path.dirname(exe_path) if exe_path else None),
            startupinfo=_make_si(),
            close_fds=True
        )
        print(f"[PC Agent] Launched on WinSta0\\Default: PID={proc.pid} cmd={cmd_list[0]}")
        return True
    except Exception as e:
        print(f"[PC Agent] launch_on_user_desktop failed: {e}")
        return False


def safe_open(target: str, cwd: str = None) -> bool:
    """Open an application, document, video, or URL using Windows native ShellExecute or desktop spawn."""
    if target.lower().endswith(".exe") and os.path.isabs(target):
        return launch_on_user_desktop(target, cwd=cwd or os.path.dirname(target))
    try:
        os.startfile(target)
        print(f"[PC Agent] Successfully opened via os.startfile: {target}")
        return True
    except Exception as e:
        print(f"[PC Agent] os.startfile failed on {target}: {e}, falling back to launch_on_user_desktop")
        return launch_on_user_desktop(target, cwd=cwd)


def launch_shell_on_user_desktop(cmd_str: str) -> bool:
    """Run a shell command on WinSta0\\Default."""
    try:
        proc = subprocess.Popen(cmd_str, shell=True, startupinfo=_make_si(), close_fds=True)
        print(f"[PC Agent] Shell cmd launched on WinSta0\\Default: PID={proc.pid}")
        return True
    except Exception as e:
        print(f"[PC Agent] launch_shell_on_user_desktop failed: {e}")
        return False


def find_and_foreground_window(title_keywords: List[str], class_keywords: List[str] = None) -> bool:
    """Enumerate WinSta0\\Default windows and bring matching one to front.
    Uses closure-based callback to safely collect HWNDs without ctypes pointer tricks.
    """
    title_kws = [k.lower() for k in title_keywords]
    class_kws  = [k.lower() for k in (class_keywords or [])]
    buf_t = ctypes.create_unicode_buffer(512)
    buf_c = ctypes.create_unicode_buffer(256)
    found_hwnd = [0]  # use list so closure can mutate

    # Callback: called once per top-level window
    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def _cb(hwnd, _lp):
        if found_hwnd[0]:
            return False  # stop enumeration once found
        if not user32.IsWindowVisible(hwnd):
            return True
        user32.GetWindowTextW(hwnd, buf_t, 512)
        user32.GetClassNameW(hwnd, buf_c, 256)
        title = buf_t.value.lower()
        cls   = buf_c.value.lower()
        title_match = any(k in title for k in title_kws)
        class_match = any(k in cls   for k in class_kws) if class_kws else False
        if title_match or class_match:
            print(f"[PC Agent] Found window: hwnd={hwnd} title='{buf_t.value}' class='{buf_c.value}'")
            found_hwnd[0] = hwnd
            return False  # stop enumeration
        return True

    # Try to enumerate the user's Default desktop first
    hdesk = user32.OpenDesktopW("Default", 0, False, 0x00000100)
    if hdesk:
        user32.EnumDesktopWindows(hdesk, _cb, 0)
        user32.CloseDesktop(hdesk)
    else:
        # Fallback: enumerate current thread's desktop
        user32.EnumWindows(_cb, 0)

    hwnd = found_hwnd[0]
    if hwnd:
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)
        return True

    print(f"[PC Agent] No window found for keywords={title_keywords}")
    return False


def find_shortcut(app_keywords: List[str]) -> str:
    search_dirs = [
        os.path.expandvars(r"%USERPROFILE%\Desktop"),
        os.path.expandvars(r"%PUBLIC%\Desktop"),
        os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"),
        os.path.expandvars(r"%ALLUSERSPROFILE%\Microsoft\Windows\Start Menu\Programs"),
    ]
    for directory in search_dirs:
        if not os.path.exists(directory):
            continue
        for lnk in glob.glob(os.path.join(directory, "**", "*.lnk"), recursive=True):
            base_name = os.path.basename(lnk).lower()
            for kw in app_keywords:
                if kw.lower() in base_name and "卸载" not in base_name and "uninstall" not in base_name:
                    return lnk
    return ""


def execute_open_software(name: str) -> Dict[str, Any]:
    name_clean = name.strip().lower()
    print(f"[PC Agent Tool] Request to open software: '{name}'")

    if any(k in name_clean for k in ["视频", "video", "纪录片", "播放"]):
        return execute_play_video(name)

    # WeChat
    if any(k in name_clean for k in ["微信", "wechat", "weixin"]):
        if find_and_foreground_window(["微信", "wechat", "weixin"], ["wechatwindow", "weixin"]):
            return {"status": "success", "app": "微信", "message": "好的，已为您显示微信窗口！"}
        desktop_wx = os.path.join(os.path.expanduser("~/Desktop"), "微信.lnk")
        if os.path.exists(desktop_wx):
            safe_open(desktop_wx)
            return {"status": "success", "app": "微信", "message": "好的，已为您在电脑屏幕上打开微信！"}
        for path in [
            r"C:\Program Files\Tencent\Weixin\Weixin.exe",
            r"C:\Program Files\Tencent\WeChat\WeChat.exe",
            r"C:\Program Files (x86)\Tencent\WeChat\WeChat.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tencent\Weixin\Weixin.exe"),
            r"D:\Program Files\Tencent\Weixin\Weixin.exe",
        ]:
            if os.path.exists(path):
                safe_open(path, cwd=os.path.dirname(path))
                return {"status": "success", "app": "微信", "message": "好的，已为您在电脑屏幕上打开微信！"}
        lnk = find_shortcut(["微信", "wechat", "weixin"])
        if lnk:
            safe_open(lnk)
            return {"status": "success", "app": "微信", "message": "好的，已为您打开微信！"}
        safe_open("weixin:")
        return {"status": "success", "app": "微信", "message": "好的，正在为您打开微信！"}

    # QQ
    if "qq" in name_clean:
        if find_and_foreground_window(["qq"], ["qqmainfram", "txguifoundation"]):
            return {"status": "success", "app": "QQ", "message": "好的，已为您显示QQ窗口！"}
        for path in [
            r"C:\Program Files\Tencent\QQNT\QQ.exe",
            os.path.expanduser(r"~\Desktop\QQ.lnk"),
            r"C:\Program Files (x86)\Tencent\QQ\Bin\QQ.exe",
            r"D:\Program Files\Tencent\QQNT\QQ.exe"
        ]:
            if os.path.exists(path):
                safe_open(path, cwd=os.path.dirname(path))
                return {"status": "success", "app": "QQ", "message": "好的，已为您打开QQ！"}
        safe_open("qq:")
        return {"status": "success", "app": "QQ", "message": "好的，正在为您打开QQ！"}

    # Browser
    if any(k in name_clean for k in ["浏览器", "网页", "chrome", "edge", "browser"]):
        if find_and_foreground_window(["chrome", "edge", "浏览器"]):
            return {"status": "success", "app": "浏览器", "message": "好的，已为您切换至浏览器窗口！"}
        for b_path in [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"
        ]:
            if os.path.exists(b_path):
                safe_open(b_path)
                return {"status": "success", "app": "浏览器", "message": "好的，已为您打开网页浏览器！"}
        safe_open("http://localhost:8001")
        return {"status": "success", "app": "浏览器", "message": "好的，已为您打开网页浏览器！"}

    # Calculator
    if any(k in name_clean for k in ["计算器", "calc", "calculator"]):
        safe_open("calc.exe")
        return {"status": "success", "app": "计算器", "message": "好的，已为您打开计算器！"}

    # Notepad
    if any(k in name_clean for k in ["记事本", "文本", "notepad", "txt"]):
        safe_open("notepad.exe")
        return {"status": "success", "app": "记事本", "message": "好的，已为您打开记事本！"}

    # File Explorer
    if any(k in name_clean for k in ["文件", "资源管理器", "此电脑", "我的电脑", "explorer"]):
        safe_open("explorer.exe")
        return {"status": "success", "app": "资源管理器", "message": "好的，已为您打开文件资源管理器！"}

    # Generic shortcut
    lnk = find_shortcut([name_clean])
    if lnk and os.path.exists(lnk):
        safe_open(lnk)
        return {"status": "success", "app": os.path.basename(lnk), "message": f"已为您打开 {name}！"}

    return {"status": "not_found", "message": f"未在电脑上找到名为 '{name}' 的应用程序"}


def normalize_video_keyword(keyword: str) -> str:
    kw = keyword.strip()
    # Strip quotes and brackets
    kw = re.sub(r'[“”"\'「」『』《》【】\[\]()（）]', '', kw).strip()
    # Strip common prefix phrases
    prefixes = [
        "请为我播放一下", "请帮我播放一下", "请为我播放", "请帮我播放", "请为我放一下", "请帮我放一下",
        "为我播放一下", "帮我播放一下", "为我播放", "帮我播放", "为我放一下", "帮我放一下",
        "我想看一下", "我想看下", "我想看看", "我想看", "我想了解", "我要看", "我想了解下",
        "我桌面上的", "桌面上的", "桌面的", "桌面",
        "我电脑上的", "电脑上的", "电脑里的", "本地的", "本地",
        "我的", "请播放", "播放", "打开", "看一下", "看下", "看", "放一个", "放一下", "放下", "放"
    ]
    for p in sorted(prefixes, key=len, reverse=True):
        if kw.startswith(p):
            kw = kw[len(p):].strip()
            break

    # Strip boundary punctuation
    kw = re.sub(r'^[，,。！!？?\s]+|[，,。！!？?\s]+$', '', kw)

    # Strip suffix phrases
    suffixes = [
        "的一个那个视频", "的一个视频", "的一个短片", "的一个那个短片", "的那个视频", "的那个短片",
        "的那个片子", "的那个录像", "的那个vlog", "的视频文件", "的短片", "的录像", "的视频",
        "视频文件", "视频", "短片", "录像", "影片", "片子", "video", "vlog"
    ]
    for s in sorted(suffixes, key=len, reverse=True):
        if kw.endswith(s):
            kw = kw[:-len(s)].strip()
            break

    # Strip leading fillers
    for filler in ["介绍一下", "介绍下", "介绍", "关于", "展示一下", "展示下", "展示"]:
        if kw.startswith(filler) and len(kw) > len(filler):
            kw = kw[len(filler):].strip()
            break

    # Strip common video file extensions
    kw = re.sub(r'\.(mp4|mkv|avi|mov|flv|wmv|webm)$', '', kw, flags=re.IGNORECASE).strip()
    return kw


def find_local_video(keyword: str) -> Optional[str]:
    """
    Search for local video files matching the keyword in:
    1. Dedicated Park Video Asset Directory: gateway/data/videos/ (HIGHEST PRIORITY)
    2. User Desktop: ~/Desktop
    3. User Videos: ~/Videos
    4. User Downloads: ~/Downloads
    5. User Documents: ~/Documents
    Supports .mp4, .mkv, .avi, .mov, .flv, .wmv, .webm.
    """
    # 1. Highest Priority: Check dedicated railway park video repository
    if video_manager:
        matched = video_manager.find_video(keyword)
        if matched and os.path.exists(matched["file_path"]):
            print(f"[PC Agent Tool] Found in dedicated park video repository: {matched['file_path']}")
            return matched["file_path"]

    video_dirs = [
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "videos")),
        os.path.expanduser("~/Desktop"),
        os.path.expanduser("~/Videos"),
        os.path.expanduser("~/Downloads"),
        os.path.expanduser("~/Documents")
    ]
    extensions = (".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm")
    all_videos = []
    desktop_root = os.path.normpath(os.path.expanduser("~/Desktop")).lower()

    for vdir in video_dirs:
        if not os.path.exists(vdir):
            continue
        vdir_depth = vdir.count(os.sep)
        for root, dirs, files in os.walk(vdir):
            current_depth = root.count(os.sep) - vdir_depth
            if current_depth > 2:
                dirs.clear()
                continue
            for f in files:
                if f.lower().endswith(extensions) and not f.startswith("."):
                    all_videos.append(os.path.join(root, f))

    if not all_videos:
        return None

    kw_raw = keyword.lower().strip()
    kw_clean = normalize_video_keyword(keyword).lower()

    generic_terms = ["本地", "本地视频", "我的视频", "电脑视频", "视频", "放个视频", "播放视频", "看视频", "录像", "video", "放视频", "播放本地视频", "放本地视频", ""]
    is_generic = (kw_clean in generic_terms) or (kw_raw in generic_terms)

    # 1. Generic local video request -> return most recently modified video
    if is_generic:
        all_videos.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        return all_videos[0]

    # 2. Smart Match with scoring
    scored = []
    user_mentioned_desktop = ("桌面" in kw_raw)

    import difflib
    for v in all_videos:
        v_norm = os.path.normpath(v)
        base = os.path.basename(v).lower()
        base_no_ext, _ = os.path.splitext(base)
        is_in_desktop = (os.path.dirname(v_norm).lower() == desktop_root)

        score = 0
        # Exact match (with or without extension)
        if kw_clean == base_no_ext or kw_clean == base:
            score = 1000
        # Basename starts with keyword
        elif base_no_ext.startswith(kw_clean):
            score = 800
        # Keyword is substring of basename
        elif kw_clean in base_no_ext:
            score = 700
        # Basename is substring of keyword (e.g. file '首页', query '播放桌面首页')
        elif base_no_ext in kw_clean and len(base_no_ext) >= 2:
            score = 650
        else:
            # Fuzzy match
            ratio = difflib.SequenceMatcher(None, kw_clean, base_no_ext).ratio()
            if ratio >= 0.55:
                score = int(500 * ratio)

        if score > 0:
            # Desktop priority bonus
            if user_mentioned_desktop and "desktop" in v_norm.lower():
                score += 150
            if is_in_desktop:
                score += 50
            # Recency bonus (up to 20 pts)
            mtime = os.path.getmtime(v)
            score += min(20, int(mtime / 100000000))
            scored.append((score, v))

    if scored:
        scored.sort(key=lambda x: x[0], reverse=True)
        best_match = scored[0][1]
        print(f"[PC Agent Tool] Smart video match for '{keyword}' (clean: '{kw_clean}'): {best_match} (score: {scored[0][0]})")
        return best_match

    return None


def make_player_fullscreen(video_name: str = "") -> bool:
    """Wait for video player window to appear on WinSta0\\Default, bring to foreground,
    maximize it, and trigger Alt+Enter for true fullscreen."""
    name_clean = os.path.splitext(video_name)[0].lower() if video_name else ""
    player_kw = ["xmp", "thunder", "迅雷", "potplayer", "vlc", "wmplayer", "media", "播放器"]
    if name_clean:
        player_kw.append(name_clean)

    buf_t = ctypes.create_unicode_buffer(512)
    buf_c = ctypes.create_unicode_buffer(256)

    # Give player process time to initialize its main window
    time.sleep(0.8)

    for _ in range(8):
        found = [0]

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
        def _cb(hwnd, _lp):
            if not user32.IsWindowVisible(hwnd):
                return True
            user32.GetWindowTextW(hwnd, buf_t, 512)
            user32.GetClassNameW(hwnd, buf_c, 256)
            t = buf_t.value.lower()
            c = buf_c.value.lower()
            if any(k in t for k in ["启动小智ai网关", "小智 ai 硬件", "visual studio code"]):
                return True
            if any(k in t or k in c for k in player_kw):
                found[0] = hwnd
                return False
            return True

        hdesk = user32.OpenDesktopW("Default", 0, False, 0x01FF)
        if hdesk:
            user32.SetThreadDesktop(hdesk)
            user32.EnumDesktopWindows(hdesk, _cb, 0)
            user32.CloseDesktop(hdesk)
        else:
            user32.EnumWindows(_cb, 0)

        hwnd = found[0]
        if hwnd:
            print(f"[PC Agent] Found media player window HWND={hwnd}, bringing to front and setting true fullscreen...")
            user32.ShowWindow(hwnd, SW_RESTORE)
            user32.SetForegroundWindow(hwnd)
            user32.BringWindowToTop(hwnd)
            time.sleep(0.2)

            # 1. Size to physical monitor resolution (DPI-aware)
            screen_w = user32.GetSystemMetrics(0)
            screen_h = user32.GetSystemMetrics(1)
            HWND_TOP = 0
            SWP_SHOWWINDOW = 0x0040
            user32.SetWindowPos(hwnd, HWND_TOP, 0, 0, screen_w, screen_h, SWP_SHOWWINDOW)
            user32.ShowWindow(hwnd, SW_MAXIMIZE)
            time.sleep(0.25)

            # 2. Send single Enter key (standard fullscreen toggle for 迅雷影音 Xmp, PotPlayer)
            VK_RETURN = 0x0D
            KEYEVENTF_KEYUP = 0x0002
            user32.keybd_event(VK_RETURN, 0, 0, 0)
            time.sleep(0.05)
            user32.keybd_event(VK_RETURN, 0, KEYEVENTF_KEYUP, 0)
            return True

        time.sleep(0.4)

    return False


def _open_video_in_browser(video_path: str, title: str = "") -> bool:
    """Open video in our gateway's built-in web player via browser (kiosk/fullscreen mode)."""
    import webbrowser
    encoded_path = urllib.parse.quote(video_path, safe="")
    encoded_title = urllib.parse.quote(title, safe="")
    player_url = f"http://localhost:8001/player.html?video_url=/api/videos/stream?path={encoded_path}&title={encoded_title}"
    print(f"[PC Agent Tool] Opening video in browser player: {player_url}")

    edge_paths = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for edge_path in edge_paths:
        if os.path.exists(edge_path):
            try:
                subprocess.Popen(
                    [edge_path, "--app=" + player_url, "--start-fullscreen"],
                    startupinfo=_make_si(),
                    close_fds=True
                )
                print(f"[PC Agent Tool] Launched Edge app mode for fullscreen video")
                return True
            except Exception as e:
                print(f"[PC Agent Tool] Edge app launch failed: {e}")

    try:
        webbrowser.open(player_url)
        print(f"[PC Agent Tool] Opened in default browser")
        return True
    except Exception as e:
        print(f"[PC Agent Tool] webbrowser.open failed: {e}")
        return False


def execute_play_video(keyword: str) -> Dict[str, Any]:
    kw = keyword.strip()
    print(f"[PC Agent Tool] Request to play video for: '{kw}'")

    matched_meta = None
    local_vid = None
    vid_title = None

    # 1. First priority: Check dedicated railway park video repository
    if video_manager:
        matched_meta = video_manager.find_video(kw)
        if matched_meta and os.path.exists(matched_meta["file_path"]):
            local_vid = matched_meta["file_path"]
            vid_title = matched_meta["title"]
            print(f"[PC Agent Tool] Matched dedicated park video: {local_vid} ({vid_title})")

    # 2. Fallback to general local search (Desktop, Videos folder, etc.)
    if not local_vid:
        local_vid = find_local_video(kw)

    if local_vid and os.path.exists(local_vid):
        local_vid = os.path.normpath(local_vid)
        vid_name = os.path.basename(local_vid)
        if not vid_title:
            vid_title = os.path.splitext(vid_name)[0]
        print(f"[PC Agent Tool] Launching native fullscreen playback for: {local_vid}")

        # Clean up any lingering desktop media players
        for proc in ["mpv.exe", "xmp.exe", "thunder.exe", "potplayer.exe", "potplayermini64.exe"]:
            try:
                subprocess.run(["taskkill", "/F", "/IM", proc],
                               startupinfo=_make_si(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

        # For Scenic AI Kiosk exhibition, the video is rendered directly on the big screen via seamless Cinema Overlay
        return {
            "status": "success",
            "video_id": matched_meta["video_id"] if matched_meta else "local_file",
            "title": vid_title,
            "path": local_vid,
            "keyword": kw,
            "mode": "kiosk_overlay",
            "message": f"好的，已为您在展厅大屏幕上全屏展映《{vid_title}》，请欣赏！"
        }

        # Automatically bring player to front, maximize, and set full screen
        threading.Thread(target=make_player_fullscreen, args=(vid_name,), daemon=True).start()

        return {
            "status": "success",
            "video_id": matched_meta["video_id"] if matched_meta else "local_file",
            "title": vid_title,
            "path": local_vid,
            "keyword": kw,
            "mode": "native_player",
            "message": f"好的，已为您在电脑大屏上全屏播放《{vid_title}》，请欣赏！"
        }

    # 3. If no physical video file was found
    return {
        "status": "not_found",
        "keyword": kw,
        "message": f"抱歉，展厅视频库中暂未找到与“{kw}”相关的视频短片。您可以把对应视频放入后台 videos 目录哦！"
    }


def execute_close_video() -> Dict[str, Any]:
    for proc in ["mpv.exe", "xmp.exe", "thunder.exe", "potplayer.exe", "potplayermini64.exe", "vlc.exe", "wmplayer.exe", "Video.UI.exe", "Microsoft.Media.Player.exe"]:
        try:
            subprocess.Popen(["taskkill", "/F", "/IM", proc],
                             startupinfo=_make_si(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
    return {"status": "success", "message": "好的，已为您关闭电脑视频播放。"}


VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP   = 0xAF

def adjust_windows_volume(action: str) -> None:
    """Adjusts Windows master volume via simulated multimedia keyboard events."""
    act = action.lower()
    if act in ["up", "volume_up"]:
        for _ in range(5):
            user32.keybd_event(VK_VOLUME_UP, 0, 0, 0)
            user32.keybd_event(VK_VOLUME_UP, 0, 2, 0)
    elif act in ["down", "volume_down"]:
        for _ in range(5):
            user32.keybd_event(VK_VOLUME_DOWN, 0, 0, 0)
            user32.keybd_event(VK_VOLUME_DOWN, 0, 2, 0)
    elif act in ["mute"]:
        user32.keybd_event(VK_VOLUME_MUTE, 0, 0, 0)
        user32.keybd_event(VK_VOLUME_MUTE, 0, 2, 0)


def execute_system_control(action: str) -> Dict[str, Any]:
    act = action.lower().strip()
    if act == "show_desktop":
        launch_shell_on_user_desktop(
            'powershell -Command "(New-Object -ComObject Shell.Application).MinimizeAll()"')
        return {"status": "success", "message": "已为您切换显示桌面"}
    elif act == "lock_screen":
        launch_shell_on_user_desktop("rundll32.exe user32.dll,LockWorkStation")
        return {"status": "success", "message": "已锁定电脑屏幕"}
    elif act in ["volume_up", "volume_down", "mute"]:
        adjust_windows_volume(act)
        return {"status": "success", "message": f"已为您调节系统音量: {act}"}
    return {"status": "unknown_action", "message": f"未知的系统动作: {action}"}


def execute_get_pc_status(query_type: str = "all") -> Dict[str, Any]:
    qt = (query_type or "all").lower().strip()
    result = {"status": "success"}

    # 1. Running applications
    running_apps = []
    app_map = {
        "weixin.exe": "微信", "wechat.exe": "微信",
        "qq.exe": "QQ", "msedge.exe": "Edge浏览器",
        "chrome.exe": "Chrome浏览器", "notepad.exe": "记事本",
        "potplayer.exe": "PotPlayer播放器", "potplayermini64.exe": "PotPlayer播放器",
        "vlc.exe": "VLC播放器", "xmp.exe": "迅雷影音", "thunder.exe": "迅雷影音"
    }
    try:
        import psutil
        for p in psutil.process_iter(['name']):
            pname = (p.info.get('name') or '').lower()
            if pname in app_map and app_map[pname] not in running_apps:
                running_apps.append(app_map[pname])
    except Exception:
        pass
    result["running_apps"] = running_apps

    # 2. Local videos found on desktop and videos folder
    local_videos = []
    exts = (".mp4", ".mkv", ".avi", ".mov")
    for d in [os.path.expanduser("~/Desktop"), os.path.expanduser("~/Videos")]:
        if os.path.exists(d):
            for f in os.listdir(d):
                if f.lower().endswith(exts) and not f.startswith("."):
                    if f not in local_videos:
                        local_videos.append(f)
    result["local_videos"] = local_videos[:8]

    if qt == "videos":
        if local_videos:
            msg = f"为您在电脑上找到了 {len(local_videos)} 个本地视频：{'、'.join(local_videos[:5])}。"
        else:
            msg = "当前桌面和视频库中暂未发现视频文件。"
    elif qt == "apps":
        if running_apps:
            msg = f"当前电脑正在运行：{'、'.join(running_apps)}。"
        else:
            msg = "当前未检测到常用交互软件在运行。"
    else:
        parts = []
        if running_apps:
            parts.append(f"正在运行的应用有：{'、'.join(running_apps)}")
        if local_videos:
            parts.append(f"检测到桌面与本地视频：{'、'.join(local_videos[:4])}")
        msg = "；".join(parts) if parts else "电脑当前运行正常，暂无活跃的多媒体播放任务。"

    result["message"] = msg
    return result


def execute_pc_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    name_clean = name.strip().lower()
    if "play_video" in name_clean or name_clean == "video":
        return execute_play_video(args.get("keyword", "") or args.get("name", "") or "火车历史")
    elif "open_software" in name_clean or name_clean == "app":
        return execute_open_software(args.get("name", "") or args.get("keyword", "") or "微信")
    elif name_clean == "close_video":
        return execute_close_video()
    elif "pc_status" in name_clean or "status" in name_clean:
        return execute_get_pc_status(args.get("query_type", "all"))
    elif name_clean == "system_control":
        return execute_system_control(args.get("action", ""))
    elif "volume" in name_clean or "speaker" in name_clean:
        vol = args.get("volume")
        act = str(args.get("action", "")).lower()
        if "down" in act:
            adjust_windows_volume("down")
            msg = "已为您调小音量"
        elif "mute" in act or vol == 0:
            adjust_windows_volume("mute")
            msg = "已为您开启静音"
        elif "up" in act:
            adjust_windows_volume("up")
            msg = "已为您调大音量"
        elif vol is not None:
            msg = f"已将音量设为 {vol}%"
        else:
            adjust_windows_volume("up")
            msg = "已为您调节音量"
        return {"status": "success", "volume": vol, "message": f"好的，{msg}。"}
    return {"status": "error", "message": f"未定义的 PC 工具: {name}"}
