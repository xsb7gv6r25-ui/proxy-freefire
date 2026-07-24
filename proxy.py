#!/usr/bin/env python3
# ============================================
# FREEFIRE PROXY - VERSIÓN FUNCIONAL
# ============================================

import os
import json
import secrets
import sqlite3
import datetime
from datetime import timedelta
from flask import Flask, request, jsonify

app = Flask(__name__)

# ==========================================
# BASE DE DATOS
# ==========================================

def init_db():
    conn = sqlite3.connect('keys.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key_code TEXT UNIQUE NOT NULL,
            expiration_date TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT 1
        )
    ''')
    conn.commit()
    conn.close()

def generate_key(days=30):
    key_code = secrets.token_hex(12).upper()
    expiration = (datetime.datetime.now() + timedelta(days=days)).isoformat()
    
    conn = sqlite3.connect('keys.db')
    c = conn.cursor()
    c.execute('INSERT INTO keys (key_code, expiration_date) VALUES (?, ?)', (key_code, expiration))
    conn.commit()
    conn.close()
    return key_code, expiration

def validate_key(key_code):
    conn = sqlite3.connect('keys.db')
    c = conn.cursor()
    c.execute('SELECT expiration_date, is_active FROM keys WHERE key_code = ?', (key_code,))
    result = c.fetchone()
    conn.close()
    if not result:
        return False, "Clave no encontrada"
    expiration, is_active = result
    if not is_active:
        return False, "Clave inactiva"
    if datetime.datetime.now().isoformat() > expiration:
        return False, "Clave expirada"
    return True, "Clave válida"

# ==========================================
# ENDPOINTS
# ==========================================

@app.route('/')
def home():
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>FreeFire Proxy</title>
        <style>
            body { background: #0a0a0a; color: #00ff00; font-family: monospace; text-align: center; padding: 50px; }
            h1 { color: #00ff00; text-shadow: 0 0 20px #00ff00; }
            .btn { background: #00ff00; color: #0a0a0a; border: none; padding: 15px 30px; font-size: 18px; cursor: pointer; border-radius: 5px; }
            .key-box { background: #1a1a1a; border: 1px solid #00ff00; padding: 20px; margin: 20px auto; max-width: 500px; border-radius: 8px; }
            input { background: #1a1a1a; color: #00ff00; border: 1px solid #00ff00; padding: 10px; width: 80%; }
        </style>
    </head>
    <body>
        <h1>🔥 FREEFIRE PROXY 🔥</h1>
        <p>Proxy funcionando correctamente</p>
        <div class="key-box">
            <h3>Generar Clave</h3>
            <button class="btn" onclick="generateKey()">Generar Clave (30 días)</button>
            <div id="result" style="margin-top: 10px;"></div>
        </div>
        <div class="key-box">
            <h3>Validar Clave</h3>
            <input type="text" id="keyInput" placeholder="Introduce tu clave">
            <button class="btn" onclick="validateKey()">Validar</button>
            <div id="validateResult" style="margin-top: 10px;"></div>
        </div>
        <script>
            function generateKey() {
                fetch('/api/generate')
                .then(r => r.json())
                .then(data => {
                    document.getElementById('result').innerHTML = 
                        '<p>Clave: <b>' + data.key + '</b></p>' +
                        '<p>Expira: ' + data.expiration + '</p>';
                });
            }
            function validateKey() {
                let key = document.getElementById('keyInput').value;
                fetch('/api/validate?key=' + key)
                .then(r => r.json())
                .then(data => {
                    document.getElementById('validateResult').innerHTML = 
                        '<p>' + data.message + '</p>';
                });
            }
        </script>
    </body>
    </html>
    '''

@app.route('/api/generate')
def api_generate():
    days = request.args.get('days', 30, type=int)
    key, expiration = generate_key(days)
    return jsonify({'key': key, 'expiration': expiration})

@app.route('/api/validate')
def api_validate():
    key = request.args.get('key')
    if not key:
        return jsonify({'error': 'Se requiere una clave'}), 400
    valid, message = validate_key(key)
    return jsonify({'valid': valid, 'message': message})

@app.route('/api/stats')
def api_stats():
    conn = sqlite3.connect('keys.db')
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM keys')
    total = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM keys WHERE is_active = 1')
    active = c.fetchone()[0]
    conn.close()
    return jsonify({'total': total, 'active': active})

# ==========================================
# EJECUCIÓN
# ==========================================

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 8080))
    print(f'🔥 FreeFire Proxy iniciado en puerto {port}')
    print(f'📱 Dashboard: https://proxy-freefire.onrender.com')
    app.run(host='0.0.0.0', port=port)
