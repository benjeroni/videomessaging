"""Give browser tests a localhost origin, like the documented SSH tunnel."""
import os
import select
import socket
import socketserver
import threading
from urllib.parse import urlsplit

def browser_base():
    base = os.getenv('SMOKE_BASE_URL', 'http://127.0.0.1:8000')
    parsed = urlsplit(base)
    if parsed.scheme != 'http' or parsed.hostname in ('localhost', '127.0.0.1', '::1'):
        return base
    target = (parsed.hostname, parsed.port or 80)
    class Forwarder(socketserver.BaseRequestHandler):
        def handle(self):
            try:
                with socket.create_connection(target, timeout=10) as upstream:
                    upstream.settimeout(None)
                    peers = [self.request, upstream]
                    while True:
                        readable, _, _ = select.select(peers, [], [], 60)
                        if not readable:
                            return
                        for source in readable:
                            data = source.recv(65536)
                            if not data:
                                return
                            (upstream if source is self.request else self.request).sendall(data)
            except OSError:
                return
    server = socketserver.ThreadingTCPServer(('127.0.0.1', 0), Forwarder)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f'http://127.0.0.1:{server.server_address[1]}'
