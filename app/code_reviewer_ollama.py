import requests

OLLAMA_URL = "http://localhost:11434/api/generate"

def review_code_file(model, code_content, guidelines, file_path):
    prompt = f"""
You are a code reviewer. Below is a file and a set of architecture and coding guidelines.

Guidelines:
{guidelines}

File Path: {file_path}
Code:
{code_content}

Please analyze and return a structured JSON response:
{{
  "file": "{file_path}",
  "summary": "Brief description",
  "issues": [
    {{
      "type": "architecture/style/performance",
      "description": "Issue description",
      "severity": "Critical/Major/Minor",
      "suggestion": "Fix or improvement suggestion"
    }}
  ],
  "rating": "Excellent/Good/Fair/Poor"
}}
"""
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False
    }
    response = requests.post(OLLAMA_URL, json=payload)
    return response.json().get("response", "")