# app/services/llm.py
import json
import google.generativeai as genai
from google import genai as genai_client
from google.genai import types as genai_types
from app.config import settings

def configure_gemini():
    if settings.GEMINI_API_KEY:
        genai.configure(api_key=settings.GEMINI_API_KEY)

# Call configuration
configure_gemini()

# Model used for the grounded-answer and semantic-comparison calls. gemini-1.5
# is no longer served on this API key, so use a current 2.x model.
GROUNDING_MODEL = "gemini-2.5-flash"


def query_with_grounding(topic: str) -> str:
    """Calls Gemini with the Google Search grounding tool enabled, returns the answer text.

    Synchronous SDK call; invoke via asyncio.to_thread() from async contexts.
    """
    if not settings.GEMINI_API_KEY:
        return ""

    try:
        client = genai_client.Client(api_key=settings.GEMINI_API_KEY)
        search_tool = genai_types.Tool(google_search=genai_types.GoogleSearch())
        response = client.models.generate_content(
            model=GROUNDING_MODEL,
            contents=(
                "Answer the following topic/question using up-to-date information. "
                "Be concise and factual.\n\n"
                f"Topic: {topic}"
            ),
            config=genai_types.GenerateContentConfig(tools=[search_tool]),
        )
        return (response.text or "").strip()
    except Exception as e:
        return f"Could not retrieve grounded answer: {str(e)}"


def compare_answers(old_answer: str, new_answer: str) -> tuple[bool, str]:
    """Asks Gemini whether new_answer represents a meaningful factual change from
    old_answer (ignoring rewording/phrasing differences), returns (changed, summary).

    Synchronous SDK call; invoke via asyncio.to_thread() from async contexts. Never
    relies on string/hash equality, since grounded phrasing varies between runs.
    """
    if not settings.GEMINI_API_KEY:
        return False, "Gemini API key is not configured"

    prompt = (
        "Two answers were produced for the same monitored topic at different times. "
        "Decide whether the SECOND answer represents a MEANINGFUL FACTUAL change "
        "from the FIRST. Ignore differences that are only rewording, phrasing, "
        "formatting, or rounding with no factual significance.\n\n"
        f"FIRST ANSWER:\n{old_answer}\n\n"
        f"SECOND ANSWER:\n{new_answer}\n\n"
        "Answer with JSON only using exactly this schema:\n"
        '{"changed": true|false, "summary": "one sentence explaining what changed (or that nothing meaningful changed)"}'
    )

    try:
        client = genai_client.Client(api_key=settings.GEMINI_API_KEY)
        response = client.models.generate_content(
            model=GROUNDING_MODEL,
            contents=prompt,
            config=genai_types.GenerateContentConfig(response_mime_type="application/json"),
        )
        data = json.loads((response.text or "").strip())
        changed = bool(data.get("changed", False))
        summary = str(data.get("summary", "Answer evaluated"))
        return changed, summary
    except Exception as e:
        return False, f"Could not compare answers: {str(e)}"

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
