"""Read-only real-widget measurements; reuse the unchanged production test fixture."""
import ctypes
import json
import time
from pathlib import Path

from test_ux_visual_chat_regressions import app, features, isolated_features


def test_chat_layout_scaled_timeline(app, capsys):
    frames=[]
    started=time.monotonic()
    def record(label):
        w=app.msg_list
        frames.append(dict(label=label,ms=round((time.monotonic()-started)*1000,2),
            geometry=app.root.geometry(),root=[app.root.winfo_width(),app.root.winfo_height()],
            list=[w.winfo_width(),w.winfo_height()],total=w._cum[-1],heights=list(w._heights),
            wrap=w._wrap_w,expected_wrap=w._wrap_width(w.winfo_width()),first=w._first_visible,
            top=w.canvasy(0),yview=list(w.yview()),at_bottom=w._at_bottom,
            resize_pending=w._resize_job is not None,scaling=float(w.tk.call('tk','scaling')),
            system_dpi=ctypes.windll.user32.GetDpiForSystem(),app_scale=app._dpi_scale,
            screen=[w.winfo_screenwidth(),w.winfo_screenheight()]))
    flush=app.msg_list._on_resize_flush
    def observed_flush():
        record('before_flush'); flush(); record('after_flush')
    app.msg_list._on_resize_flush=observed_flush
    samples=[(2,'小周','上午的任务都处理好了，分享一下今天的计划。'),
             (1,'我','收到。我把重点整理进工作表，下午一起看。'),
             (3,'陈同学','会议是 15:00，我先准备好资料。'),
             (2,'小周','这是一条比较长的消息，用来检查中文换行、消息留白和窗口缩小时的阅读体验。')]
    rows=[{'seq':i,'uid':uid,'nick':nick,'channel':'public','text':text,'ts':1791518400+i*60}
          for i,(uid,nick,text) in enumerate(samples,1)]
    record('initial'); app.msg_list.load(rows,me_uid=1); app.root.update(); record('loaded')
    app.root.geometry('1000x700')
    for i in range(5):
        app.root.update(); record('original_loop_'+str(i)); time.sleep(.02)
    record('original_assertion_time')
    until=time.monotonic()+.6
    while time.monotonic()<until:
        app.root.update(); time.sleep(.01)
    record('settled_600ms')
    scale=app._dpi_scale
    app.root.geometry(f'{int(1000*scale)}x{int(700*scale)}')
    grow=time.monotonic()
    for delay in (0,.02,.06,.10,.16,.3,.6):
        while time.monotonic()-grow < delay:
            app.root.update(); time.sleep(.005)
        app.root.update(); record('scaled_growth_'+str(delay))
    with capsys.disabled(): print('LAYOUT_TIMELINE '+json.dumps(frames,ensure_ascii=False),flush=True)
    assert len(frames)>=9
