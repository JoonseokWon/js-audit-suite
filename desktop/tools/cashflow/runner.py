"""Cash-flow desktop actions; calculation policy remains in the copied engine."""
from .shared import *

class RunnerActions:

    def set_running(self, running):
        self.running = running
        self.run_button.configure(state='disabled' if running else 'normal')
        self.cancel_button.configure(state='normal' if running else 'disabled')
        self.save_button.configure(state='normal' if self.result is not None and (not running) else 'disabled')
        if running:
            self.progress.start(12)
        else:
            self.progress.stop()

    def clear_result(self):
        self.result = None
        for tree in (self.diff_tree, self.line_tree, self.trace_tree):
            tree.delete(*tree.get_children())
        for val in self.cards.values():
            val.set('—')
        self.save_button.configure(state='disabled')

    def invalidate(self):
        if self.cancel_event:
            self.cancel_event.set()
        self.generation += 1
        self.set_running(False)

    def start(self):
        if self.source_path is None and self.example is None:
            messagebox.showinfo('입력 필요', '예제를 불러오거나 Excel 파일을 선택하세요.', parent=self.root)
            return
        self.invalidate()
        self.clear_result()
        token = self.generation
        cancellation = threading.Event()
        self.cancel_event = cancellation
        source = self.source_path
        example = self.example
        self.set_running(True)
        self.status.set('원본 읽기 · 입력 검증 · 명세 대사 중…')

        def work():
            try:
                book = read_input(source, cancellation) if source else example
                result = calculate(book, cancellation)
                self.messages.put((token, 'result', result))
            except Cancelled:
                self.messages.put((token, 'cancel', None))
            except InputError as e:
                self.messages.put((token, 'result', input_error_result(e)))
            except Exception as e:
                self.messages.put((token, 'error', str(e)))
        threading.Thread(target=work, daemon=True, name='cashflow-validation').start()

    def poll(self):
        self._poll_timer = None
        if self._closed:
            return
        try:
            while True:
                token, kind, payload = self.messages.get_nowait()
                if token != self.generation:
                    continue
                self.set_running(False)
                if kind == 'result':
                    self.result = payload
                    self.render()
                elif kind == 'error':
                    self.clear_result()
                    self.status.set('파일 처리 실패 · 원본/권한/형식을 확인하세요')
                    messagebox.showerror('처리 오류', payload, parent=self.root)
                else:
                    self.status.set('실행 취소됨')
        except queue.Empty:
            pass
        if not self._closed and self.root.winfo_exists():
            self._poll_timer = self.root.after(50, self.poll)

    def cancel_run(self):
        self.invalidate()
        self.clear_result()
        self.status.set('실행 취소됨 · 다시 검증할 수 있습니다')

    def close(self):
        self.invalidate()
        self._closed = True
        if self._poll_timer is not None:
            try:
                self.root.after_cancel(self._poll_timer)
            except tk.TclError:
                pass
            self._poll_timer = None
        self.display.close()
        self.root.destroy()
