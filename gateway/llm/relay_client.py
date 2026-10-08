import json
import time
import httpx
from typing import AsyncGenerator, Optional
from gateway.config import config

class RelayLLMClient:
    """
    Connects to the user's Gemini relay gateway (default: http://localhost:8000/v1).
    Supports streaming chat completions, TTFT measurement, and MCP tool declarations.
    """
    def __init__(self):
        self.history = []

    def reset_history(self):
        self.history = []

    def add_message(self, role: str, content: str):
        self.history.append({"role": role, "content": content})
        # Keep last 10 rounds to avoid token overflow
        if len(self.history) > 20:
            self.history = self.history[-20:]

    def build_mcp_tools(self, tools_list: list) -> list:
        """Converts Xiaozhi ESP32 device tools & PC tools into OpenAI function calling format."""
        openai_tools = []
        for tool in tools_list:
            # If already in standard OpenAI tool format
            if isinstance(tool, dict) and tool.get("type") == "function":
                openai_tools.append(tool)
                continue

            name = tool.get("name")
            desc = tool.get("description", "")
            params = tool.get("parameters", {})
            
            # Convert property list to JSON Schema properties
            properties = {}
            required = []
            if isinstance(params, dict):
                if "required" in params and isinstance(params["required"], list):
                    required.extend(params["required"])

                if "properties" in params and isinstance(params["properties"], dict):
                    for prop_name, prop_data in params["properties"].items():
                        prop_type = prop_data.get("type", "string")
                        properties[prop_name] = {
                            "type": prop_type,
                            "description": prop_data.get("description", "")
                        }
                        if prop_data.get("required", False) and prop_name not in required:
                            required.append(prop_name)

            openai_tools.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": desc,
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required
                    }
                }
            })
        return openai_tools

    async def stream_chat(
        self,
        user_text: str,
        device_tools: Optional[list] = None,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None
    ) -> AsyncGenerator[tuple[str, Optional[dict], dict], None]:
        """
        Sends user text to the relay and streams back tokens.
        Yields: (token_str, tool_call_dict, metrics_dict)
        """
        self.add_message("user", user_text)

        effective_prompt = system_prompt if system_prompt is not None else config.system_prompt
        effective_temp = temperature if temperature is not None else config.temperature

        messages = [{"role": "system", "content": effective_prompt}]
        messages.extend(self.history)

        payload = {
            "model": config.model_name,
            "messages": messages,
            "temperature": effective_temp,
            "stream": True
        }

        if device_tools:
            tools = self.build_mcp_tools(device_tools)
            if tools:
                payload["tools"] = tools

        headers = {
            "Authorization": f"Bearer {config.relay_api_key}",
            "Content-Type": "application/json"
        }

        t_start = time.time()
        ttft_ms = 0.0
        first_token = True
        full_reply = ""
        tool_calls = []

        if not config.relay_api_key or config.relay_api_key in ("sk-default", "none"):
            yield "[LLM] 未配置大模型 API Key。请在控制台【系统配置】页面填入您的 DeepSeek 或兼容大模型 API 密钥。", None, {"ttft_ms": 0, "total_ms": 0}
            return

        url = config.get_chat_url()

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                async with client.stream("POST", url, json=payload, headers=headers) as response:
                    if response.status_code != 200:
                        err_body = await response.aread()
                        err_text = err_body.decode('utf-8', errors='replace')
                        if response.status_code == 401:
                            err_msg = f"[LLM 认证失败 401] 您的 API Key 无效或已过期，请在网关配置中检查填写的 Key。"
                        elif response.status_code == 402:
                            err_msg = f"[LLM 余额不足 402] 您的 API 账户余额已耗尽，请前往对应服务商充值。"
                        elif response.status_code == 429:
                            err_msg = f"[LLM 频率超限 429] 触发服务商流控或并发限制，请稍后重试。"
                        else:
                            err_msg = f"[LLM] 请求异常 HTTP {response.status_code}: {err_text}"
                        yield err_msg, None, {"ttft_ms": 0, "total_ms": 0}
                        return

                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data: "):
                            continue
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break

                        try:
                            chunk = json.loads(data_str)
                            choice = chunk.get("choices", [{}])[0]
                            delta = choice.get("delta", {})

                            # 1. Content streaming
                            content = delta.get("content")
                            if content:
                                if first_token:
                                    ttft_ms = (time.time() - t_start) * 1000.0
                                    first_token = False
                                full_reply += content
                                yield content, None, {"ttft_ms": ttft_ms}

                            # 2. Tool call streaming
                            delta_tool_calls = delta.get("tool_calls")
                            if delta_tool_calls:
                                for tc in delta_tool_calls:
                                    tc_id = tc.get("id")
                                    fn = tc.get("function", {})

                                    target_call = None
                                    if tc_id:
                                        for existing in tool_calls:
                                            if existing.get("id") == tc_id:
                                                target_call = existing
                                                break
                                        if not target_call:
                                            target_call = {"id": tc_id, "name": "", "arguments": ""}
                                            tool_calls.append(target_call)
                                    elif tool_calls:
                                        target_call = tool_calls[-1]
                                    else:
                                        target_call = {"id": "", "name": "", "arguments": ""}
                                        tool_calls.append(target_call)

                                    if fn.get("name"):
                                        target_call["name"] = fn["name"]
                                    if fn.get("arguments"):
                                        target_call["arguments"] += fn["arguments"]

                        except Exception as e:
                            continue

            except Exception as e:
                err_msg = f"连接大模型中转网关异常: {e}"
                yield err_msg, None, {"ttft_ms": 0, "total_ms": 0}
                return

        total_ms = (time.time() - t_start) * 1000.0
        if full_reply:
            self.add_message("assistant", full_reply)
        elif tool_calls:
            tools_summary = ", ".join([tc.get("name", "") for tc in tool_calls if tc.get("name")])
            self.add_message("assistant", f"已调用工具执行操作: {tools_summary}")

        # Emit any collected tool calls
        for tc in tool_calls:
            name = tc.get("name", "").strip()
            if name:
                try:
                    args = json.loads(tc.get("arguments", "{}"))
                except Exception:
                    args = {}
                yield "", {"name": name, "arguments": args}, {"ttft_ms": ttft_ms, "total_ms": total_ms}
