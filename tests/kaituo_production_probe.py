"""Production Kaito proof with explicitly labelled synthetic funded/terminal fixtures."""
import json,os,secrets,subprocess,tempfile,threading,random
from dataclasses import replace
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from config import CFG
from server import Hub
from server_recovery import StoreCoordinator
from web import serve
from games_pkg.kaituo import KaituoGame
from kaituo_fixtures import fund,near_win
import sys
out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(prefix='kaituo-wire-',dir=Path.cwd()/'_tmp_gui') as tmp:
 folder=Path(tmp);StoreCoordinator.initialize_new(folder/'store');cfg=replace(CFG,admin_pwd=secrets.token_urlsafe(24),bind_host='127.0.0.1',audit_dir=str(folder/'audit'),web_files_dir=str(folder/'files'),discovery_enabled=False,tray_enabled=False,persist_interval=3600)
 hub=Hub(cfg=cfg,store_dir=str(folder/'store'),web_password='');listener=serve(hub,port=0,https=False)
 blocked_stock = {}
 class H(BaseHTTPRequestHandler):
  def log_message(self,*a):pass
  def do_POST(self):
   with hub.rooms.lock:
    room=next(iter(hub.rooms.rooms.values()))
    if self.path=='/seed':room.gs=KaituoGame(room.players,seed=1)
    elif self.path=='/produce':
     g=room.gs;g.rng=random.Random(5);g.robber=(2,4);g.tiles[(0,0)]['num']=8;g.rolled=False;g.last_dice=None;g.production=[]
    elif self.path=='/fund':fund(room.gs)
    elif self.path=='/nearwin':near_win(room.gs)
    elif self.path=='/block-wood':
     inventory = room.gs.res[room.gs.players[0]]
     blocked_stock['wood'] = inventory['wood']
     inventory['wood'] = 0
    elif self.path=='/restore-wood':
     room.gs.res[room.gs.players[0]]['wood'] = blocked_stock.pop('wood')
    else:raise ValueError('Unknown synthetic fixture')
    data=json.dumps(room.gs.snapshot()).encode()
   self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(data)
 control=ThreadingHTTPServer(('127.0.0.1',0),H);worker=threading.Thread(target=control.serve_forever,daemon=True);worker.start()
 try:
  r=subprocess.run(['node','tests/kaituo_production_probe.cjs',str(listener.server_address[1]),str(out),str(control.server_address[1])],timeout=90,capture_output=True,text=True,encoding='utf-8',creationflags=0x08000000 if os.name=='nt' else 0)
  (out/'production-browser.txt').write_text(r.stdout+r.stderr,encoding='utf-8');assert r.returncode==0,r.stdout+r.stderr
  delivered=json.loads((out/'production-final-state.json').read_text(encoding='utf-8'));assert max(delivered['state']['score'].values())==10 and delivered['state']['winner_uid'] is not None
  print('kaituo production HTTP/SSE setup/robber/build/trade/terminal PASS; staged fixtures explicit')
 finally:control.shutdown();control.server_close();worker.join(5);hub.shutdown(normal=False,timeout=8)
