"""Capture only a synthetic test HWND, including on a private desktop."""
import ctypes as c
from ctypes import wintypes as w
from PIL import Image


def capture(root, path):
    root.update()
    u,g=c.windll.user32,c.windll.gdi32
    u.GetParent.argtypes=[w.HWND];u.GetParent.restype=w.HWND
    u.GetWindowDC.argtypes=[w.HWND];u.GetWindowDC.restype=w.HDC
    g.CreateCompatibleDC.argtypes=[w.HDC];g.CreateCompatibleDC.restype=w.HDC
    g.CreateCompatibleBitmap.argtypes=[w.HDC,c.c_int,c.c_int];g.CreateCompatibleBitmap.restype=w.HBITMAP
    g.SelectObject.argtypes=[w.HDC,w.HANDLE];g.SelectObject.restype=w.HANDLE
    g.DeleteObject.argtypes=[w.HANDLE];g.DeleteDC.argtypes=[w.HDC]
    u.ReleaseDC.argtypes=[w.HWND,w.HDC];u.PrintWindow.argtypes=[w.HWND,w.HDC,w.UINT]
    class Header(c.Structure):
        _fields_=[('size',w.DWORD),('width',w.LONG),('height',w.LONG),('planes',w.WORD),('bits',w.WORD),('compression',w.DWORD),('image',w.DWORD),('x',w.LONG),('y',w.LONG),('colors',w.DWORD),('important',w.DWORD)]
    hwnd=u.GetParent(root.winfo_id());rect=w.RECT();u.GetWindowRect(hwnd,c.byref(rect));width,height=rect.right-rect.left,rect.bottom-rect.top
    dc=u.GetWindowDC(hwnd);mem=g.CreateCompatibleDC(dc);bmp=g.CreateCompatibleBitmap(dc,width,height);old=g.SelectObject(mem,bmp)
    try:
        assert u.PrintWindow(hwnd,mem,2), 'PrintWindow failed'
        header=Header(c.sizeof(Header),width,-height,1,32,0,0,0,0,0,0);buf=c.create_string_buffer(width*height*4)
        g.GetDIBits.argtypes=[w.HDC,w.HBITMAP,w.UINT,w.UINT,c.c_void_p,c.c_void_p,w.UINT]
        assert g.GetDIBits(mem,bmp,0,height,buf,c.byref(header),0)
        image=Image.frombuffer('RGB',(width,height),buf,'raw','BGRX',0,1)
        path.parent.mkdir(parents=True,exist_ok=True);image.save(path)
    finally:g.SelectObject(mem,old);g.DeleteObject(bmp);g.DeleteDC(mem);u.ReleaseDC(hwnd,dc)
