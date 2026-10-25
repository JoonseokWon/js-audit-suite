"""Launch independent local tools without mixing their inputs into an engagement."""
from pathlib import Path
import subprocess
import sys


def open_cashflow(host):
    if host.busy or not host.check_navigation():
        return False
    if getattr(sys,'frozen',False):
        command=[sys.executable,'--tool','cashflow']
    else:
        command=[sys.executable,'-B',str(Path(__file__).resolve().parents[2]/'app.py'),
                 '--tool','cashflow']
    subprocess.Popen(command,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    host.status.set('별도 현금흐름표 도구를 열었어요. 이 도구의 입력·결과는 현재 업무와 자동 연결하지 않아요.')
    return True
