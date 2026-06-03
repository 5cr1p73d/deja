import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from openai import OpenAI
from db import get_conn

conn = get_conn(); c = conn.cursor()
rows = dict(c.execute("SELECT key, value FROM settings WHERE key LIKE 'ai_%'").fetchall())
conn.close()
api_key = (rows.get("ai_api_key") or "").strip()
model = (rows.get("ai_model") or "").strip()
if not model:
    print("Nessun modello AI configurato (Impostazioni → AI). Imposta 'ai_model' nel DB per il test.")
    sys.exit(1)

for base in ["https://api.gonkagate.com/v1", "https://api.gonkagate.com/v1/"]:
    print(f"== {base} ==")
    try:
        client = OpenAI(base_url=base, api_key=api_key)
        r = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "say hi in 5 words"}],
            max_tokens=30,
        )
        print("OK:", r.choices[0].message.content)
    except Exception as e:
        print(f"FAIL: {type(e).__name__}: {str(e)[:300]}")
    print()
