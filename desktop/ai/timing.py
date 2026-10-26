"""UI-thread elapsed time only; never alters provider or queue status messages."""
from time import monotonic
import tkinter as tk


class AITiming:
    def stop_ai_elapsed(self,clear=True):
        timer=getattr(self,'_ai_elapsed_timer',None)
        self._ai_elapsed_timer=None;self._ai_job_started=None
        if timer is not None:
            try:self.root.after_cancel(timer)
            except tk.TclError:pass
        if clear and hasattr(self,'ai_elapsed'):
            try:self.ai_elapsed.set('')
            except tk.TclError:pass

    def start_ai_elapsed(self):
        self.stop_ai_elapsed();self._ai_job_started=monotonic()
        self.update_ai_elapsed()

    def update_ai_elapsed(self):
        timer=getattr(self,'_ai_elapsed_timer',None);self._ai_elapsed_timer=None
        if timer is not None:
            try:self.root.after_cancel(timer)
            except tk.TclError:pass
        started=getattr(self,'_ai_job_started',None)
        if started is None:return
        if self.cancel.is_set():
            self.stop_ai_elapsed()
            self.ai_elapsed.set('취소 요청됨 · 작업 종료를 기다리는 중')
            return
        seconds=max(0,int(monotonic()-started));minutes,seconds=divmod(seconds,60)
        self.ai_elapsed.set(f'작업 경과 {minutes:02}:{seconds:02} · 준비 중단으로 취소')
        self._ai_elapsed_timer=self.root.after(1000,self.update_ai_elapsed)
