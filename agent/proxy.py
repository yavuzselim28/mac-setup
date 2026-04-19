import http.server
import urllib.request
import json
import os
import subprocess
import threading

AGENT_DIR = os.path.expanduser('~/mac-setup/agent')
AGENT_SCRIPT = os.path.join(AGENT_DIR, 'platform_agent_lg.py')
LOG_FILE = os.path.join(AGENT_DIR, 'logs/agent.log')

# Laufender Agent-Prozess
agent_proc = None
agent_lock = threading.Lock()

def run_agent_bg():
    global agent_proc
    with agent_lock:
        if agent_proc and agent_proc.poll() is None:
            return False  # läuft bereits
        agent_proc = subprocess.Popen(
            ['/opt/homebrew/bin/python3', AGENT_SCRIPT],
            cwd=AGENT_DIR,
            stdout=open(LOG_FILE, 'a'),
            stderr=subprocess.STDOUT
        )
        return True

def agent_running():
    global agent_proc
    return agent_proc is not None and agent_proc.poll() is None

class Handler(http.server.SimpleHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/llm':
            length = int(self.headers['Content-Length'])
            body = self.rfile.read(length)
            try:
                req = urllib.request.Request(
                    'http://localhost:8080/v1/chat/completions',
                    data=body,
                    headers={'Content-Type': 'application/json'}
                )
                with urllib.request.urlopen(req, timeout=120) as r:
                    response = r.read()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(response)
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())

        elif self.path == '/run-agent':
            started = run_agent_bg()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            if started:
                self.wfile.write(json.dumps({'status': 'started', 'pid': agent_proc.pid}).encode())
            else:
                self.wfile.write(json.dumps({'status': 'already_running', 'pid': agent_proc.pid}).encode())

        else:
            super().do_GET()

    def do_GET(self):
        if self.path == '/agent-status':
            running = agent_running()
            pid = agent_proc.pid if agent_proc else None
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'running': running, 'pid': pid}).encode())
        else:
            super().do_GET()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def log_message(self, format, *args):
        pass

os.chdir(AGENT_DIR)
print('Dashboard + Proxy auf http://localhost:8999')
http.server.HTTPServer(('', 8999), Handler).serve_forever()
