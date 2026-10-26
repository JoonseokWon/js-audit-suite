"""Company native desktop actions."""
from desktop.shared import *
from desktop.widgets.flow import FlowFrame
from desktop.widgets.tables import tree, fill

class CompanyActions:

    def sector_selection(self):
        self.sector_name.set(next((c['name'] for c in self.sector_options if c['code'] == self.active_sector), '회사를 선택하세요'))
        if self.active_sector is None:
            from desktop.demo.context import has_demo_marker
            if has_demo_marker(self.ws):
                self.sector_name.set(self.ws.engagement['회사명'])
                self.sector_description.set('JS전자 감사 시연 · 가상 제조업 자료의 별도 업무예요. 실제 감사 수행·승인과 모회사 연결결산을 포함하지 않아요.')
            else:self.sector_description.set('수동 업무 · 회사명·범위는 현재 업무 정보를 확인하세요.')

    def new_sector(self):
        chosen = next((c['code'] for c in self.sector_options if c['name'] == self.sector_name.get()), None)
        if chosen is None:
            raise AuditError('먼저 모회사 또는 자회사를 선택하세요.')
        return self.select_sector(chosen, fresh=True)

    def select_sector(self, code, fresh=False):
        if self.busy:
            self.sector_selection()
            raise AuditError('준비·검사 중입니다. 완료 또는 취소 후 선택하세요.')
        if code not in [c['code'] for c in self.sector_options]:
            raise AuditError('지원하지 않는 업종 회사')
        if not self.check_navigation():
            self.sector_selection()
            return False
        from sector_demo import open_company
        self.set_busy(True)
        self.cancel.clear()
        self.status.set('모회사·자회사별 자료·저장 이력을 확인 중…')

        def worker():
            try:
                result = open_company(code, self.sector_home, resource('sector_resources'), fresh=fresh, event=self.cancel, progress=lambda s: self.queue.put(('status', s)))
                self.queue.put(('sector_ready', result))
            except Exception as e:
                self.queue.put(('sector_error', str(e)))
        threading.Thread(target=worker, daemon=False).start()
        return True
