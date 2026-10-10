#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小智 AI 语音网关 - 脚本入口 (向下兼容代理)
自动定位工程根目录并调起统一入口 run.py
"""
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
os.chdir(PROJECT_ROOT)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import run

if __name__ == "__main__":
    run.main()
