#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小智 AI 网关 - Agent Skill 技能与工作流文件管理引擎 (SkillManager)
================================================================================
支持标准 Agent Skill 文件系统：
  1. 支持直接上传/下载标准 Markdown (.md / .skill.md) 与 JSON (.skill.json) 技能文件；
  2. 自动从 GitHub 或社区 Skill 文件中解析阶段流、元数据与 SOP 指令；
  3. 支持角色快速挂载/卸载 Skill，支持在线 Markdown 源码直读直写与一键导出；
  4. 物理归档落盘在 gateway/data/skills/ 目录下，透明可追溯。
================================================================================
"""

import os
import re
import json
import uuid
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

from gateway.config import DATA_DIR
SKILLS_DIR = DATA_DIR / "skills"

# 内置标准预设 Skill 模板 (符合真实 Agent SKILL.md 规范)
PRESET_SKILLS = [
    {
        "id": "major_advisor",
        "filename": "major_advisor.skill.md",
        "name": "四阶段高校招生与专业咨询SOP",
        "description": "从意向破冰到专业详述、就业前景及报考指导的标准引导式流程",
        "author": "xiaozhi-official",
        "version": "1.0.0",
        "stages": [
            {
                "stage_id": 1,
                "name": "考生意向与兴趣探索",
                "goal": "了解考生的文理科类、高考分数区间及感兴趣的专业大类",
                "instruction": "热情询问考生关注的学科方向与未来职业憧憬，引导明确目标。",
                "exit_condition": "当考生明确提出具体意向专业或咨询主题时过渡。"
            },
            {
                "stage_id": 2,
                "name": "专业建设与特色详解",
                "goal": "结合权威资料与培养方案，详述专业的师资力量、优势方向与核心特色",
                "instruction": "详实准确地介绍该专业的建设亮点、实验条件与师资，解答专业相关咨询。",
                "exit_condition": "详尽解答专业特色与建设情况后过渡。"
            },
            {
                "stage_id": 3,
                "name": "就业前景与升学深造剖析",
                "goal": "结合官方数据介绍毕业去向、名企就业率与考研保研通道",
                "instruction": "客观解答就业去向和升学优势，消除考生与家长的顾虑。",
                "exit_condition": "解答完就业前景疑问后过渡。"
            },
            {
                "stage_id": 4,
                "name": "报考填报指导与寄语",
                "goal": "提供投档位次参考、选考科目要求与官方招生办联系方式",
                "instruction": "给予清晰的志愿填报建议，并送上诚挚的高考祝福与迎新寄语。",
                "exit_condition": "完成本轮咨询接待。"
            }
        ]
    },
    {
        "id": "psychologist",
        "filename": "psychologist.skill.md",
        "name": "四阶段心理疏导与情绪修复SOP",
        "description": "基于认知行为与人本主义心理学的引导式专业心理疏导工作流",
        "author": "xiaozhi-official",
        "version": "1.0.0",
        "stages": [
            {
                "stage_id": 1,
                "name": "共情倾听与全然接纳",
                "goal": "接纳来访者当下情绪，给予安全感与陪伴感，严禁急于给建议或说教",
                "instruction": "深切共情对方的感受，用温柔语言肯定其不易，鼓励敞开心扉倾诉更多细节。",
                "exit_condition": "当对方充分宣泄了情绪并确认感到被理解时过渡。"
            },
            {
                "stage_id": 2,
                "name": "温和探寻诱因与困扰",
                "goal": "温和探寻引发情绪风暴的具体生活事件或思维压力源",
                "instruction": "以开放式提问轻柔询问：能跟我多讲讲是什么事情或想法让你觉得这么累吗？",
                "exit_condition": "当明确了引发负面情绪的具体诱因事件后过渡。"
            },
            {
                "stage_id": 3,
                "name": "认知重构与视角转换",
                "goal": "协助打破思维盲区，发现自身被忽视的力量与新的视角",
                "instruction": "肯定对方一路走来的坚韧，启发性提问：如果从另一个视角看，有没有可能...",
                "exit_condition": "当对方情绪明显舒缓并产生新的积极视角时过渡。"
            },
            {
                "stage_id": 4,
                "name": "微小行动与心理着陆",
                "goal": "提供一个此刻就能做的微小放松行动，赋能重拾掌控感",
                "instruction": "引导一个微小的身体着陆（如喝一杯温水、三次腹式深呼吸），并给予坚定的守候承诺。",
                "exit_condition": "完成本轮疏导，保持随时在线守候姿态。"
            }
        ]
    },
    {
        "id": "socratic_tutor",
        "filename": "socratic_tutor.skill.md",
        "name": "三阶段苏格拉底启发式教学SOP",
        "description": "通过反问与启发引导用户自主推导知识，而非直接灌输标准答案",
        "author": "xiaozhi-official",
        "version": "1.0.0",
        "stages": [
            {
                "stage_id": 1,
                "name": "概念澄清与定义探寻",
                "goal": "引导用户用自己的语言表述遇到的问题，明确核心疑点",
                "instruction": "不急于公布结论，而是询问：你能用自己的话说说你认为这个概念的核心是什么吗？",
                "exit_condition": "当用户给出了自己的初步理解或困惑点后过渡。"
            },
            {
                "stage_id": 2,
                "name": "逻辑反例与思维矛盾激活",
                "goal": "抛出轻量反例或边界条件，促使用户发现固有思维中的疏漏",
                "instruction": "友好抛出思维对照：如果遇到某种极端场景，之前的推论是否还成立呢？",
                "exit_condition": "当用户意识到思维局限并开始修正思考时过渡。"
            },
            {
                "stage_id": 3,
                "name": "知识自洽推导与规律升华",
                "goal": "引导用户总结出普适性规律，并给予热情的思维肯定",
                "instruction": "肯定用户的自主思考突破，鼓励总结规律并尝试举一反三。",
                "exit_condition": "完成本轮思维启发互动。"
            }
        ]
    },
    {
        "id": "sales_sop",
        "filename": "sales_sop.skill.md",
        "name": "四阶段客户需求挖掘与促成SOP",
        "description": "专业销售与商务顾问引导工作流，从破冰、痛点剖析到方案呈现",
        "author": "xiaozhi-official",
        "version": "1.0.0",
        "stages": [
            {
                "stage_id": 1,
                "name": "破冰建联与业务背景摸底",
                "goal": "建立专业信任感，轻量了解客户业务规模与行业场景",
                "instruction": "亲切问候，了解客户当前所在的行业与业务现状，营造轻松探讨氛围。",
                "exit_condition": "当客户告知了基本业务场景与当前关注方向时过渡。"
            },
            {
                "stage_id": 2,
                "name": "核心痛点与降本增效诉求挖掘",
                "goal": "深入探寻当前流程中的卡点、痛点及最迫切的改善期望",
                "instruction": "聚焦核心挑战：在现有流程中，团队花费时间最多或最容易出错的环节是哪里？",
                "exit_condition": "当锁定客户的核心痛点与期望指标时过渡。"
            },
            {
                "stage_id": 3,
                "name": "匹配解决方案与价值论证",
                "goal": "针对痛点给出精准方案匹配，论证落地价值与标杆案例",
                "instruction": "针对前序痛点，条理清晰地展示针对性解法与预期成效，杜绝泛泛而谈。",
                "exit_condition": "方案介绍完毕并解答客户疑虑后过渡。"
            },
            {
                "stage_id": 4,
                "name": "推进试用与下一步行动约定",
                "goal": "敲定下一步行动节点（如安排实机演示、免费PoC试用或发送方案材料）",
                "instruction": "明确约定具体跟进动作：我们可以为您开通测试环境体验，您看这周安排如何？",
                "exit_condition": "达成下一步推进共识后结束本轮。"
            }
        ]
    }
]

class SkillManager:
    """
    Agent Skill 统一管理器：
    负责 skills 物理目录文件读写、Markdown 解析与序列化、Skill 库管理。
    """
    def __init__(self):
        SKILLS_DIR.mkdir(parents=True, exist_ok=True)
        self._ensure_preset_skills()

    def _ensure_preset_skills(self):
        """确保预设 Skill 物理文件在磁盘存在"""
        for preset in PRESET_SKILLS:
            filepath = SKILLS_DIR / preset["filename"]
            if not filepath.exists():
                md_content = self.export_to_markdown(preset)
                try:
                    filepath.write_text(md_content, encoding="utf-8")
                except Exception as e:
                    print(f"[SkillManager] Failed to seed preset skill {preset['filename']}: {e}")

    def export_to_markdown(self, skill_data: Dict[str, Any]) -> str:
        """将 Skill 结构转换为标准优雅的 SKILL.md Markdown 格式"""
        name = skill_data.get("name", "未命名技能")
        desc = skill_data.get("description", "")
        author = skill_data.get("author", "user")
        version = skill_data.get("version", "1.0.0")
        stages = skill_data.get("stages", [])

        lines = [
            "---",
            f"name: {name}",
            f"description: {desc}",
            f"version: {version}",
            f"author: {author}",
            "type: agent-workflow-sop",
            "---",
            "",
            f"# {name}",
            "",
            f"> {desc}" if desc else "",
            "",
            "## 流程阶段 (Stages)",
            ""
        ]

        for idx, stage in enumerate(stages, 1):
            stage_name = stage.get("name") or f"阶段 {idx}"
            goal = stage.get("goal", "")
            condition = stage.get("exit_condition", "")
            instruction = stage.get("instruction", "")

            lines.append(f"### 阶段 {idx}: {stage_name}")
            if goal:
                lines.append(f"- **核心目标**: {goal}")
            if condition:
                lines.append(f"- **进入下一阶段条件**: {condition}")
            if instruction:
                lines.append(f"- **阶段执行策略**: {instruction}")
            lines.append("")

        return "\n".join(lines).strip() + "\n"

    def parse_markdown(self, md_text: str, filename: str = "custom.skill.md") -> Dict[str, Any]:
        """
        深度解析 Markdown Skill 文件：
        支持 YAML frontmatter、Markdown 阶段标题、列表属性提取。
        具备高容错性，即使用户上传纯 Prompt Markdown，也能自适应解析。
        """
        name = Path(filename).stem.replace(".skill", "")
        desc = ""
        author = "community"
        version = "1.0.0"
        stages = []

        content = md_text.strip()

        # 1. 尝试解析 YAML Frontmatter
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter = parts[1]
                content = parts[2].strip()
                for line in frontmatter.strip().splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        k = k.strip().lower()
                        v = v.strip().strip('"\'')
                        if k == "name" and v:
                            name = v
                        elif k in ("description", "desc") and v:
                            desc = v
                        elif k == "author" and v:
                            author = v
                        elif k == "version" and v:
                            version = v

        # 2. 如果标题没有在 frontmatter，尝试从第一行一级标题提取
        first_h1 = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
        if first_h1 and name in (Path(filename).stem, "custom"):
            name = first_h1.group(1).strip()

        # 3. 提取阶段 (匹配 ## 阶段 / ### 阶段 / ## Stage / ### Stage)
        stage_blocks = re.split(r'(?m)^#{2,4}\s+(?:阶段\s*\d*[:：]?|Stage\s*\d*[:：]?)\s*', content)
        
        if len(stage_blocks) > 1:
            # 找到各个阶段
            stage_matches = list(re.finditer(r'(?m)^#{2,4}\s+(?:阶段\s*\d*[:：]?|Stage\s*\d*[:：]?)\s*(.+)$', content))
            for i, match in enumerate(stage_matches):
                stage_title = match.group(1).strip()
                # 截取该阶段内容
                start_pos = match.end()
                end_pos = stage_matches[i + 1].start() if i + 1 < len(stage_matches) else len(content)
                block_body = content[start_pos:end_pos].strip()

                goal = ""
                cond = ""
                instr = ""

                # 提取各个字段
                m_goal = re.search(r'(?:[-*]\s*)?(?:\*\*|__)?(?:核心目标|目标|Goal)(?:\*\*|__)?[:：]\s*(.+)', block_body, re.IGNORECASE)
                if m_goal:
                    goal = m_goal.group(1).strip()

                m_cond = re.search(r'(?:[-*]\s*)?(?:\*\*|__)?(?:进入下一阶段条件|流转条件|触发条件|Condition|Exit)(?:\*\*|__)?[:：]\s*(.+)', block_body, re.IGNORECASE)
                if m_cond:
                    cond = m_cond.group(1).strip()

                m_instr = re.search(r'(?:[-*]\s*)?(?:\*\*|__)?(?:阶段执行策略|执行策略|策略|指令|Instruction|Strategy)(?:\*\*|__)?[:：]\s*(.+)', block_body, re.IGNORECASE)
                if m_instr:
                    instr = m_instr.group(1).strip()
                else:
                    # 如果没有显式标记执行策略，把未识别的普通文本作为指令
                    cleaned = re.sub(r'(?:[-*]\s*)?(?:\*\*|__)?(?:核心目标|进入下一阶段条件|流转条件).+?\n', '', block_body).strip()
                    if cleaned:
                        instr = cleaned[:300]

                stages.append({
                    "stage_id": i + 1,
                    "name": stage_title,
                    "goal": goal or f"推进{stage_title}",
                    "instruction": instr or f"执行{stage_title}对应策略与回答。",
                    "exit_condition": cond or "达成阶段目标后自然过渡。"
                })

        # 4. 容错回退：如果是自由文本或普通 Prompt，将其自适应封装为通用 SOP 阶段
        if not stages:
            stages = [
                {
                    "stage_id": 1,
                    "name": "核心技能交互与引导",
                    "goal": desc or f"执行 {name} 核心业务指导",
                    "instruction": content[:600] if content else f"严格依据 {name} 指引执行。",
                    "exit_condition": "完成本轮交互。"
                }
            ]

        # 5. 如果没有 desc，从首段提取
        if not desc:
            paragraphs = [p.strip() for p in content.split("\n\n") if p.strip() and not p.startswith("#")]
            if paragraphs:
                desc = paragraphs[0][:120]

        return {
            "enabled": True,
            "name": name,
            "description": desc or "自定义引导式工作流",
            "author": author,
            "version": version,
            "stages": stages,
            "raw_markdown": md_text
        }

    def parse_json(self, json_text: str, filename: str = "custom.skill.json") -> Dict[str, Any]:
        """解析 JSON 格式的 Skill 文件"""
        data = json.loads(json_text)
        name = data.get("name") or Path(filename).stem
        desc = data.get("description", "")
        stages = data.get("stages", [])
        
        normalized_stages = []
        for idx, s in enumerate(stages, 1):
            normalized_stages.append({
                "stage_id": s.get("stage_id", idx),
                "name": s.get("name") or s.get("title") or f"阶段 {idx}",
                "goal": s.get("goal", ""),
                "instruction": s.get("instruction", ""),
                "exit_condition": s.get("exit_condition") or s.get("condition", "")
            })

        return {
            "enabled": True,
            "name": name,
            "description": desc,
            "stages": normalized_stages,
            "raw_markdown": self.export_to_markdown({
                "name": name,
                "description": desc,
                "stages": normalized_stages
            })
        }

    def import_skill_file(self, filename: str, content_bytes: bytes) -> Dict[str, Any]:
        """将上传的 Skill 文件存储落盘并解析返回结构化数据"""
        SKILLS_DIR.mkdir(parents=True, exist_ok=True)
        # 解码文本
        try:
            text = content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            text = content_bytes.decode("gbk", errors="ignore")

        # 规范化去除多重后缀
        base_stem = Path(filename).name
        for sfx in [".skill.md", ".skill.json", ".md", ".json", ".txt", ".yaml"]:
            if base_stem.lower().endswith(sfx):
                base_stem = base_stem[:-len(sfx)]
                break
        if not base_stem:
            base_stem = f"skill_{int(time.time())}"

        # 确定后缀
        ext = Path(filename).suffix.lower()
        if ext in (".json", ".skill.json"):
            parsed = self.parse_json(text, filename=filename)
            save_name = f"{base_stem}.skill.json"
        else:
            parsed = self.parse_markdown(text, filename=filename)
            save_name = f"{base_stem}.skill.md"

        # 规范化保存文件名
        safe_name = re.sub(r'[^\w\-_\.]', '_', save_name)
        save_path = SKILLS_DIR / safe_name
        
        # 始终保存规范化的 markdown 格式
        markdown_to_save = self.export_to_markdown(parsed)
        save_path.write_text(markdown_to_save, encoding="utf-8")
        parsed["filename"] = safe_name
        return parsed

    def list_skills(self) -> List[Dict[str, Any]]:
        """获取已安装/上传的所有 Skill 技能列表"""
        results = []
        if not SKILLS_DIR.exists():
            return results

        for p in SKILLS_DIR.glob("*"):
            if p.is_file() and p.suffix.lower() in (".md", ".json"):
                try:
                    content = p.read_text(encoding="utf-8")
                    if p.suffix.lower() == ".json":
                        info = self.parse_json(content, filename=p.name)
                    else:
                        info = self.parse_markdown(content, filename=p.name)
                    
                    results.append({
                        "filename": p.name,
                        "name": info.get("name", p.stem),
                        "description": info.get("description", ""),
                        "stage_count": len(info.get("stages", [])),
                        "stages": info.get("stages", []),
                        "file_size": p.stat().st_size,
                        "updated_at": time.strftime("%Y-%m-%d %H:%M", time.localtime(p.stat().st_mtime))
                    })
                except Exception as e:
                    print(f"[SkillManager] Failed to read {p.name}: {e}")

        # 按名称排序
        results.sort(key=lambda x: x["name"])
        return results

    def get_skill(self, skill_id_or_filename: str) -> Optional[Dict[str, Any]]:
        """根据 id 或文件名查询并返回完整的 Skill 字典结构"""
        for sk in self.list_skills():
            if sk.get("id") == skill_id_or_filename or sk.get("filename") == skill_id_or_filename:
                return sk
        for ps in PRESET_SKILLS:
            if ps.get("id") == skill_id_or_filename or ps.get("filename") == skill_id_or_filename:
                return dict(ps)
        return None

    def get_skill_content(self, filename: str) -> Optional[str]:
        """获取特定 Skill 文件的原始内容"""
        p = SKILLS_DIR / filename
        if p.exists() and p.is_file():
            return p.read_text(encoding="utf-8")
        return None

    def delete_skill(self, filename: str) -> bool:
        """删除指定 Skill 文件"""
        p = SKILLS_DIR / filename
        if p.exists() and p.is_file():
            p.unlink()
            return True
        return False

skill_manager = SkillManager()
