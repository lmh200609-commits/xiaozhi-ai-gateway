# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('D:/gemini 工作区/ai硬件工作区/gateway/web', 'gateway/web'), ('D:/gemini 工作区/ai硬件工作区/gateway/data/skills', 'gateway/data/skills')]
binaries = []
hiddenimports = ['uvicorn', 'uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.auto', 'uvicorn.protocols', 'uvicorn.protocols.http', 'uvicorn.protocols.http.auto', 'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto', 'uvicorn.lifespan', 'uvicorn.lifespan.on', 'fastapi', 'starlette', 'multipart', 'aiofiles', 'websockets', 'sherpa_onnx', 'onnxruntime', 'miniaudio', 'edge_tts', 'fastembed', 'PIL', 'PIL.Image', 'PIL._imaging', 'pyogg', 'pyogg.opus', 'pyogg.library_loader', 'tokenizers', 'requests', 'jieba', 'pypdf', 'docx', 'serial', 'esptool', 'esp_idf_nvs_partition_gen', 'sqlite3', 'numpy', 'pydantic', 'httpx', 'gateway.main', 'gateway.config', 'gateway.audio.opus_codec', 'gateway.audio.vad', 'gateway.asr.sense_voice', 'gateway.tts.edge_tts_streamer', 'gateway.llm.relay_client', 'gateway.rag.knowledge_store', 'gateway.rag.fts_engine', 'gateway.rag.embedding', 'gateway.rag.entity_graph', 'gateway.rag.document_parser', 'gateway.rag.knowledge_structurer', 'gateway.rag.zone_manager', 'gateway.rag.video_manager', 'gateway.roles.role_manager', 'gateway.roles.skill_manager', 'gateway.agent.pc_tools', 'gateway.scripts.auto_sync_nvs', 'gateway.scripts.free_port', 'gateway.scripts.download_models']
tmp_ret = collect_all('gateway')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('sherpa_onnx')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('fastembed')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('miniaudio')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('pyogg')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('PIL')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('tokenizers')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['D:/gemini 工作区/ai硬件工作区/run.py'],
    pathex=['D:/gemini 工作区/ai硬件工作区'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'scipy', 'pandas', 'hf_xet', 'unittest', 'pytest', 'IPython'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='XiaozhiGateway',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='XiaozhiGateway',
)
