import http.server
import urllib.request
import json
import os

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

os.chdir(os.path.expanduser('~/mac-setup/agent'))
print('Dashboard + Proxy auf http://localhost:8999')
http.server.HTTPServer(('', 8999), Handler).serve_forever()
