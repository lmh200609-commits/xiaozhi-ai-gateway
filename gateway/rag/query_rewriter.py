"""
Context-Aware Query Rewriting & Multi-Turn Coreference Resolution for Voice Dialogues.
Resolves pronouns ('它', '这辆车', '那个展厅') and elliptical follow-ups within < 1ms.
"""
import re
from typing import List, Dict, Optional

class VoiceQueryRewriter:
    def __init__(self):
        # Pronouns commonly used in spoken Chinese museum inquiries
        self.pronoun_pattern = re.compile(r"(它|这台|这辆|这个|那台|那个|此车|该机车|该展项)")

        # Common ASR homophone and typo corrections for voice hardware
        self.asr_typos = [
            (re.compile(r"毛泽东浩"), "毛泽东号"),
            (re.compile(r"朱德浩"), "朱德号"),
            (re.compile(r"黄继光浩"), "黄继光号"),
            (re.compile(r"前进浩"), "前进号"),
            (re.compile(r"东风浩"), "东风号"),
            (re.compile(r"韶山浩"), "韶山号"),
            (re.compile(r"复兴浩"), "复兴号"),
            (re.compile(r"(白城火车园|白城机车园|大安火车园|大安机车园|大安博览园)"), "大安机车博览园"),
        ]

    def extract_recent_entity(self, history: List[Dict[str, str]], enable_railway: bool = True) -> Optional[str]:
        """Finds the most recent railway entity mentioned in previous conversation rounds if enabled."""
        if not enable_railway:
            return None
        from gateway.rag.entity_graph import entity_graph

        for msg in reversed(history[-4:]):
            content = msg.get("content", "")
            matched = entity_graph.match_entities(content)
            if matched:
                return matched[0].name
        return None

    def normalize_query(self, query: str, enable_railway: bool = True) -> str:
        """Corrects common Chinese speech-to-text phonetic misrecognitions if railway enabled."""
        q = query
        if enable_railway:
            for pattern, replacement in self.asr_typos:
                q = pattern.sub(replacement, q)
        return q

    def rewrite_query(self, user_query: str, history: List[Dict[str, str]] = None, enable_railway: bool = True) -> str:
        """
        Rewrites conversational voice query into an explicit, search-optimized query.
        Execution latency is < 0.5ms using fast rule-based entity resolution.
        """
        q = self.normalize_query(user_query.strip(), enable_railway=enable_railway)

        if not history or not enable_railway:
            return q

        recent_entity = self.extract_recent_entity(history, enable_railway=enable_railway)
        if not recent_entity:
            return q

        # Case 1: Direct pronoun replacement ("它是什么时候造的？" -> "毛泽东号机车是什么时候造的？")
        if self.pronoun_pattern.search(q):
            rewritten = self.pronoun_pattern.sub(recent_entity, q)
            print(f"[Query Rewriter] Coreference resolved: '{q}' -> '{rewritten}'")
            return rewritten

        # Case 2: Short elliptical continuation ("多少吨？", "最高时速呢？", "在哪？")
        if len(q) <= 6 and not any(k in q for k in ["你好", "再见", "谢谢", "好的"]):
            rewritten = f"{recent_entity} {q}"
            print(f"[Query Rewriter] Elliptical expanded: '{q}' -> '{rewritten}'")
            return rewritten

        return q

query_rewriter = VoiceQueryRewriter()
