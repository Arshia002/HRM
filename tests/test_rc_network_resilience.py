import shutil, ssl, tempfile, threading, unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from sazmanhr.api_client import ApiClient, ApiError
from sazmanhr.database import Repository
from sazmanhr.server import ApiServer
from sazmanhr.tls import ensure_self_signed_certificate

ROOT=Path(__file__).resolve().parents[1]; SEED=ROOT/'data/seed/sazmanhr-seed.sqlite'

def start_tls(repo, root, port=0):
    cert,key,fingerprint=ensure_self_signed_certificate(root)
    server=ApiServer(('127.0.0.1',port),repo,tls_enabled=True); ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); ctx.load_cert_chain(cert,key); server.socket=ctx.wrap_socket(server.socket,server_side=True)
    t=threading.Thread(target=server.serve_forever,daemon=True);t.start();return server,t,fingerprint

class RcNetworkResilienceTests(unittest.TestCase):
    def test_six_clients_concurrently_operate_over_pinned_tls(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); db=root/'hrm.sqlite'; shutil.copy2(SEED,db); repo=Repository(db); password='RC!Network1500'
            for i in range(6): repo.create_user(f'rc.admin.{i}',f'RC مدیر {i}',password,'admin',must_change_password=False)
            server,t,fp=start_tls(repo,root); clients=[ApiClient(f'https://127.0.0.1:{server.server_address[1]}',tls_fingerprint=fp) for _ in range(6)]
            try:
                for i,c in enumerate(clients): c.login(f'rc.admin.{i}',password)
                people=clients[0].request('GET','/api/personnel',query={'limit':6})['items']
                def work(pair):
                    i,c=pair; d=c.request('GET',f"/api/personnel/{people[i]['id']}"); d['actual_location']=f'RC-TLS-{i}'; return c.request('POST','/api/personnel',d)
                with ThreadPoolExecutor(max_workers=6) as pool: out=list(pool.map(work,enumerate(clients)))
                self.assertEqual(len(out),6)
            finally:
                server.shutdown();server.server_close();t.join(timeout=3)
    def test_disconnect_is_reported_and_reconnect_recovers(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); db=root/'hrm.sqlite'; shutil.copy2(SEED,db); repo=Repository(db); server,t,fp=start_tls(repo,root); port=server.server_address[1]; c=ApiClient(f'https://127.0.0.1:{port}',tls_fingerprint=fp,timeout=.5)
            self.assertEqual(c.health()['status'],'ok'); server.shutdown();server.server_close();t.join(timeout=3)
            with self.assertRaises(ApiError): c.health()
            server2,t2,_=start_tls(repo,root,port)
            try: self.assertEqual(c.health()['status'],'ok')
            finally: server2.shutdown();server2.server_close();t2.join(timeout=3)
    def test_changed_certificate_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); db=root/'hrm.sqlite'; shutil.copy2(SEED,db); repo=Repository(db); server,t,fp=start_tls(repo,root)
            try:
                bad=('00:'*31)+'00'; c=ApiClient(f'https://127.0.0.1:{server.server_address[1]}',tls_fingerprint=bad)
                with self.assertRaisesRegex(ApiError,'اثر انگشت'): c.health()
            finally: server.shutdown();server.server_close();t.join(timeout=3)
