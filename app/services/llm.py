# app/services/llm.py
import json
import google.generativeai as genai
from app.config import settings

def configure_gemini():
    if settings.GEMINI_API_KEY:
        genai.configure(api_key=settings.GEMINI_API_KEY)

# Call configuration
configure_gemini()

async def check_condition(html_content: str, condition: str) -> tuple[bool, str]:
    if not settings.GEMINI_API_KEY:
        return False, "Gemini API key is not configured"
        
    # Truncate html_content to first 8000 characters
    truncated_html = html_content[:8000] if html_content else ""
    
    prompt = (
        f"Given this webpage content, does the following condition appear to be met?\n"
        f"Condition: {condition}\n\n"
        f"Webpage Content:\n"
        f"{truncated_html}\n\n"
        f"Answer with JSON only using exactly this schema:\n"
        f'{{"matched": true|false, "summary": "one sentence explanation"}}'
    )
    
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        # genai SDK calls are synchronous block, but we can call it directly
        # or execute it if needed. Let's make the API call.
        response = model.generate_content(
            prompt,
            generation_config={"response_mime_type": "application/json"}
        )
        
        result_text = response.text.strip()
        data = json.loads(result_text)
        matched = bool(data.get("matched", False))
        summary = str(data.get("summary", "Condition evaluated"))
        return matched, summary
    except Exception as e:
        return False, f"Could not analyze content: {str(e)}"
