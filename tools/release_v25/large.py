import sys
from .config import *
from .policy import read,run,require
from .build import pinned


def verify(frozen=False):
    folder,_=pinned();path=QA/'large-input-10002.xlsx'
    from .large_case import create
    if not path.exists():create(path)
    name='frozen-large' if frozen else 'source-large';report=QA/name/'report.json'
    args=['--self-test-large-ledger','--report',report,'--input',path,'--rows','10002','--total','5001']
    command=[PROJECT/'실행파일'/EXE,*args] if frozen else [sys.executable,'-B','-X','utf8','app.py',*args]
    run(command,QA/(name+'.log'),PROJECT/'실행파일' if frozen else folder)
    result=read(report);require(result['ok'] and result['rows']==10002,'10,002행 경계 검증 실패')
    pinned();return result
