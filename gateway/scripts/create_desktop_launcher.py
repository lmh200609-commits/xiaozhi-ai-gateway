#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""向下兼容快捷方式生成代理"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import setup_desktop_launcher

if __name__ == "__main__":
    setup_desktop_launcher.main()
