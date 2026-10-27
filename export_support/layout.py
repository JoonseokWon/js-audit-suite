"""Conservative 25-line rows: <=408pt, below Excel's 409pt maximum."""
import unicodedata

MAX_ROW_HEIGHT=409
MAX_LINES=25
MAX_CELL_UTF16=30000


def char_width(ch,column):
    if ch=='\t':return 4-column%4
    if unicodedata.combining(ch) or ch in ('\u200d','\ufe0f'):return 0
    return 2 if unicodedata.east_asian_width(ch) in ('W','F') else 1


def split_display(value,width):
    """Split without inserting/removing a code point. Joining pieces is exact."""
    if not value:return [''],1
    capacity=max(8,int(width)-2);pieces=[];buffer=[];line=1;column=0;units=0;maximum=1
    index=0
    while index<len(value):
        token=value[index:index+2] if value[index:index+2]=='\r\n' else value[index]
        size=sum(2 if ord(ch)>0xFFFF else 1 for ch in token)
        nl=token in ('\n','\r','\r\n')
        next_line=line+1 if nl else line
        next_column=0 if nl else column+char_width(token,column)
        if next_column>capacity:next_line+=1;next_column=char_width(token,0)
        if buffer and (next_line>MAX_LINES or units+size>MAX_CELL_UTF16):
            pieces.append(''.join(buffer));maximum=max(maximum,line)
            buffer=[];line=1;column=0;units=0
            continue
        buffer.append(token);line=next_line;column=next_column;units+=size;index+=len(token)
    pieces.append(''.join(buffer));maximum=max(maximum,line)
    return pieces,maximum


def row_height(lines):return min(MAX_ROW_HEIGHT,max(25,lines*16+8))
