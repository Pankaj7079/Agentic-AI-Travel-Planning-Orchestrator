import sys, os, warnings
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from pathlib import Path

for line in Path('d:/PariKrama_Agentic-AI-Travel-Planning-Orchestrator/.env').read_text(encoding='utf-8').splitlines():
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        k, _, v = line.partition('=')
        os.environ.setdefault(k.strip(), v.strip())

key = os.environ.get('GEMINI_API_KEY', '')
models_to_try = [
    'gemini-2.5-flash-lite-preview-06-17',
    'gemini-2.5-flash',
    'gemini-1.5-flash-latest',
    'gemini-1.5-flash',
    'gemini-1.5-pro',
]

with warnings.catch_warnings():
    warnings.simplefilter('ignore', FutureWarning)
    import google.generativeai as genai

genai.configure(api_key=key)

# First: list available models
print('Available models on your key:')
try:
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(f'  - {m.name}')
except Exception as e:
    print(f'  Could not list models: {e}')

print()
print('Testing models:')
for model_name in models_to_try:
    try:
        m = genai.GenerativeModel(model_name)
        r = m.generate_content('Say: OK')
        print(f'  [PASS] {model_name}  -> "{r.text.strip()[:20]}"')
        break  # found working model
    except Exception as e:
        err = str(e)[:80]
        print(f'  [FAIL] {model_name}  -> {err}')
