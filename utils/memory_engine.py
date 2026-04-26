import json
import asyncio
from typing import List, Dict
from utils.local_llm import local_llm
from utils.chat_history import chat_history, DEFAULT_USER_ID

MEMORY_SYSTEM_PROMPT = """You are a Memory Extraction Assistant. 
Analyze the provided conversation history and extract any concrete facts, preferences, or important details about the user that might be useful for future conversations (e.g., "User lives in New York", "User is a Python developer", "User prefers concise answers", "User's dog is named Rex").
Do not output conversational text. Output ONLY a valid JSON object in the following format:
{
    "memories": [
        {"key": "Location", "value": "User lives in New York"},
        {"key": "Profession", "value": "Python Developer"}
    ]
}
If there are no new facts to extract, output: {"memories": []}
"""

async def extract_and_save_memories(user_id: str, history: List[Dict], latest_user_msg: str, latest_ai_msg: str):
    """
    Extracts facts from recent messages and saves them to the SQLite memory table.
    Designed to run as a background task.
    """
    try:
        # Build the conversation payload that the extractor will see
        conversation_context = ""
        for h in history[-4:]:  # Look at the last few messages for context
            conversation_context += f"{h['role'].upper()}: {h['content']}\n"
        
        conversation_context += f"USER: {latest_user_msg}\n"
        conversation_context += f"ASSISTANT: {latest_ai_msg}\n"

        prompt = f"Here is the recent conversation:\n\n{conversation_context}\n\nExtract the user facts as JSON:"

        # Call the LLM (non-streaming or just collect the stream)
        # Note: If the LLM is busy (e.g. llama.cpp is single-threaded), we might have to wait.
        full_response = ""
        async for token in local_llm.stream_chat(
            message=prompt,
            model=None, # use default
            context=None,
            history=[],
            system_prompt=MEMORY_SYSTEM_PROMPT
        ):
            full_response += token
        
        # safely parse JSON
        json_str = full_response
        
        # sometimes LLM wraps out json in markdown codeblocks
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0]
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0]
            
        data = json.loads(json_str.strip())
        
        memories = data.get("memories", [])
        for mem in memories:
            key = mem.get("key")
            val = mem.get("value")
            if key and val:
                chat_history.save_memory(key, val, user_id=user_id)
                print(f"[*] Memory extracted: {key} -> {val}")
                
    except Exception as e:
        print(f"[!] Background memory extraction failed: {e}")
