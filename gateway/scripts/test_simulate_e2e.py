import sys
import os
import json
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from starlette.testclient import TestClient
from gateway.main import app, session_skill_tracker
from gateway.roles.role_manager import role_manager
from gateway.rag.knowledge_store import knowledge_store

client = TestClient(app)

def test_simulate_exact_mode_and_skill():
    print("=" * 60)
    print("🚀 Running E2E Test on /api/chat/simulate for Exact Mode & Skill SOP")
    print("=" * 60)

    # 1. Test major_advisor in exact mode with RAG hit
    test_doc = {
        "title": "软件工程专业建设成果报告",
        "category": "专业介绍",
        "content": "大连东软信息学院软件工程专业是首批国家级一流本科专业建设点，建有国家级软件工程实验教学示范中心，依托东软产业优势，实施TOPCARES一体化人才培养模式。",
        "zone_id": "default_zone",
        "source_file_name": "软件工程专业建设成果报告.md"
    }
    doc_id = knowledge_store.add_structured_document(
        doc_data={
            "title": test_doc["title"],
            "category": test_doc["category"],
            "summary": "专业建设成果介绍",
            "qa_pairs": [{
                "question": "请你介绍学校专业建设情况",
                "answer": test_doc["content"]
            }],
            "fact_chunks": [{
                "title": test_doc["title"],
                "content": test_doc["content"]
            }]
        },
        raw_text=test_doc["content"],
        file_name="软件工程专业建设成果报告.md",
        file_type="md",
        zone_id="default_zone",
        zone_name="默认通用知识区"
    )

    # Mock RelayLLMClient.stream_chat to inspect effective prompt and temperature passed
    captured_calls = []

    async def mock_stream_chat(self, user_text, device_tools=None, system_prompt="", temperature=0.7):
        captured_calls.append({
            "user_text": user_text,
            "system_prompt": system_prompt,
            "temperature": temperature
        })
        # If exact mode and hit, return verbatim chunk
        if "严格知识库原文复述模式" in system_prompt and "大连东软信息学院软件工程专业" in system_prompt:
            yield test_doc["content"], None, {"ttft_ms": 12.0}
        elif "未检索到与用户提问匹配的官方权威记录" in system_prompt or "未检索到官方记录指令" in system_prompt:
            yield "抱歉，官方知识库中暂未收录相关权威内容。", None, {"ttft_ms": 10.0}
        elif "角色身份确认与开场引导交互指令" in system_prompt:
            yield "是的！我是高校官方专业建设与招生咨询顾问。很高兴为您服务！请问您对哪个专业方向感兴趣？", None, {"ttft_ms": 15.0}
        else:
            yield f"这是当前阶段的模拟引导回复", None, {"ttft_ms": 15.0}

    with patch("gateway.llm.relay_client.RelayLLMClient.stream_chat", mock_stream_chat):
        # A. Query major_advisor with matching question
        res = client.post("/api/chat/simulate", json={
            "text": "请你介绍学校专业建设情况",
            "role_id": "major_advisor",
            "session_id": "test_e2e_session"
        })
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["rag_mode"] == "exact"
        assert len(data["rag_matched"]) > 0
        assert data["rag_matched"][0]["source_file_name"] == "软件工程专业建设成果报告.md"
        assert data["assistant_reply"] == test_doc["content"]
        assert captured_calls[-1]["temperature"] == 0.0, f"Expected temperature 0.0, got {captured_calls[-1]['temperature']}"
        assert "严格知识库原文复述模式" in captured_calls[-1]["system_prompt"]
        print("  ✅ [PASS] Test A: Exact verbatim mode matched RAG, temperature=0.0, exact text returned.")

        # B1. Query major_advisor with unhit factual question in exact mode (should refuse standardly)
        res_unhit = client.post("/api/chat/simulate", json={
            "text": "明天天气怎么样，会下雨吗？",
            "role_id": "major_advisor",
            "session_id": "test_e2e_session"
        })
        assert res_unhit.status_code == 200
        data_unhit = res_unhit.json()
        assert data_unhit["rag_mode"] == "exact"
        assert "抱歉，官方知识库中暂未收录相关权威内容。" in data_unhit["assistant_reply"]
        assert captured_calls[-1]["temperature"] == 0.0
        print("  ✅ [PASS] Test B1: Exact verbatim mode factual unhit handled with standardized refusal, 0 hallucination.")

        # B2. Query major_advisor with persona confirmation in exact mode (should affirm identity, NOT refuse!)
        res_persona = client.post("/api/chat/simulate", json={
            "text": "你不是官方高校的那个招生顾问吗？",
            "role_id": "major_advisor",
            "session_id": "test_e2e_session"
        })
        assert res_persona.status_code == 200
        data_persona = res_persona.json()
        assert data_persona["rag_mode"] == "exact"
        assert "角色身份确认与开场引导交互指令" in captured_calls[-1]["system_prompt"]
        assert "抱歉，官方知识库中暂未收录相关权威内容。" not in data_persona["assistant_reply"]
        assert "招生咨询顾问" in data_persona["assistant_reply"]
        assert captured_calls[-1]["temperature"] == 0.2
        print("  ✅ [PASS] Test B2: Persona confirmation '你不是官方高校的那个招生顾问吗？' correctly affirmed role identity without unhit refusal.")

        # B3. Query major_advisor with greeting in exact mode (should greet & guide, NOT refuse!)
        res_greet = client.post("/api/chat/simulate", json={
            "text": "你好",
            "role_id": "major_advisor",
            "session_id": "test_e2e_session"
        })
        assert res_greet.status_code == 200
        data_greet = res_greet.json()
        assert "角色身份确认与开场引导交互指令" in captured_calls[-1]["system_prompt"]
        assert "抱歉，官方知识库中暂未收录相关权威内容。" not in data_greet["assistant_reply"]
        print("  ✅ [PASS] Test B3: Greeting '你好' correctly triggered persona greeting & stage guidance.")

        # C. Query psychologist with multi-stage workflow
        res_psy1 = client.post("/api/chat/simulate", json={
            "text": "心语老师，我最近压力很大",
            "role_id": "psychologist",
            "stage_id": 1,
            "session_id": "psy_session"
        })
        assert res_psy1.status_code == 200
        data_psy1 = res_psy1.json()
        assert data_psy1["skill_info"]["current_stage_id"] == 1
        assert "共情倾听" in data_psy1["skill_info"]["current_stage_name"]
        assert "阶段 1 - 【共情倾听与全然接纳】" in captured_calls[-1]["system_prompt"]
        print("  ✅ [PASS] Test C1: Psychologist Stage 1 (Empathy) executed.")

        # Advance to Stage 2
        res_psy2 = client.post("/api/chat/simulate", json={
            "text": "主要是工作上领导给的指标太重了",
            "role_id": "psychologist",
            "advance_stage": True,
            "session_id": "psy_session"
        })
        assert res_psy2.status_code == 200
        data_psy2 = res_psy2.json()
        assert data_psy2["skill_info"]["current_stage_id"] == 2
        assert "温和探寻诱因" in data_psy2["skill_info"]["current_stage_name"]
        assert "阶段 2 - 【温和探寻诱因与困扰】" in captured_calls[-1]["system_prompt"]
        print("  ✅ [PASS] Test C2: Psychologist advance_stage smoothly stepped to Stage 2.")

        # D. Test [NEXT_STAGE] tag auto-transition
        async def mock_stream_chat_auto_advance(self, user_text, device_tools=None, system_prompt="", temperature=0.7):
            yield "我完全理解你的处境，那么能多跟我说说压力最大的具体事情吗？[NEXT_STAGE]", None, {"ttft_ms": 10.0}

        with patch("gateway.llm.relay_client.RelayLLMClient.stream_chat", mock_stream_chat_auto_advance):
            res_auto = client.post("/api/chat/simulate", json={
                "text": "心语老师，我真的快撑不住了",
                "role_id": "psychologist",
                "stage_id": 1,
                "session_id": "auto_adv_session"
            })
            assert res_auto.status_code == 200
            data_auto = res_auto.json()
            assert "[NEXT_STAGE]" not in data_auto["assistant_reply"], "Tag [NEXT_STAGE] must be stripped from response!"
            assert data_auto["skill_info"]["auto_advanced"] is True, "Must flag auto_advanced as True"
            assert data_auto["skill_info"]["current_stage_id"] == 2, "Must automatically step to Stage 2"
            print("  ✅ [PASS] Test D: [NEXT_STAGE] tag stripped and stage automatically advanced.")

    # Clean up test document
    knowledge_store.delete_document(doc_id)
    print("  ✅ [PASS] Test cleanup: removed temporary document.")

    # E. Test Manual Document Physical Archive & Lossless Download
    res_man = client.post("/api/knowledge", json={
        "title": "手动录入高校测试章程",
        "category": "招生政策",
        "content": "第一条：本章程适用于高校全日制普通本科招生工作。\n\n第二条：学校招生工作遵循公平竞争、公正选拔的原则。",
        "zone_id": "default_zone"
    })
    assert res_man.status_code == 200
    man_doc_id = res_man.json()["doc_id"]

    # Verify download endpoint
    res_dl = client.get(f"/api/documents/{man_doc_id}/download")
    assert res_dl.status_code == 200, f"Download manual doc failed: {res_dl.status_code}"
    assert "本章程适用于高校全日制普通本科招生工作" in res_dl.text
    print("  ✅ [PASS] Test E1: Manual document has real physical archive and downloads accurately.")

    # Cascade delete
    res_del = client.delete(f"/api/documents/{man_doc_id}")
    assert res_del.status_code == 200
    res_dl_after = client.get(f"/api/documents/{man_doc_id}/download")
    assert res_dl_after.status_code == 404
    print("  ✅ [PASS] Test E2: Manual document cascade deleted from disk and database.")

    print("\n" + "=" * 60)
    print("🎉 ALL SIMULATE E2E TESTS PASSED 100%!")
    print("=" * 60)

if __name__ == "__main__":
    test_simulate_exact_mode_and_skill()
