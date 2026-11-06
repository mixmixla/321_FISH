"""Headless Chromium clicks production UNO, /api/game and the real Hub."""
from dataclasses import replace
import ctypes
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import winreg
from urllib.parse import urlsplit, parse_qs

from config import CFG
from server import Hub
from web import _Handler
from test_anime_uno import scene


def test_uno_production_callbacks_bind_all_room_and_login_identities(tmp_path):
    from boardgames.cards_uno_web import WEB_JS
    data=tmp_path/'callbacks.json';data.write_text(json.dumps({'versions':[{'sha':'candidate','js':WEB_JS,'require_blocked':True}]}),encoding='utf-8')
    result=subprocess.run([shutil.which('node'),str(Path(__file__).with_name('cards_uno_guard_probe.cjs')),str(data),str(tmp_path/'uno-guard-results.json')],
                          capture_output=True,text=True,encoding='utf-8',timeout=10)
    assert result.returncode==0,result.stdout+result.stderr
    report=json.loads(result.stdout)['results'][0]
    assert report['normal_sends']==3 and report['stale_cases']==45 and report['stale_sends']==0


def test_headless_actual_http_cards_draw_colors_mobile_and_spectator(tmp_path):
    # The gate remaps LOCALAPPDATA to a fresh synthetic profile. Discover only
    # the installed executable cache through the Windows known-folder API;
    # browser user data still lives in Playwright's new temporary profile.
    folder = ctypes.create_unicode_buffer(32768)
    assert ctypes.windll.shell32.SHGetFolderPathW(None, 0x1c, None, 0, folder) == 0
    cache = Path(folder.value)/'ms-playwright'
    if not (cache/'.links').is_dir():
        # Read the host installation location only; never open a browser profile.
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Volatile Environment') as key:
            profile = Path(winreg.QueryValueEx(key, 'USERPROFILE')[0])
        cache = profile/'AppData/Local/ms-playwright'
    links = cache/'.links'
    modules = [Path(p.read_text(encoding='utf-8').strip()) for p in links.iterdir()]
    module = next((p for p in modules if (p/'package.json').is_file()), None)
    assert module, 'Existing headless Chromium runtime is required'
    h = Hub(cfg=replace(CFG, bind_host='127.0.0.1', audit_dir=str(tmp_path/'audit'),
                       web_files_dir=str(tmp_path/'files')), audit_dir=str(tmp_path/'audit'))
    user, token = h.login_web('合成UNO甲', '127.0.0.1')
    other, _ = h.login_web('合成UNO乙', '127.0.0.1')
    assert user and other
    room = h.rooms.create(user.uid, 'uno'); h.rooms.join(other.uid, room.room_id); h.rooms.start(user.uid, room.room_id)
    def reset():
        g = scene(); g.players = [user.uid, other.uid]
        g.hands = {user.uid: g.hands[7], other.uid: g.hands[8]}
        g.scores = {user.uid: 0, other.uid: 0}; room.gs = g
    reset()
    class Handler(_Handler):
        hub = h
        def do_GET(self):
            parsed = urlsplit(self.path)
            if parsed.path in ('/__cards/scene', '/__cards/reset', '/__cards/finish-ready'):
                # Test fixture control on a random loopback port, absent from the app.
                with h.lock:
                    if parsed.path.endswith('reset'): reset()
                    if parsed.path.endswith('finish-ready'):
                        reset(); room.gs.hands[user.uid] = room.gs.hands[user.uid][:1]
                    uid = int(parse_qs(parsed.query).get('uid', [str(user.uid)])[0])
                    data = {'room': room.summary(), 'state': room.gs.snapshot(), 'private': room.gs.private(uid)}
                raw = json.dumps(data).encode()
                self.send_response(200); self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw))); self.end_headers(); self.wfile.write(raw)
            else:
                super().do_GET()
    httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True); thread.start()
    config = tmp_path/'browser.json'
    config.write_text(json.dumps({'module': str(module), 'url': f'http://127.0.0.1:{httpd.server_port}',
                                 'uid': user.uid, 'other': other.uid, 'token': token, 'cache': str(cache),
                                 'out': str(tmp_path)}), encoding='utf-8')
    try:
        result = subprocess.run([shutil.which('node'), str(Path(__file__).with_name('cards_uno_browser.cjs')), str(config)],
                                capture_output=True, text=True, encoding='utf-8', timeout=50)
        assert result.returncode == 0, result.stdout+result.stderr
        report = json.loads(result.stdout)
        assert report['actions'] == 8 and report['spectatorHidden'] and report['mobileNoOverflow']
        assert report['artLoaded'] and report['duplicateIdsDistinct']
        assert report['pendingProbe']['sameFrameRedrawBlocked'] and report['pendingProbe']['wrapperRedrawBlocked']
        assert report['pendingProbe']['newFrameReleases'] and report['pendingProbe']['explicitRejectionRetries']
        print('UNO_WEB_EVIDENCE', tmp_path, report)
    finally:
        httpd.shutdown(); httpd.server_close(); thread.join(5)
