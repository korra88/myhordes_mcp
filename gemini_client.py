import os
import asyncio
import json
from pathlib import Path
from dotenv import load_dotenv
import google.generativeai as genai
from google.generativeai.types import content_types
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.styles import Style

# Load environment variables
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("Error: GEMINI_API_KEY not found in environment variables.")
    exit(1)

genai.configure(api_key=GEMINI_API_KEY)

TIPS_DIR = Path(__file__).parent / "tips"
PERSONALITY_FILE = Path(__file__).parent / "AGENT-PERSONALITY.md"

PROMPT_STYLE = Style.from_dict({
    "prompt": "ansiyellow bold",
})


def load_system_prompt() -> str:
    """Load persona + all tips files into a single system prompt."""
    parts = []
    if PERSONALITY_FILE.exists():
        parts.append(PERSONALITY_FILE.read_text())
    for tips_file in sorted(TIPS_DIR.glob("*.md")):
        parts.append(tips_file.read_text())
    return "\n\n---\n\n".join(parts)


def _clean_schema(schema: dict) -> dict:
    """Convert JSON Schema to Gemini-compatible Schema (uppercase types, no unsupported fields)."""
    UNSUPPORTED = {"default", "title", "additionalProperties", "$schema"}
    TYPE_MAP = {
        "string": "STRING",
        "integer": "INTEGER",
        "number": "NUMBER",
        "boolean": "BOOLEAN",
        "array": "ARRAY",
        "object": "OBJECT",
    }
    cleaned = {}
    for k, v in schema.items():
        if k in UNSUPPORTED:
            continue
        if k == "type" and isinstance(v, str):
            cleaned[k] = TYPE_MAP.get(v, v.upper())
        else:
            cleaned[k] = v
    if "properties" in cleaned:
        cleaned["properties"] = {
            k: _clean_schema(v) for k, v in cleaned["properties"].items()
        }
    if "items" in cleaned and isinstance(cleaned["items"], dict):
        cleaned["items"] = _clean_schema(cleaned["items"])
    return cleaned


def mcp_tool_to_gemini_declaration(mcp_tool):
    """Convert an MCP tool to Gemini FunctionDeclaration format."""
    return {
        "name": mcp_tool.name,
        "description": mcp_tool.description,
        "parameters": _clean_schema(mcp_tool.inputSchema),
    }


async def handle_function_calls(session: ClientSession, response, chat):
    """Iteratively handle all function calls until Gemini returns a text response."""
    while True:
        parts = response.candidates[0].content.parts
        tool_calls = [p for p in parts if p.function_call.name]
        if not tool_calls:
            break

        tool_responses = []
        for part in tool_calls:
            tool_name = part.function_call.name
            tool_args = dict(part.function_call.args)

            print(f"\n  [tool] {tool_name}({json.dumps(tool_args)})")

            try:
                result = await session.call_tool(tool_name, tool_args)
                tool_output = "\n".join(
                    c.text for c in result.content if hasattr(c, "text")
                )
                tool_responses.append({
                    "function_response": {
                        "name": tool_name,
                        "response": {"result": tool_output},
                    }
                })
            except Exception as e:
                tool_responses.append({
                    "function_response": {
                        "name": tool_name,
                        "response": {"error": str(e)},
                    }
                })

        response = chat.send_message(
            content_types.to_contents({"role": "function", "parts": tool_responses})
        )

    return response


async def run_gemini_client():
    server_params = StdioServerParameters(
        command=str(Path(__file__).parent / ".venv" / "bin" / "python"),
        args=["main.py"],
        env=dict(os.environ),
    )

    print("Starting MyHordes MCP Server...")

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            mcp_tools_list = await session.list_tools()
            gemini_tools = [mcp_tool_to_gemini_declaration(t) for t in mcp_tools_list.tools]

            system_prompt = load_system_prompt()
            model = genai.GenerativeModel(
                model_name="gemini-2.0-flash",
                tools=gemini_tools,
                system_instruction=system_prompt,
            )

            chat = model.start_chat()

            print(f"\n--- MyHordes Desert Veteran (Gemini) ---")
            print(f"Tools: {len(mcp_tools_list.tools)} loaded. Type 'exit' to quit.\n")

            history_file = Path(__file__).parent / ".gemini_history"
            prompt_session = PromptSession(
                history=FileHistory(str(history_file)),
                auto_suggest=AutoSuggestFromHistory(),
                style=PROMPT_STYLE,
            )

            while True:
                try:
                    user_input = await prompt_session.prompt_async(
                        [("class:prompt", "Citizen > ")]
                    )
                except (EOFError, KeyboardInterrupt):
                    print("\nFarewell, citizen. Try not to die out there.")
                    break

                user_input = user_input.strip()
                if not user_input:
                    continue
                if user_input.lower() in ("exit", "quit"):
                    print("Farewell, citizen. Try not to die out there.")
                    break

                print("\nVeteran is thinking...\n")

                try:
                    response = chat.send_message(user_input)
                    response = await handle_function_calls(session, response, chat)

                    text = response.text if response.text else "(No response)"
                    print(f"Veteran: {text}\n")

                except Exception as e:
                    print(f"\n[!] Error: {e}\n")


if __name__ == "__main__":
    asyncio.run(run_gemini_client())
