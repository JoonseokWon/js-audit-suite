"""Pure logical-to-physical geometry. No desktop mutation."""
import math
from .constants import SCALE_OPTIONS

def normalize_scale(value):
    try:
        text=str(value).strip().removesuffix('%').strip()
        number=float(text)
    except (TypeError,ValueError):raise ValueError('화면 배율은 90·100·110·125·150·175% 중에서 선택하세요.') from None
    if not math.isfinite(number) or number not in SCALE_OPTIONS:raise ValueError('지원하지 않는 화면 배율')
    return int(number)

def display_metrics(dpi=96,scale=100,linespace=None):
    dpi=float(dpi)
    if not math.isfinite(dpi) or not 48<=dpi<=768:raise ValueError('유효한 DPI 범위가 아닙니다.')
    percent=normalize_scale(scale);factor=dpi/96*percent/100
    px=lambda n:max(1,round(n*factor))
    line=math.ceil(11*dpi/72*percent/100*1.4) if linespace is None else int(linespace)
    return {'dpi':dpi,'percent':percent,'factor':factor,'tk_scaling':dpi/72*percent/100,
            'normal_points':11,'small_points':10,'row_height':max(px(30),line+px(8)),
            'column_width':px(170),'button_padding':(px(10),px(6)),'scrollbar_width':px(16)}

def window_geometry(work_area,dpi=96,scale=100):
    """Client geometry with enough margins for the Windows frame and taskbar."""
    if len(work_area)!=4:raise ValueError('작업영역은 left, top, right, bottom이어야 합니다.')
    left,top,right,bottom=map(int,work_area);w,h=right-left,bottom-top
    if w<160 or h<160:raise ValueError('작업영역이 너무 작습니다.')
    metric=display_metrics(dpi,scale);factor=metric['factor'];osfactor=float(dpi)/96
    margin_x=min(max(12,round(24*osfactor)),w//8)
    frame_margin=min(max(32,round(64*osfactor)),h//4)
    # App text zoom must not force the window or its minimum size to grow.
    width=min(round(1680*osfactor),w-2*margin_x)
    height=min(round(1080*osfactor),h-frame_margin)
    x=left+(w-width)//2;y=top+max(8,round(8*osfactor))
    return {'width':width,'height':height,'x':x,'y':y,
            'min_width':min(width,960),'min_height':min(height,640),
            'work_area':(left,top,right,bottom)}
