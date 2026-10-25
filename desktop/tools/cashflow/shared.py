"""Explicit dependencies shared by the independent tool's small controllers."""
from datetime import datetime
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from .engine import calculate,Cancelled,InputBook,Row,SCHEMA,SETTINGS
from .excel_io import read_input,export_result,save_input,InputError,input_error_result
from .samples import sample_cases

LABELS={'CFO':'영업활동','CFI':'투자활동','CFF':'재무활동','FX':'환율영향',
        'CASH_DELTA':'현금증감','CASH_OPEN':'기초현금','CASH_CLOSE':'기말현금'}
SCOPE='독립 도구 · 통합 업무 DB·원장·조서에 자동으로 기록하지 않아요.'
