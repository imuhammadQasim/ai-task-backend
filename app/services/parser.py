# app/services/parser.py
import json
import openai
from fastapi import HTTPException
from app.config import settings

# Initialize OpenAI Client
client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)

async def parse_task(raw_input: str) -> dict:
    if not settings.OPENAI_API_KEY:
        # Fallback or error if key is empty
        raise HTTPException(
            status_code=422,
            detail="OpenAI API key not configured"
        )
    
    system_prompt = (
        "You are an AI that parses natural language inputs into structured task specifications.\n"
        "Analyze the user's input and extract relevant details.\n"
        "Return ONLY a JSON object matching this schema:\n"
        "{\n"
        '  "task_type": "web_monitor" | "date_reminder",\n'
        '  "url": "string or null",\n'
        '  "condition": "what to watch for",\n'
        '  "schedule_mins": integer minimum 60,\n'
        '  "notification_channel": "email" | "messenger"\n'
        "}\n"
        "Do not include any markup like ```json or explanations outside the JSON."
    )
    
    try:
        # Call OpenAI GPT-4o-mini using sync client run inside async wrapper or using loop.run_in_executor
        # For simplicity and standard async/await compat:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": raw_input}
            ],
            response_format={"type": "json_object"},
            temperature=0.0
        )
        content = response.choices[0].message.content
        result = json.loads(content)
        
        # Validate properties
        if "task_type" not in result:
            result["task_type"] = "web_monitor"
        if "schedule_mins" not in result or not isinstance(result["schedule_mins"], int):
            result["schedule_mins"] = 60
        elif result["schedule_mins"] < 60:
            result["schedule_mins"] = 60
            
        return result
    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail="Could not parse task input"
        )
