import importlib.util
import json
from pathlib import Path
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODULE = Path(__file__).parents[1] / 'backend/xiaozhi_memory/mem_pet/client.py'
spec = importlib.util.spec_from_file_location('pet_memory_client', MODULE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        self.server.observed = (self.path, self.headers.get('Authorization'),
                                json.loads(self.rfile.read(int(self.headers['Content-Length']))))
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(getattr(self.server,'reply',{'context': '已确认资料：小林，喜欢天文','profile':{'revision':0}}), ensure_ascii=False).encode())

    def log_message(self, *args):
        pass


class VoiceMemoryTest(unittest.TestCase):
    def test_real_http_query_contract_and_credential_header(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = module.PetMemoryClient(f'http://127.0.0.1:{server.server_port}', 'fictional-token')
            self.assertIn('小林', client.recall('我叫什么？'))
            self.assertEqual(server.observed, ('/api/recall', 'Bearer fictional-token', {'query': '我叫什么？'}))
            self.assertEqual(client.recall_snapshot('偏好')['profile']['revision'],0)
        finally:
            server.shutdown()
            server.server_close()

    def test_unavailable_memory_returns_explicit_unavailable_instead_of_invented_facts(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        port = server.server_port
        server.server_close()
        client = module.PetMemoryClient(f'http://127.0.0.1:{port}', 'fictional-token', timeout=0.2)
        with self.assertRaisesRegex(module.MemoryUnavailable, 'MEMORY_UNAVAILABLE'):
            client.recall('我叫什么？')

    def test_only_loopback_endpoints_and_bounded_query(self):
        with self.assertRaises(ValueError):
            module.PetMemoryClient('http://example.com', 'token')
        client = module.PetMemoryClient('http://127.0.0.1:8766', 'token')
        with self.assertRaises(ValueError):
            client.recall('啊' * 1000)

    def test_snapshot_rejects_missing_boolean_negative_and_text_revisions(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        try:
            client=module.PetMemoryClient(f'http://127.0.0.1:{server.server_port}','fictional-token')
            for revision in (None,True,-1,'2',1.5):
                server.reply={'context':'数据','profile':{'revision':revision}}
                with self.assertRaises(module.MemoryUnavailable): client.recall_snapshot('资料')
        finally:
            server.shutdown(); server.server_close()


if __name__ == '__main__':
    unittest.main()
