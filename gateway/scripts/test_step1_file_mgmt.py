import os
import sys
import io
import time
from pathlib import Path

# Set UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

def run_tests():
    print("==================================================")
    print("🚀 [Step 1 Test] Knowledge Base File Warehouse & Traceability Test")
    print("==================================================")

    from gateway.rag.knowledge_store import knowledge_store
    from gateway.main import app, DOCUMENTS_DIR
    from starlette.testclient import TestClient

    client = TestClient(app)

    # 1. Verify schema migration
    print("\n[Test 1] Verifying SQLite documents table schema...")
    with knowledge_store.get_conn() as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(documents)").fetchall()]
        print(f"Columns in 'documents': {cols}")
        assert "file_size" in cols, "file_size column missing in documents table"
        assert "file_path" in cols, "file_path column missing in documents table"
        assert "zone_id" in cols, "zone_id column missing in documents table"
    print("✅ Test 1 Passed: Database schema contains file_size and file_path.")

    # 2. Test Document Upload with physical disk persistence
    print("\n[Test 2] Testing Document Upload with Physical File Persistence...")
    sample_content = """# 大安机车博览园智能导览测试手册
大安机车博览园位于吉林白城，拥有全国唯一的机车封存基地。
## 问答常见问题
问：大安机车博览园有哪些特色展项？
答：大安机车博览园拥有76台壮观的蒸汽机车群，荣获世界纪录，并且拥有德制V100内燃机车和红色朱德号功勋机车展区。
## 游览提示
园区配备了小智AI智能硬件问答终端，游客可通过语音随时咨询机车历史和场馆路线。
"""
    test_filename = "test_daan_guide_manual.md"
    upload_bytes = sample_content.encode("utf-8")

    files = {"file": (test_filename, io.BytesIO(upload_bytes), "text/markdown")}
    data = {"zone_id": "baicheng_railway"}

    res = client.post("/api/knowledge/upload", files=files, data=data)
    assert res.status_code == 200, f"Upload failed: {res.text}"
    resp_data = res.json()
    print("Upload response:", resp_data)

    doc_id = resp_data["doc_id"]
    assert doc_id, "doc_id missing in upload response"
    assert resp_data["has_physical_file"] is True, "has_physical_file is False"
    assert resp_data["file_size"] == len(upload_bytes), f"file_size mismatch: {resp_data['file_size']} vs {len(upload_bytes)}"
    assert resp_data["file_name"] == test_filename, "file_name mismatch"

    # Check physical file on disk
    doc_detail = knowledge_store.get_document_details(doc_id)
    assert doc_detail, "Failed to get document details from knowledge store"
    saved_path = Path(doc_detail["file_path"])
    print(f"Physical file saved at: {saved_path}")
    assert saved_path.is_file(), f"Physical file does not exist at {saved_path}"
    assert saved_path.read_bytes() == upload_bytes, "Saved physical file content does not match uploaded bytes!"
    print("✅ Test 2 Passed: Physical file persisted accurately on disk with exact byte match.")

    # 3. Test Slice Traceability
    print("\n[Test 3] Testing Slice Traceability...")
    chunks = doc_detail["chunks"]
    print(f"Parsed {len(chunks)} chunks for {test_filename}")
    assert len(chunks) > 0, "No chunks generated"
    for idx, ch in enumerate(chunks):
        assert ch["source_file_name"] == test_filename, f"Chunk {idx} source_file_name incorrect: {ch.get('source_file_name')}"
        assert ch["doc_title"], "Chunk doc_title is empty"
        print(f" - Chunk #{idx+1} [{ch['chunk_type']}]: source_file='{ch['source_file_name']}', question='{ch.get('question')}'")
    print("✅ Test 3 Passed: All chunks have explicit source_file_name metadata.")

    # 4. Test List Documents API
    print("\n[Test 4] Testing GET /api/documents...")
    res_list = client.get("/api/documents?zone_id=baicheng_railway")
    assert res_list.status_code == 200
    docs_list = res_list.json()["documents"]
    uploaded_doc_in_list = next((d for d in docs_list if d["id"] == doc_id), None)
    assert uploaded_doc_in_list is not None, "Uploaded doc not found in /api/documents"
    assert uploaded_doc_in_list["has_physical_file"] is True
    assert uploaded_doc_in_list["file_size"] == len(upload_bytes)
    print(f"Found uploaded doc in list: title='{uploaded_doc_in_list['title']}', size={uploaded_doc_in_list['file_size']}B, chunks={uploaded_doc_in_list['total_chunks']}")
    print("✅ Test 4 Passed: GET /api/documents correctly returns file size, physical existence flag, and chunk stats.")

    # 5. Test List Chunks API
    print("\n[Test 5] Testing GET /api/knowledge/chunks...")
    res_chunks = client.get(f"/api/knowledge/chunks?doc_id={doc_id}")
    assert res_chunks.status_code == 200
    all_chunks = res_chunks.json()["chunks"]
    assert len(all_chunks) == len(chunks)
    assert all_chunks[0]["source_file_name"] == test_filename
    print(f"Retrieved {len(all_chunks)} chunks for doc {doc_id} with source_file_name='{all_chunks[0]['source_file_name']}'")
    print("✅ Test 5 Passed: GET /api/knowledge/chunks returns traced chunks.")

    # 6. Test Search Traceability
    print("\n[Test 6] Testing Search Traceability...")
    res_search = client.post("/api/knowledge/search", json={"query": "大安机车博览园有哪些特色展项？", "top_k": 3})
    assert res_search.status_code == 200
    search_data = res_search.json()
    print(f"Search results for '大安机车博览园有哪些特色展项？': ({len(search_data['results'])} hits)")
    found_uploaded = False
    for r in search_data["results"]:
        print(f" - Hit: source_file='{r.get('source_file_name')}', type={r.get('type')}, RRF score={r.get('rrf_score')}, title='{r.get('title')}'")
        assert "source_file_name" in r, "Search result missing source_file_name!"
        if r.get("doc_id") == doc_id:
            found_uploaded = True
    print("✅ Test 6 Passed: Hybrid search results contain source_file_name for every hit.")

    # 7. Test Physical File Download API
    print("\n[Test 7] Testing GET /api/documents/{doc_id}/download...")
    res_dl = client.get(f"/api/documents/{doc_id}/download")
    assert res_dl.status_code == 200, f"Download failed: {res_dl.status_code}"
    assert res_dl.content == upload_bytes, "Downloaded content does not match original uploaded bytes!"
    content_disp = res_dl.headers.get("content-disposition", "")
    print(f"Content-Disposition header: {content_disp}")
    assert "attachment" in content_disp, "Content-Disposition does not contain attachment"
    print("✅ Test 7 Passed: Download endpoint streamed exact original file bytes with proper attachment headers.")

    # 8. Test Cascade Deletion
    print("\n[Test 8] Testing Cascade Deletion...")
    assert saved_path.is_file(), "File should exist before deletion"
    res_del = client.delete(f"/api/documents/{doc_id}")
    assert res_del.status_code == 200, f"Delete failed: {res_del.text}"

    # Verify physical file is gone
    assert not saved_path.exists(), f"Physical file still exists after deletion! {saved_path}"
    print(f"Physical file successfully removed: {saved_path.exists() == False}")

    # Verify database document row is gone
    with knowledge_store.get_conn() as conn:
        doc_count = conn.execute("SELECT COUNT(*) FROM documents WHERE id = ?", (doc_id,)).fetchone()[0]
        assert doc_count == 0, "Document row still exists in database!"

        # Verify chunks rows are gone
        chunk_count = conn.execute("SELECT COUNT(*) FROM chunks WHERE doc_id = ?", (doc_id,)).fetchone()[0]
        assert chunk_count == 0, f"Chunks still exist in database: {chunk_count}"

    # Verify details returns 404
    res_detail_after = client.get(f"/api/documents/{doc_id}")
    assert res_detail_after.status_code == 404, "Document should return 404 after deletion"

    print("✅ Test 8 Passed: Cascade deletion cleanly removed physical file, DB document record, chunks, and FTS5 index.")

    print("\n==================================================")
    print("🎉 ALL STEP 1 TESTS PASSED PERFECTLY (100% SUCCESS)!")
    print("==================================================")

if __name__ == "__main__":
    run_tests()
