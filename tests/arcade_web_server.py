"""Loopback-only synthetic game fixture serving the production page and rules."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import os
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import web
from boardgames.gallery import read_resource
from games_pkg.halloween import HalloweenGame
from games_pkg.yahtzee import YahtzeeGame, CATS
from games_pkg.drawguess import DrawGuessGame
from games_pkg.calc24 import Calc24Game
from games_pkg.guess_number import GuessNumberGame
from games_pkg.tile2048 import Tile2048Game

game=HalloweenGame([7,8],seed=8)
game.stack[7]=[0]*8;game.area=[0]*4;game.area_owners=[7,8,7,8];game.counts=[4,0,0,0,0]
game_name=os.environ.get('ARCADE_GAME','halloween')
if game_name=='yahtzee':game=YahtzeeGame([7,8],seed=23)
if game_name=='drawguess':game=DrawGuessGame([7,8],seed=3)
if game_name=='calc24':game=Calc24Game([7,8],seed=3);game.cards=[1,2,3,4]
if game_name=='guess_number':game=GuessNumberGame([7,8],seed=1)
if game_name=='tile2048':game=Tile2048Game([7],seed=2)
actions=[]


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def send(self,data,mime='application/json'):
        if not isinstance(data,bytes):data=json.dumps(data,ensure_ascii=False).encode('utf-8')
        self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    def do_GET(self):
        if self.path=='/':return self.send(web._SERVED_PAGE(),'text/html; charset=utf-8')
        if self.path=='/start':
            game.area=[];game.area_owners=[];game.counts=[0]*5;return self.send({'ok':True})
        if self.path=='/decision':
            game.area=[0]*4;game.area_owners=[7,8,7,8];game.counts=[4,0,0,0,0];return self.send({'ok':True})
        if self.path=='/final':
            if game_name=='yahtzee':
                game.turn=0;game.rolled=True;game.dice=[6]*5;game.scores={u:{c:0 for c in CATS} for u in [7,8]};game.scores[7]['yahtzee']=None;return self.send({'ok':True})
            game.area=[0]*4;game.area_owners=[7,8,7,8];game.counts=[4,0,0,0,0];game.stack[7]=[0];return self.send({'ok':True})
        if self.path=='/fixture':return self.send({'state':game.snapshot(),'private':game.private(7),'actions':actions,'legal':game.legal_moves(7) if game_name=='tile2048' else None})
        if self.path=='/tile-stage':
            game.board=[[2,2,4,8],[16,32,64,128],[256,512,1024,0],[0,0,0,0]];game.score=0;return self.send({'ok':True})
        if self.path=='/tile-win':
            game.board=[[1024,1024,0,0]]+[[0]*4 for _ in range(3)];game.score=0;return self.send({'ok':True})
        if self.path=='/math-final':
            game._next_round();game.round_no=5;game.cards=[3,3,8,8];return self.send({'ok':True})
        if self.path=='/math-end':
            game.tick(game.reveal_end_at+1);return self.send({'ok':True})
        if self.path.startswith('/game-art/'):
            try:data,mime=read_resource(self.path.split('/')[-1].split('?')[0]);return self.send(data,mime)
            except FileNotFoundError:pass
        self.send({})
    def do_POST(self):
        data=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))) or '{}')
        if self.path=='/api/game' and data.get('op')=='action':
            try:game.act(8 if game_name in ('drawguess','guess_number') and 'guess' in data['action'] else 7,data['action']);actions.append(data['action']);return self.send({'ok':True})
            except Exception as error:return self.send({'ok':False,'error':str(error)})
        self.send({'ok':True})


server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
print(server.server_port,flush=True)
server.serve_forever()
