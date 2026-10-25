"""Workspaces native desktop actions."""
from desktop.shared import *
from desktop.widgets.flow import FlowFrame
from desktop.widgets.tables import tree, fill

class WorkspacesActions:

    def new_dialog(self):
        if self.busy or not self.check_navigation():
            return
        win = tk.Toplevel(self.root)
        win.title('새 감사 업무')
        win.transient(self.root)
        frame = ttk.Frame(win, padding=15)
        frame.pack(fill='both', expand=True)
        fields = {}
        defaults = {'회사코드': '', '회사명': '', '시작일': '2026-01-01', '기준일': '2026-12-31', '회계체계': 'K-IFRS', '감사기준': '한국 회계감사기준 / 해당 보고기간 시행일 확인', '작성자': ''}
        for i, (k, v) in enumerate(defaults.items()):
            ttk.Label(frame, text=k).grid(row=i, column=0, sticky='w', pady=5)
            var = tk.StringVar(value=v)
            fields[k] = var
            ttk.Entry(frame, textvariable=var, width=55).grid(row=i, column=1)

        def create():
            if self.busy or not self.check_navigation():
                return
            folder = filedialog.askdirectory(parent=win, title='새 업무를 만들 빈 폴더 선택')
            if folder:

                def op():
                    self.ws = Workspace(folder, create={k: v.get() for k, v in fields.items()})
                    self.reset_workspace_view()
                    self.active_sector = None
                    self.sector_selection()
                    self.refresh()
                    win.destroy()
                self.call(op)
        ttk.Button(frame, text='빈 폴더 선택 후 생성', command=create).grid(row=8, column=1, sticky='e', pady=10)

    def open_workspace(self, folder):
        if self.busy:
            raise AuditError('검사 중 업무를 바꿀 수 없습니다.')
        ws = Workspace(folder)
        self.ws = ws
        self.reset_workspace_view()
        self.active_sector = None
        self.sector_selection()
        self.refresh()

    def open_dialog(self):
        if self.busy or not self.check_navigation():
            return
        folder = filedialog.askdirectory(parent=self.root, title='업무.sqlite3가 있는 업무 폴더')
        if folder:
            self.call(lambda: self.open_workspace(folder))

    def start_demo(self, folder, full=False, analytics=False):
        if self.busy:
            raise AuditError('검사 실행 중')
        self.ws = Workspace(folder, create={'회사코드': 'SYNTH01', '회사명': '합성 제조회사 (SYNTHETIC ONLY)', '시작일': '2026-01-01', '기준일': '2026-12-31', '회계체계': 'K-IFRS / 합성 시나리오', '감사기준': '한국 회계감사기준 / 학습용', '작성자': '합성작성자', '더미업무': True})
        self.reset_workspace_view()
        self.active_sector = None
        self.sector_selection()
        self.refresh()
        self.launch([(m, resource('samples', '통합', f)) for m, f in (ANALYTIC_DEMO_FILES if analytics else FULL_DEMO_FILES if full else DEMO_FILES)])

    def demo_dialog(self):
        if self.busy or not self.check_navigation():
            return
        folder = filedialog.askdirectory(parent=self.root, title='더미업무를 보관할 상위 폴더 선택')
        if folder:
            self.call(lambda: self.start_demo(Path(folder) / ('더미업무_' + datetime.now(timezone(timedelta(hours=9))).strftime('%Y%m%d_%H%M%S')), full=True, analytics=True))

    def case_dialog(self):
        if self.busy or not self.check_navigation():
            return
        data = json.loads(resource('worker_cases.json').read_text(encoding='utf-8'))
        win = tk.Toplevel(self.root)
        win.title('계정별 독립 증빙연습')
        win.transient(self.root)
        ttk.Label(win, text='현재 업무와 분리된 새 합성 업무를 만듭니다. 33개 사례는 서로 합산하지 않습니다.', padding=12).pack()
        selected = tk.StringVar(value=data[0]['worker'] + ' | ' + data[0]['case_id'])
        box = ttk.Combobox(win, textvariable=selected, state='readonly', width=75, values=[x['worker'] + ' | ' + x['case_id'] for x in data])
        box.pack(padx=12, pady=10)

        def start():
            if self.busy or not self.check_navigation():
                return
            entry = data[box.current()]
            folder = filedialog.askdirectory(parent=win, title='새 독립 연습 업무를 만들 상위 폴더')
            if not folder:
                return

            def op():
                self.ws = Workspace(Path(folder) / ('계정연습_' + entry['case_id'] + '_' + datetime.now().strftime('%Y%m%d_%H%M%S')), create={'회사코드': 'SYNTH01', '회사명': '독립 계정 합성 사례', '시작일': '2026-01-01', '기준일': '2026-12-31', '회계체계': 'K-IFRS / 합성 제한 사례', '감사기준': '학습용·실제 감사 수행 아님', '작성자': '합성작성자', '더미업무': True})
                self.reset_workspace_view()
                self.active_sector = None
                self.sector_selection()
                self.refresh()
                win.destroy()
                self.launch([('계정별증빙연습', resource(entry['file']))])
            self.call(op)
        ttk.Button(win, text='새 독립 업무에서 실행', command=start).pack(pady=12)

    def copy_templates(self):
        folder = filedialog.askdirectory(parent=self.root, title='입력양식과 더미자료를 복사할 폴더')
        if folder:
            self.call(lambda: self.copy_input_bundle(folder))

    def copy_input_bundle(self, folder):
        target = Path(folder) / '통합감사_v1.7_입력자료'
        if target.exists():
            raise AuditError('동일 복사 폴더가 이미 있습니다. 다른 폴더를 선택하세요.')
        for src, dest in [('templates', '입력양식'), ('samples', '더미자료'), ('raw_analytics', '분석원천자료'), ('sector_resources', '업종별자료'), ('문서', '사용안내')]:
            shutil.copytree(resource(src), target / dest)
        self.status.set('입력양식·더미·원천·사용안내 복사 완료: ' + str(target))
        return target

    def open_raw_data(self, open_folder=True):
        self.guard()
        from sector_demo import data_folder
        folder = data_folder(self.ws)
        if open_folder:
            import os
            os.startfile(str(folder))
        self.status.set('최초 더미 입력·원천 열람 / 최신 등록사본은 업무/원본/: ' + str(folder))
        return folder
