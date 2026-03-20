import os
import asyncio
import json
from dotenv import load_dotenv
import google.generativeai as genai
from google.generativeai.types import content_types
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession

# Load environment variables
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("Error: GEMINI_API_KEY not found in environment variables.")
    exit(1)

genai.configure(api_key=GEMINI_API_KEY)

# The Persona we defined earlier
SYSTEM_PROMPT = """
You are a "Desert Veteran", an elite strategic advisor for the survival browser game MyHordes.
Your tone is cynical, direct, unapologetic, and highly analytical.
Always use your tools to check the town status before giving advice.
You have access to tools that can fetch real-time game data and search the wiki.
"""

def mcp_tool_to_gemini_declaration(mcp_tool):
    """Converts an MCP tool to Gemini's FunctionDeclaration format."""
    # MCP tool has: name, description, inputSchema
    # Gemini declaration: name, description, parameters
    
    # inputSchema is a JSON Schema
    return {
        "name": mcp_tool.name,
        "description": mcp_tool.description,
        "parameters": mcp_tool.inputSchema
    }

async def handle_function_calls(session: ClientSession, response, chat):
    """Iteratively handles function calls from Gemini until a final text response is reached."""
    while response.candidates[0].content.parts[0].function_call:
        tool_call = response.candidates[0].content.parts[0].function_call
        tool_name = tool_call.name
        tool_args = dict(tool_call.args)
        
        print(f"[*] Veteran is using tool: {tool_name}({json.dumps(tool_args)})")
        
        try:
            # Call the MCP tool
            result = await session.call_tool(tool_name, tool_args)
            
            # Format the result for Gemini
            # result.content is a list of content parts (TextContent, ImageContent, etc.)
            # We assume text for now.
            tool_output = "\n".join([c.text for c in result.content if hasattr(c, 'text')])
            
            # Send the tool output back to Gemini
            response = chat.send_message(
                content_types.to_contents({
                    "role": "function",
                    "parts": [
                        {
                            "function_response": {
                                "name": tool_name,
                                "response": {"result": tool_output}
                            }
                        }
                    ]
                })
            )
        except Exception as e:
            print(f"Error calling tool {tool_name}: {e}")
            # Inform Gemini about the error
            response = chat.send_message(
                content_types.to_contents({
                    "role": "function",
                    "parts": [
                        {
                            "function_response": {
                                "name": tool_name,
                                "response": {"error": str(e)}
                            }
                        }
                    ]
                })
            )
    return response

async def run_gemini_client():
    # 1. Define how to start our local MCP server
    server_params = StdioServerParameters(
        command="python",
        args=["main.py"],
        env=dict(os.environ) # Pass environment variables down to the server
    )

    print("Starting MyHordes MCP Server in background...")
    
    # 2. Connect via stdio
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("Connected to MCP Server!")

            # 3. Fetch tools from the server
            mcp_tools_list = await session.list_tools()
            print(f"Discovered {len(mcp_tools_list.tools)} tools.")

            # Convert mcp_tools to Gemini's expected tool format
            gemini_tools = [mcp_tool_to_gemini_declaration(t) for t in mcp_tools_list.tools]
            
            # Initialize Gemini Model
            model = genai.GenerativeModel(
                model_name='gemini-2.0-flash', # Using latest flash for speed
                tools=gemini_tools,
                system_instruction=SYSTEM_PROMPT
            )

            chat = model.start_chat()

            print("\n--- MyHordes Desert Veteran ---")
            print("Type 'exit' to quit.\n")

            # Simple CLI Loop
            while True:
                try:
                    user_input = input("Citizen > ")
                except EOFError:
                    break
                    
                if user_input.lower() in ['quit', 'exit']:
                    break
                
                if not user_input.strip():
                    continue

                print("Veteran is thinking...")
                
                try:
                    # Send message to Gemini
                    response = chat.send_message(user_input)

                    # Handle Function Calling Loop
                    response = await handle_function_calls(session, response, chat)
                    
                    if response.text:
                        print(f"\nVeteran: {response.text}")
                    else:
                        print("\nVeteran: (No response)")
                        
                except Exception as e:
                    print(f"\n[!] Error: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(run_gemini_client())
    except KeyboardInterrupt:
        pass
