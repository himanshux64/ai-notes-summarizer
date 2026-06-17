import os
import re
import json

# Fallback imports to support both langchain-huggingface and older langchain-community
try:
    from langchain_huggingface import HuggingFaceEndpoint
except ImportError:
    try:
        from langchain_community.llms import HuggingFaceHub as HuggingFaceEndpoint
    except ImportError:
        HuggingFaceEndpoint = None

from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

PROMPT_TEMPLATE = """You are an expert AI academic tutor and research assistant. Your task is to analyze the following text and generate structured learning materials.

Format your output exactly with these tags:
<summary>
Write a concise, high-level summary of 3-5 sentences describing the core theme and context.
</summary>

<bullet_points>
List 5-8 detailed bullet points summarizing the key facts and sequence of ideas.
</bullet_points>

<takeaways>
Provide 3-5 high-impact, actionable takeaways or lessons from the text.
</takeaways>

<study_notes>
Create well-structured, in-depth revision notes. Use headings (###), bold text, and sub-bullets to organize main concepts.
</study_notes>

<flashcards>
Create 4-6 flashcards for active recall study. Format each card exactly like this:
Q: [Clear, concise question about a key fact or concept]
A: [Direct, accurate answer]
</flashcards>

Here is the text to analyze:
{text}
"""

def parse_llm_output(output_text):
    """
    Parses the structured LLM output containing XML-like tags.
    Falls back to header splits if tags are missing or broken.
    """
    summary_match = re.search(r'<summary>(.*?)</summary>', output_text, re.DOTALL | re.IGNORECASE)
    bullets_match = re.search(r'<bullet_points>(.*?)</bullet_points>', output_text, re.DOTALL | re.IGNORECASE)
    takeaways_match = re.search(r'<takeaways>(.*?)</takeaways>', output_text, re.DOTALL | re.IGNORECASE)
    notes_match = re.search(r'<study_notes>(.*?)</study_notes>', output_text, re.DOTALL | re.IGNORECASE)
    flashcards_match = re.search(r'<flashcards>(.*?)</flashcards>', output_text, re.DOTALL | re.IGNORECASE)
    
    summary = summary_match.group(1).strip() if summary_match else None
    bullet_points = bullets_match.group(1).strip() if bullets_match else None
    takeaways = takeaways_match.group(1).strip() if takeaways_match else None
    study_notes = notes_match.group(1).strip() if notes_match else None
    flashcards_str = flashcards_match.group(1).strip() if flashcards_match else None
    
    # Fallback: Split by markdown headers if XML tags failed
    if not summary:
        sections = re.split(r'#+\s*(summary|bullet[ -]points|key[ -]takeaways|takeaways|study[ -]notes|flashcards)', output_text, flags=re.IGNORECASE)
        parsed = {}
        for i in range(1, len(sections), 2):
            sec_name = sections[i].lower().replace(" ", "_").replace("-", "_")
            sec_content = sections[i+1].strip() if i+1 < len(sections) else ""
            parsed[sec_name] = sec_content
            
        summary = parsed.get('summary')
        bullet_points = parsed.get('bullet_points', parsed.get('bullet_points'))
        takeaways = parsed.get('key_takeaways', parsed.get('takeaways'))
        study_notes = parsed.get('study_notes', parsed.get('study_notes'))
        flashcards_str = parsed.get('flashcards')

    # Assign final values with fallback defaults
    summary = summary or "No summary segment detected. Here is raw output preview:\n" + output_text[:300] + "..."
    bullet_points = bullet_points or "No bullet points segment detected."
    takeaways = takeaways or "No takeaways segment detected."
    study_notes = study_notes or "No study notes segment detected."
    
    # Parse flashcards
    flashcards = []
    if flashcards_str:
        # Match Q: ... A: ... pairs
        pairs = re.findall(r'(?:Q|Question):\s*(.*?)\n(?:A|Answer):\s*(.*?)(?=\n(?:Q|Question):|$)', flashcards_str + '\n', re.DOTALL | re.IGNORECASE)
        for q, a in pairs:
            flashcards.append({
                "question": q.strip(),
                "answer": a.strip()
            })
            
    # If no flashcards found from standard tags, search entire document for Q & A pairs
    if not flashcards:
        pairs = re.findall(r'(?:Q|Question):\s*(.*?)\n(?:A|Answer):\s*(.*?)(?=\n(?:Q|Question):|$)', output_text + '\n', re.DOTALL | re.IGNORECASE)
        for q, a in pairs:
            flashcards.append({
                "question": q.strip(),
                "answer": a.strip()
            })
            
    # Default fallback flashcards
    if not flashcards:
        flashcards = [
            {"question": "What is the primary topic of this document?", "answer": summary[:150] + "..."}
        ]
        
    return {
        "summary": summary,
        "bullet_points": bullet_points,
        "takeaways": takeaways,
        "study_notes": study_notes,
        "flashcards": flashcards
    }

def generate_mock_summary(text):
    """
    Generates structured summaries locally without an LLM for testing.
    """
    sentences = [s.strip() for s in re.split(r'[.!?]', text) if len(s.strip()) > 8]
    
    # Summary
    summary_sentences = sentences[:3] if len(sentences) >= 3 else sentences
    summary = " ".join(summary_sentences) + "." if summary_sentences else "The provided text was too short to generate a summary."
    
    # Bullet points
    if len(sentences) > 3:
        bullet_points = "\n".join([f"- {s}." for s in sentences[3:9]])
    else:
        bullet_points = "\n".join([f"- {s}." for s in sentences])
    if not bullet_points:
        bullet_points = "- Insufficient text length to extract bullet points."
        
    # Takeaways
    if len(sentences) > 2:
        takeaways = "\n".join([f"- {s}." for s in sentences[-3:]])
    else:
        takeaways = "- Understand the core details as outlined in the summary."
        
    # Study notes
    study_notes = "### Key Topics Identified\n\n"
    if sentences:
        study_notes += f"**Core statement:** {sentences[0]}.\n\n"
    study_notes += "### Discussion points\n"
    for s in sentences[:8]:
        study_notes += f"* {s}\n"
        
    # Flashcards
    flashcards = []
    # Try finding capitalised words/nouns to make questions
    words = list(set([w.strip(".,;:?!\"'()[]") for w in text.split() if len(w) > 5 and w[0].isupper()]))
    if len(words) >= 3:
        for w in words[:4]:
            flashcards.append({
                "question": f"What is the context of '{w}' in this document?",
                "answer": f"Refer to the text segment: '... {w} ...' to review its definitions and significance."
            })
    else:
        flashcards = [
            {"question": "What is the main subject of this file?", "answer": summary[:100] + "..."},
            {"question": "Where can I find details on key facts?", "answer": "Check the bullet points and study notes sections."}
        ]
        
    return {
        "summary": summary,
        "bullet_points": bullet_points,
        "takeaways": takeaways,
        "study_notes": study_notes,
        "flashcards": flashcards
    }

def summarize_text(text, api_token=None, model_name="meta-llama/Meta-Llama-3-8B-Instruct"):
    """
    Main summarization entry point. If api_token is provided, calls HF via InferenceClient.
    Otherwise, falls back to local mock summarizer.
    """
    if not api_token or api_token.strip() == "" or api_token == "mock":
        return generate_mock_summary(text)
        
    # Prevent old browser localStorage from crashing the app
    if "Mistral" in model_name or "zephyr" in model_name or "Llama-3.1" in model_name:
        model_name = "meta-llama/Meta-Llama-3-8B-Instruct"

    if HuggingFaceEndpoint is None:
        # Fallback if libraries aren't loaded properly
        return generate_mock_summary(text)
        
    try:
        from huggingface_hub import InferenceClient
        
        client = InferenceClient(model=model_name, token=api_token)
        
        # Build prompt
        prompt = PROMPT_TEMPLATE.format(text=text)
        
        try:
            # Try chat_completion first (required by some providers for instruct models)
            messages = [{"role": "user", "content": prompt}]
            response = client.chat_completion(
                messages=messages,
                max_tokens=1024,
                temperature=0.3
            )
            raw_output = response.choices[0].message.content
        except Exception as chat_err:
            # If the model is not a chat model, fallback to text_generation
            try:
                raw_output = client.text_generation(
                    prompt,
                    max_new_tokens=1024,
                    temperature=0.3
                )
            except Exception as text_err:
                # Raise the original error if both fail, prioritizing the first relevant message
                raise Exception(f"chat_completion error: {str(chat_err)} | text_generation error: {str(text_err)}")
        
        # Parse output
        return parse_llm_output(raw_output)
        
    except Exception as e:
        print(f"Error calling LLM: {str(e)}")
        # If real API fails (e.g. rate limit, invalid key), return mock data but add error note
        mock_data = generate_mock_summary(text)
        mock_data["summary"] = f"⚠️ [LLM API Error: {str(e)} - Displaying fallback notes]\n\n" + mock_data["summary"]
        return mock_data
