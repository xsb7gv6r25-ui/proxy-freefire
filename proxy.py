#!/usr/bin/env python3
# ============================================
# FREEFIRE ULTIMATE PROXY v4.1
# CODIGO CORREGIDO - SIN ERRORES
# ============================================

import sys
import os
import socket
import threading
import time
import random
import json
import hashlib
import base64
import sqlite3
import secrets
import re
import argparse
import logging
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Tuple, Optional, Dict

# ==========================================
# VERSION
# ==========================================

VERSION = "4.1.0"
AUTHOR = "PICOLAS"

# ==========================================
# 1. SISTEMA DE LOGS (CORREGIDO)
# ==========================================

class Logger:
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if Logger._initialized:
            return
        Logger._initialized = True
        os.makedirs('logs', exist_ok=True)
        self.logger = logging.getLogger('FreeFireProxy')
        self.logger.setLevel(logging.DEBUG)
        
        file_handler = logging.FileHandler('logs/proxy.log')
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter('[%(asctime)s] %(levelname)s - %(message)s')
        file_handler.setFormatter(file_formatter)
        
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter('%(message)s')
        console_handler.setFormatter(console_formatter)
        
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
    
    @classmethod
    def info(cls, message):
        cls().logger.info(message)
    
    @classmethod
    def success(cls, message):
        cls().logger.info(f"✅ {message}")
    
    @classmethod
    def warning(cls, message):
        cls().logger.warning(f"⚠️ {message}")
    
    @classmethod
    def error(cls, message):
        cls().logger.error(f"❌ {message}")
    
    @classmethod
    def debug(cls, message):
        cls().logger.debug(f"🔍 {message}")

# ==========================================
# 2. SISTEMA DE AUTENTICACION
# ==========================================

class KeyManager:
    def __init__(self, db_path='keys.db'):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key_code TEXT UNIQUE NOT NULL,
                user_id TEXT,
                expiration_date DATETIME NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_used DATETIME,
                is_active BOOLEAN DEFAULT 1,
                max_devices INTEGER DEFAULT 1,
                current_devices INTEGER DEFAULT 0,
                notes TEXT
            )
        ''')
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key_id INTEGER,
                device_id TEXT UNIQUE,
                device_name TEXT,
                ip TEXT,
                first_connect DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_connect DATETIME,
                last_ip TEXT,
                is_active BOOLEAN DEFAULT 1,
                FOREIGN KEY (key_id) REFERENCES keys(id)
            )
        ''')
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS usage_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key_code TEXT,
                action TEXT,
                details TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                ip TEXT,
                user_agent TEXT
            )
        ''')
        
        c.execute('CREATE INDEX IF NOT EXISTS idx_keys_code ON keys(key_code)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_devices_key_id ON devices(key_id)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_logs_key ON usage_logs(key_code)')
        
        conn.commit()
        conn.close()
    
    def generate_key(self, days_valid: int = 7, max_devices: int = 1, notes: str = '') -> Tuple[str, str]:
        key_code = secrets.token_hex(12).upper()
        expiration = datetime.now() + timedelta(days=days_valid)
        
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''
            INSERT INTO keys (key_code, expiration_date, max_devices, notes)
            VALUES (?, ?, ?, ?)
        ''', (key_code, expiration.isoformat(), max_devices, notes))
        conn.commit()
        conn.close()
        
        Logger.info(f"Clave generada: {key_code} ({days_valid} días)")
        return key_code, expiration.isoformat()
    
    def validate_key(self, key_code: str, device_id: str, ip: str, user_agent: str = '') -> Tuple[bool, str]:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute('''
            SELECT id, key_code, expiration_date, is_active, max_devices, current_devices, notes
            FROM keys WHERE key_code = ?
        ''', (key_code,))
        key_data = c.fetchone()
        
        if not key_data:
            return False, "CLAVE_INVALIDA"
        
        key_id, code, expiration, is_active, max_devices, current_devices, notes = key_data
        
        if not is_active:
            return False, "CLAVE_INACTIVA"
        
        expiration_date = datetime.fromisoformat(expiration)
        if datetime.now() > expiration_date:
            return False, "CLAVE_EXPIRADA"
        
        c.execute('SELECT COUNT(*) FROM devices WHERE key_id = ? AND is_active = 1', (key_id,))
        device_count = c.fetchone()[0]
        
        if device_count >= max_devices:
            return False, "LIMITE_ALCANZADO"
        
        c.execute('SELECT id FROM devices WHERE device_id = ? AND key_id = ?', (device_id, key_id))
        existing = c.fetchone()
        
        if existing:
            c.execute('''
                UPDATE devices SET last_connect = ?, last_ip = ?, is_active = 1
                WHERE device_id = ? AND key_id = ?
            ''', (datetime.now().isoformat(), ip, device_id, key_id))
        else:
            c.execute('''
                INSERT INTO devices (key_id, device_id, ip, last_connect)
                VALUES (?, ?, ?, ?)
            ''', (key_id, device_id, ip, datetime.now().isoformat()))
        
        if not existing:
            c.execute('''
                UPDATE keys SET current_devices = current_devices + 1, last_used = ?
                WHERE id = ?
            ''', (datetime.now().isoformat(), key_id))
        
        conn.commit()
        conn.close()
        return True, "AUTORIZADO"
    
    def revoke_key(self, key_code: str) -> bool:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('UPDATE keys SET is_active = 0 WHERE key_code = ?', (key_code,))
        conn.commit()
        conn.close()
        Logger.info(f"Clave revocada: {key_code}")
        return True
    
    def extend_key(self, key_code: str, days: int) -> bool:
        new_expiration = datetime.now() + timedelta(days=days)
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('UPDATE keys SET expiration_date = ? WHERE key_code = ?', 
                 (new_expiration.isoformat(), key_code))
        conn.commit()
        conn.close()
        Logger.info(f"Clave extendida: {key_code} (+{days} días)")
        return True
    
    def get_stats(self) -> Dict:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute('SELECT COUNT(*) FROM keys')
        total_keys = c.fetchone()[0]
        
        c.execute('SELECT COUNT(*) FROM keys WHERE is_active = 1')
        active_keys = c.fetchone()[0]
        
        c.execute('SELECT COUNT(*) FROM keys WHERE expiration_date < datetime("now")')
        expired_keys = c.fetchone()[0]
        
        c.execute('SELECT COUNT(*) FROM devices WHERE is_active = 1')
        total_devices = c.fetchone()[0]
        
        c.execute('SELECT COUNT(*) FROM usage_logs')
        total_logs = c.fetchone()[0]
        
        conn.close()
        return {
            'total_keys': total_keys,
            'active_keys': active_keys,
            'expired_keys': expired_keys,
            'total_devices': total_devices,
            'total_logs': total_logs
        }
    
    def validate_client(self, username: str, password: str) -> bool:
        expected_hash = hashlib.sha256('picolas2026'.encode()).hexdigest()
        return username == 'admin' and hashlib.sha256(password.encode()).hexdigest() == expected_hash

# ==========================================
# 3. MOTOR DE INYECCION
# ==========================================

class Injector:
    def __init__(self):
        self.patterns = {
            'recoil': re.compile(r'"recoil":(\d+)', re.IGNORECASE),
            'reload_speed': re.compile(r'"reload_speed":(\d+)', re.IGNORECASE),
            'accuracy': re.compile(r'"accuracy":(\d+)', re.IGNORECASE),
            'speed': re.compile(r'"speed":(\d+)', re.IGNORECASE)
        }
    
    def inject(self, data):
        if not data:
            return data
        
        try:
            if isinstance(data, bytes):
                data_str = data.decode('utf-8', errors='ignore')
            else:
                data_str = str(data)
            
            modified = data_str
            
            # Sin Recoil
            modified = self.patterns['recoil'].sub(r'"recoil":0', modified)
            
            # Recarga Rapida
            modified = self.patterns['reload_speed'].sub(r'"reload_speed":1', modified)
            
            # Precision Mejorada
            matches = self.patterns['accuracy'].findall(modified)
            for match in matches:
                if match.isdigit():
                    original = int(match)
                    new_accuracy = int(original * 1.9)
                    modified = modified.replace(f'"accuracy":{match}', f'"accuracy":{new_accuracy}')
            
            # Velocidad Mejorada
            matches = self.patterns['speed'].findall(modified)
            for match in matches:
                if match.isdigit():
                    original = int(match)
                    new_speed = int(original * 2.5)
                    modified = modified.replace(f'"speed":{match}', f'"speed":{new_speed}')
            
            return modified.encode('utf-8') if isinstance(data, bytes) else modified
            
        except Exception as e:
            Logger.error(f"Error en inyeccion: {e}")
            return data

# ==========================================
# 4. PROXY PRINCIPAL
# ==========================================

class FreeFireProxy:
    def __init__(self, port=8080):
        self.port = port
        self.injector = Injector()
        self.key_manager = KeyManager()
        
        self.stats = {
            'requests': 0,
            'injections': 0,
            'errors': 0,
            'start_time': time.time()
        }
        
        Logger.info(f"Proxy inicializado en puerto {port}")
    
    def start(self):
        server = HTTPServer(('0.0.0.0', self.port), self._create_handler())
        Logger.success(f"Proxy escuchando en 0.0.0.0:{self.port}")
        Logger.info("Presiona Ctrl+C para detener")
        
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            Logger.info("Deteniendo proxy...")
            server.shutdown()
    
    def _create_handler(self):
        class ProxyHandler(BaseHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                self.proxy = FreeFireProxy.this
                super().__init__(*args, **kwargs)
            
            def do_GET(self):
                self._handle_request('GET')
            
            def do_POST(self):
                self._handle_request('POST')
            
            def do_CONNECT(self):
                self._handle_connect()
            
            def _handle_request(self, method):
                try:
                    if not self._check_auth():
                        self.send_response(401)
                        self.send_header('Proxy-Authenticate', 'Basic realm="FreeFire Proxy"')
                        self.end_headers()
                        return
                    
                    self.proxy.stats['requests'] += 1
                    
                    if self._is_freefire_traffic():
                        self.proxy.stats['injections'] += 1
                        modified = self._inject_hacks(self.rfile.read())
                    else:
                        modified = self.rfile.read()
                    
                    self._forward_request(method, modified)
                    
                except Exception as e:
                    Logger.error(f"Error en request: {e}")
                    self.proxy.stats['errors'] += 1
                    self.send_response(500)
                    self.end_headers()
            
            def _handle_connect(self):
                try:
                    host, port = self.path.split(':')
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.connect((host, int(port)))
                    
                    self.send_response(200, 'Connection Established')
                    self.end_headers()
                    
                    self._handle_tunnel(sock)
                except Exception as e:
                    Logger.error(f"Error en CONNECT: {e}")
                    self.send_response(500)
                    self.end_headers()
            
            def _handle_tunnel(self, server_sock):
                client_sock = self.request
                
                def forward(src, dst):
                    try:
                        while True:
                            data = src.recv(4096)
                            if not data:
                                break
                            if self._is_freefire_traffic():
                                data = self._inject_hacks(data)
                            dst.send(data)
                    except:
                        pass
                
                t1 = threading.Thread(target=forward, args=(client_sock, server_sock))
                t2 = threading.Thread(target=forward, args=(server_sock, client_sock))
                t1.daemon = True
                t2.daemon = True
                t1.start()
                t2.start()
                t1.join()
                t2.join()
            
            def _check_auth(self):
                auth = self.headers.get('Proxy-Authorization')
                if not auth:
                    return False
                try:
                    encoded = auth.split(' ')[1]
                    decoded = base64.b64decode(encoded).decode()
                    username, password = decoded.split(':')
                    return self.proxy.key_manager.validate_client(username, password)
                except:
                    return False
            
            def _is_freefire_traffic(self):
                host = self.headers.get('Host', '')
                freefire_domains = [
                    'freefire.garena.com', 'ff.garena.com',
                    'api.garena.com', 'account.garena.com',
                    'match.garena.com', 'game.garena.com'
                ]
                return any(domain in host.lower() for domain in freefire_domains)
            
            def _inject_hacks(self, data):
                try:
                    return self.proxy.injector.inject(data)
                except Exception as e:
                    Logger.error(f"Error en inyeccion: {e}")
                    return data
            
            def _forward_request(self, method, data):
                import requests
                host = self.headers.get('Host', '')
                path = self.path
                url = f"http://{host}{path}"
                headers = dict(self.headers)
                headers.pop('Proxy-Authorization', None)
                headers.pop('Proxy-Connection', None)
                
                try:
                    if method == 'GET':
                        resp = requests.get(url, headers=headers, params=parse_qs(self.path.split('?')[1]) if '?' in self.path else None)
                    else:
                        resp = requests.post(url, headers=headers, data=data)
                    
                    self.send_response(resp.status_code)
                    for key, value in resp.headers.items():
                        self.send_header(key, value)
                    self.end_headers()
                    if resp.content:
                        self.wfile.write(resp.content)
                except Exception as e:
                    Logger.error(f"Error forward: {e}")
                    self.send_response(500)
                    self.end_headers()
        
        FreeFireProxy.this = self
        return ProxyHandler

# ==========================================
# 5. EJECUCION (CORREGIDO)
# ==========================================

def main():
    parser = argparse.ArgumentParser(description="FreeFire Proxy")
    parser.add_argument('--port', type=int, default=8080, help='Puerto del proxy')
    parser.add_argument('--key', type=int, help='Generar clave (dias)')
    parser.add_argument('--revoke', type=str, help='Revocar clave')
    parser.add_argument('--stats', action='store_true', help='Mostrar estadisticas')
    
    args = parser.parse_args()
    
    # Logger se inicializa solo, no necesita .init()
    Logger.info(f"FreeFire Ultimate Proxy v{VERSION}")
    
    if args.key:
        km = KeyManager()
        key, exp = km.generate_key(args.key)
        Logger.success(f"Clave generada: {key}")
        Logger.success(f"Expira: {exp}")
        return
    
    if args.revoke:
        km = KeyManager()
        if km.revoke_key(args.revoke):
            Logger.success(f"Clave revocada: {args.revoke}")
        else:
            Logger.error(f"Clave no encontrada: {args.revoke}")
        return
    
    if args.stats:
        km = KeyManager()
        stats = km.get_stats()
        Logger.info(f"Claves totales: {stats['total_keys']}")
        Logger.info(f"Claves activas: {stats['active_keys']}")
        Logger.info(f"Claves expiradas: {stats['expired_keys']}")
        Logger.info(f"Dispositivos: {stats['total_devices']}")
        return
    
    proxy = FreeFireProxy(port=args.port)
    proxy.start()

if __name__ == "__main__":
    main()
