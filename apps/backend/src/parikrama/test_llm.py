import sys, os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from pathlib import Path

for line in Path('d:/PariKrama_Agentic-AI-Travel-Planning-Orchestrator/.env').read_text(encoding='utf-8').splitlines():
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        k, _, v = line.partition('=')
        os.environ.setdefault(k.strip(), v.strip())

# Test Gemini
try:
    import google.generativeai as genai
    key = os.environ.get('GEMINI_API_KEY', '')
    model_name = os.environ.get('GEMINI_MODEL', 'gemini-1.5-flash')
    genai.configure(api_key=key)
    m = genai.GenerativeModel(model_name)
    r = m.generate_content('Reply with: OK')
    txt = r.text.strip()[:30]
    print(f'[PASS] GEMINI  model={model_name}  response={txt}')
except Exception as e:
    print(f'[FAIL] GEMINI  {str(e)[:150]}')

# Test Groq
try:
    from groq import Groq
    key = os.environ.get('GROQ_API_KEY', '')
    model_name = os.environ.get('GROQ_PRIMARY_MODEL', 'llama-3.3-70b-versatile')
    c = Groq(api_key=key)
    r = c.chat.completions.create(
        model=model_name,
        messages=[{'role': 'user', 'content': 'Reply with: OK'}],
        max_tokens=5
    )
    txt = r.choices[0].message.content.strip()[:30]
    print(f'[PASS] GROQ    model={model_name}  response={txt}')
except Exception as e:
    print(f'[FAIL] GROQ    {str(e)[:150]}')
