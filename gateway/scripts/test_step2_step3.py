"""
Automated Verification Test for Step 2 & Step 3:
1. Exact Verbatim RAG Mode (rag_mode == "exact")
   - Exact verbatim prompt enforcement
   - Unhit standard refusal enforcement
   - Temperature forced to 0.0
2. Role Skill Multi-Stage Workflow SOP (skill)
   - Schema validation for preset roles (major_advisor, psychologist)
   - Session stage tracking & progression
   - Dynamic prompt injection per stage
"""

import sys
import os
import json
import time

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from gateway.roles.role_manager import role_manager
from gateway.rag.knowledge_store import knowledge_store
from gateway.main import build_effective_prompt, get_session_stage, session_skill_tracker

def test_roles_schema():
    print("=" * 60)
    print("Test 1: Verify Role Schema & Presets for rag_mode & skill")
    print("=" * 60)

    roles = role_manager.get_roles()
    role_map = {r["id"]: r for r in roles}

    # Verify major_advisor
    assert "major_advisor" in role_map, "major_advisor preset role missing!"
    ma = role_map["major_advisor"]
    assert ma.get("rag_mode") == "exact", f"major_advisor rag_mode must be 'exact', got {ma.get('rag_mode')}"
    assert ma.get("rag_enabled") is True, "major_advisor rag_enabled must be True"
    assert ma.get("temperature") == 0.0, f"major_advisor temperature must be 0.0, got {ma.get('temperature')}"
    assert ma.get("skill") is not None, "major_advisor skill must be defined"
    assert ma["skill"].get("enabled") is True, "major_advisor skill must be enabled"
    assert len(ma["skill"].get("stages", [])) == 4, "major_advisor must have 4 stages"
    print("  [PASS] major_advisor preset verified (rag_mode='exact', 4-stage SOP, temp=0.0)")

    # Verify psychologist
    assert "psychologist" in role_map, "psychologist preset role missing!"
    psy = role_map["psychologist"]
    assert psy.get("rag_mode") == "smart", f"psychologist rag_mode must be 'smart', got {psy.get('rag_mode')}"
    assert psy.get("skill") is not None, "psychologist skill must be defined"
    assert psy["skill"].get("enabled") is True, "psychologist skill must be enabled"
    assert len(psy["skill"].get("stages", [])) == 4, "psychologist must have 4 stages"
    print("  [PASS] psychologist preset verified (rag_mode='smart', 4-stage counseling SOP)")

    # Verify all roles have rag_mode
    for r in roles:
        assert "rag_mode" in r, f"Role {r['id']} missing rag_mode!"
        assert r["rag_mode"] in ("smart", "exact"), f"Invalid rag_mode {r['rag_mode']} in {r['id']}"
    print("  [PASS] All roles have valid rag_mode attribute")

def test_exact_verbatim_prompt():
    print("\n" + "=" * 60)
    print("Test 2: Exact Verbatim Prompt Construction (rag_mode == 'exact')")
    print("=" * 60)

    ma_role = [r for r in role_manager.get_roles() if r["id"] == "major_advisor"][0]

    # Case A: Matched RAG chunk
    mock_rag_matched = [
        {
            "id": "chunk_001",
            "title": "计算机科学与技术专业建设方案",
            "content": "大连东软信息学院计算机科学与技术专业是首批国家级一流本科专业建设点，建有国家级实验教学示范中心，实施TOPCARES一体化人才培养模式。",
            "source_file_name": "学校专业建设白皮书.pdf"
        }
    ]

    prompt_hit = build_effective_prompt(ma_role, "请你介绍学校专业建设情况", mock_rag_matched)
    
    assert "严格知识库原文复述模式" in prompt_hit, "Prompt missing exact mode header!"
    assert "逐字逐句一字不差地复述" in prompt_hit, "Prompt missing verbatim reproduction instruction!"
    assert "严禁自行总结" in prompt_hit, "Prompt missing strict summary prohibition!"
    assert "严禁添加任何开场白、客套寒暄" in prompt_hit, "Prompt missing filler prohibition!"
    assert "大连东软信息学院计算机科学与技术专业" in prompt_hit, "Prompt missing verbatim content injection!"
    print("  [PASS] Case A: RAG Hit produces strict verbatim reproduction instructions")

    # Case B: Unhit RAG
    prompt_unhit = build_effective_prompt(ma_role, "请问明天天气怎么样？", [])
    assert "未检索到与用户提问匹配的官方权威记录" in prompt_unhit or "未检索到官方记录指令" in prompt_unhit, "Prompt missing unhit instruction!"
    assert "抱歉，官方知识库中暂未收录相关权威内容。" in prompt_unhit, "Prompt missing standardized refusal statement!"
    print("  [PASS] Case B: RAG Unhit enforces standardized refusal with zero hallucination")

def test_skill_stage_tracking():
    print("\n" + "=" * 60)
    print("Test 3: Skill SOP Stage Tracking & Prompt Adaptation")
    print("=" * 60)

    psy_role = [r for r in role_manager.get_roles() if r["id"] == "psychologist"][0]
    stages = psy_role["skill"]["stages"]

    session_id = f"test_session_{int(time.time())}"

    # Stage 1 default
    st1 = get_session_stage(session_id, psy_role)
    assert st1["stage_id"] == 1, f"Initial stage should be 1, got {st1['stage_id']}"
    assert "共情倾听" in st1["name"], f"Stage 1 should be empathy, got {st1['name']}"
    
    prompt_st1 = build_effective_prompt(psy_role, "我最近特别焦虑", [], stage=st1)
    assert "【当前执行阶段】：阶段 1 - 【共情倾听与全然接纳】" in prompt_st1, "Prompt should reflect Stage 1"
    assert "接纳来访者当下情绪" in prompt_st1, "Prompt should reflect Stage 1 goal"
    print("  [PASS] Session Stage 1 initialized & prompt injected correctly")

    # Advance to Stage 2
    st2 = get_session_stage(session_id, psy_role, requested_stage_id=2)
    assert st2["stage_id"] == 2, f"Should be stage 2, got {st2['stage_id']}"
    prompt_st2 = build_effective_prompt(psy_role, "是因为最近项目deadline快到了", [], stage=st2)
    assert "【当前执行阶段】：阶段 2 - 【温和探寻诱因与困扰】" in prompt_st2, "Prompt should reflect Stage 2"
    print("  [PASS] Transition to Stage 2 verified")

    # Advance to Stage 3
    st3 = get_session_stage(session_id, psy_role, requested_stage_id=3)
    assert st3["stage_id"] == 3
    prompt_st3 = build_effective_prompt(psy_role, "也许我把期望定得太高了", [], stage=st3)
    assert "【当前执行阶段】：阶段 3 - 【认知重构与视角转换】" in prompt_st3
    print("  [PASS] Transition to Stage 3 verified")

    # Advance to Stage 4
    st4 = get_session_stage(session_id, psy_role, requested_stage_id=4)
    assert st4["stage_id"] == 4
    prompt_st4 = build_effective_prompt(psy_role, "我感觉好一些了", [], stage=st4)
    assert "【当前执行阶段】：阶段 4 - 【微小行动与心理着陆】" in prompt_st4
    print("  [PASS] Transition to Stage 4 verified")

def test_add_and_update_custom_role_with_skill_and_exact_mode():
    print("\n" + "=" * 60)
    print("Test 4: Custom Role Creation & Update with exact mode and Skill")
    print("=" * 60)

    test_role_data = {
        "id": "test_socratic_tutor",
        "name": "苏格拉底哲学导师",
        "emoji": "🏛️",
        "description": "通过启发式提问引导思考",
        "voice": "zh-CN-YunjianNeural",
        "temperature": 0.0,
        "rag_enabled": True,
        "rag_mode": "exact",
        "rag_top_k": 2,
        "system_prompt": "你是苏格拉底导师。严格按资料启发回答。",
        "skill": {
            "enabled": True,
            "name": "苏格拉底启发式教学SOP",
            "description": "三阶段追问流",
            "stages": [
                {
                    "stage_id": 1,
                    "name": "定义澄清",
                    "goal": "澄清核心概念",
                    "instruction": "请学生给出自己的定义",
                    "exit_condition": "明确初步观点后过渡"
                },
                {
                    "stage_id": 2,
                    "name": "反例追问",
                    "goal": "指出思维漏洞",
                    "instruction": "提供反例",
                    "exit_condition": "发现矛盾后过渡"
                }
            ]
        }
    }

    created = role_manager.add_role(test_role_data)
    assert created["id"] == "test_socratic_tutor"
    assert created["rag_mode"] == "exact"
    assert created["skill"]["enabled"] is True
    assert len(created["skill"]["stages"]) == 2
    print("  [PASS] Successfully created custom role with exact mode & skill")

    # Update role
    updated = role_manager.update_role("test_socratic_tutor", {
        "rag_mode": "smart",
        "temperature": 0.5
    })
    assert updated["rag_mode"] == "smart"
    assert updated["temperature"] == 0.5
    print("  [PASS] Successfully updated custom role rag_mode and temperature")

    # Clean up test role
    role_manager.delete_role("test_socratic_tutor")
    remaining_ids = [r["id"] for r in role_manager.get_roles()]
    assert "test_socratic_tutor" not in remaining_ids
    print("  [PASS] Cleaned up test custom role")

if __name__ == "__main__":
    print("🚀 Starting Automated Test for Step 2 & Step 3...\n")
    test_roles_schema()
    test_exact_verbatim_prompt()
    test_skill_stage_tracking()
    test_add_and_update_custom_role_with_skill_and_exact_mode()
    print("\n" + "=" * 60)
    print("🎉 ALL STEP 2 & STEP 3 TESTS PASSED PERFECTLY (100% SUCCESS)!")
    print("=" * 60)
