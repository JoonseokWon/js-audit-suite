"""Native Tk application integration checks + capture only our rendered window.
Controls are invoked by Tk, not by external user-input automation.
Native OS file dialog interaction is explicitly not claimed.
"""
import json,sys,time,platform,traceback,ctypes,struct,zlib
from pathlib import Path

def capture_window(root,path):
    from ctypes import wintypes
    user=ctypes.WinDLL('user32',use_last_error=True);gdi=ctypes.WinDLL('gdi32',use_last_error=True)
    user.GetParent.argtypes=[wintypes.HWND];user.GetParent.restype=wintypes.HWND
    user.GetWindowRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
    user.GetDC.argtypes=[wintypes.HWND];user.GetDC.restype=wintypes.HDC
    user.ReleaseDC.argtypes=[wintypes.HWND,wintypes.HDC]
    user.PrintWindow.argtypes=[wintypes.HWND,wintypes.HDC,wintypes.UINT]
    gdi.CreateCompatibleDC.argtypes=[wintypes.HDC];gdi.CreateCompatibleDC.restype=wintypes.HDC
    gdi.CreateCompatibleBitmap.argtypes=[wintypes.HDC,ctypes.c_int,ctypes.c_int];gdi.CreateCompatibleBitmap.restype=wintypes.HBITMAP
    gdi.SelectObject.argtypes=[wintypes.HDC,wintypes.HGDIOBJ];gdi.SelectObject.restype=wintypes.HGDIOBJ
    gdi.GetDIBits.argtypes=[wintypes.HDC,wintypes.HBITMAP,wintypes.UINT,wintypes.UINT,ctypes.c_void_p,ctypes.c_void_p,wintypes.UINT]
    gdi.DeleteObject.argtypes=[wintypes.HGDIOBJ];gdi.DeleteDC.argtypes=[wintypes.HDC]
    hwnd=user.GetParent(root.winfo_id());rect=wintypes.RECT();user.GetWindowRect(hwnd,ctypes.byref(rect));width,height=rect.right-rect.left,rect.bottom-rect.top
    hdc=user.GetDC(hwnd);mem=gdi.CreateCompatibleDC(hdc);bitmap=gdi.CreateCompatibleBitmap(hdc,width,height);old=gdi.SelectObject(mem,bitmap)
    try:
        if not user.PrintWindow(hwnd,mem,2):raise RuntimeError('PrintWindow returned failure')
        gdi.SelectObject(mem,old)
        header=struct.pack('<IiiHHIIiiII',40,width,-height,1,32,0,width*height*4,0,0,0,0)
        info=ctypes.create_string_buffer(header+bytes(12));buf=ctypes.create_string_buffer(width*height*4)
        if gdi.GetDIBits(mem,bitmap,0,height,buf,info,0)!=height:raise RuntimeError('GetDIBits failed')
        pixels=buf.raw
        if len(set(pixels[::97]))<3:raise RuntimeError('Capture is blank')
        scan=bytearray()
        for y in range(height):
            scan.append(0)
            for x in range(width):
                i=(y*width+x)*4;scan.extend((pixels[i+2],pixels[i+1],pixels[i]))
        def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
        path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(scan))+chunk(b'IEND',b''))
        return {'path':str(path),'width':width,'height':height}
    finally:gdi.SelectObject(mem,old);gdi.DeleteObject(bitmap);gdi.DeleteDC(mem);user.ReleaseDC(hwnd,hdc)

def destroy_test_window(root):
    """Cancel this test interpreter's timers before opening the next Tk root."""
    if root:
        for timer in root.tk.splitlist(root.tk.call('after','info')):root.after_cancel(timer)
        root.destroy()

