from flask import Flask, jsonify, render_template_string
import json
from config import STATIC_DIR

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path='/static')
HTML = '''<!doctype html>
<html lang="th"><head><meta charset="utf-8"><meta http-equiv="refresh" content="3">
<title>Smart Fire Detection</title>
<style>body{font-family:Arial;background:#111827;color:#e5e7eb;margin:20px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.card{background:#1f2937;padding:16px;border-radius:12px}img{width:100%;border-radius:8px}pre{white-space:pre-wrap}@media(max-width:800px){.grid{grid-template-columns:1fr}}</style>
</head><body><h1>Smart Fire Detection v2</h1><div class="grid">
<div class="card"><h2>Latest frame</h2><img src="/static/latest_frame.jpg"></div>
<div class="card"><h2>Last alert</h2><img src="/static/latest_alert.jpg"></div></div>
<div class="card" style="margin-top:16px"><h2>Status</h2><pre>{{ status }}</pre></div></body></html>'''

@app.route('/')
def index():
    p = STATIC_DIR / 'status.json'
    status = p.read_text(encoding='utf-8') if p.exists() else '{"status":"waiting"}'
    return render_template_string(HTML, status=status)

@app.route('/api/status')
def api_status():
    p = STATIC_DIR / 'status.json'
    return jsonify({'status':'waiting'}) if not p.exists() else jsonify(json.loads(p.read_text(encoding='utf-8')))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
