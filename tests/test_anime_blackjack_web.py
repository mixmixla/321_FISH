"""Blackjack headless Chromium uses real production REST and Hub dispatch."""
import ctypes
from dataclasses import replace
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import subprocess
import threading
from urllib.parse import urlsplit
import winreg

from config import CFG
from server import Hub
from web import _Handler
from test_anime_blackjack import scene


def test_headless_blackjack_hit_stand_settle_mobile_spectator(tmp_path):
    folder=ctypes.create_unicode_buffer(32768)
    assert ctypes.windll.shell32.SHGetFolderPathW(None,0x1c,None,0,folder)==0
    cache=Path(folder.value)/'ms-playwright'
    if not (cache/'.links').is_dir():
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Volatile Environment') as key:
            cache=Path(winreg.QueryValueEx(key,'USERPROFILE')[0])/'AppData/Local/ms-playwright'
    module=next(Path(p.read_text(encoding='utf-8').strip()) for p in (cache/'.links').iterdir())
    h=Hub(cfg=replace(CFG,bind_host='127.0.0.1',audit_dir=str(tmp_path/'audit'),web_files_dir=str(tmp_path/'files')),audit_dir=str(tmp_path/'audit'))
    user,token=h.login_web('合成翡翠甲','127.0.0.1');other,other_token=h.login_web('合成翡翠乙','127.0.0.1');assert user and other
    room=h.rooms.create(user.uid,'blackjack');h.rooms.join(other.uid,room.room_id);h.rooms.start(user.uid,room.room_id)
    room.gs=scene((user.uid,other.uid))
    class Handler(_Handler):
        hub=h
        def do_GET(self):
            if urlsplit(self.path).path in ('/__cards/scene','/__cards/reset'):
                with h.lock:
                    if urlsplit(self.path).path=='/__cards/reset':room.gs=scene((user.uid,other.uid))
                    data={'room':room.summary(),'state':room.gs.snapshot()}
                raw=json.dumps(data).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
            else:super().do_GET()
    httpd=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=httpd.serve_forever,daemon=True);thread.start()
    config=tmp_path/'browser.json';config.write_text(json.dumps({'module':str(module),'cache':str(cache),'url':f'http://127.0.0.1:{httpd.server_port}',
        'uid':user.uid,'other':other.uid,'token':token,'otherToken':other_token,'out':str(tmp_path)}),encoding='utf-8')
    try:
        result=subprocess.run([shutil.which('node'),str(Path(__file__).with_name('cards_blackjack_browser.cjs')),str(config)],capture_output=True,text=True,encoding='utf-8',timeout=45)
        assert result.returncode==0,result.stdout+result.stderr
        report=json.loads(result.stdout);assert report['actions']==3 and report['holeHidden'] and report['revealed'] and report['mobileNoOverflow']
        assert report['pendingProbe']['sameFrameRedrawBlocked'] and report['pendingProbe']['wrapperRedrawBlocked']
        assert report['pendingProbe']['newFrameReleases'] and report['pendingProbe']['explicitRejectionRetries']
    finally:httpd.shutdown();httpd.server_close();thread.join(5)
