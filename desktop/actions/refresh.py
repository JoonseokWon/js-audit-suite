"""Refresh native desktop actions."""
from desktop.shared import *
from desktop.widgets.flow import FlowFrame
from desktop.widgets.tables import tree, fill

class RefreshActions:

    def refresh(self):
        if not self.ws:
            return
        self.ws.refresh()
        e = self.ws.engagement
        latest = self.ws.latest()
        self.info.set(f"{e['회사명']} / {e['회사코드']} / {e['시작일']} ~ {e['기준일']} / " + ('더미업무 / ' if e.get('더미업무') else '') + str(self.ws.root))
        fill(self.run_tree, [{'모듈': m, '실행상태': '입력 보완 필요' if r['result']['blocking'] else '자동검사 종료·수동절차 필요', '차단': r['result']['blocking'], '검토': r['result']['review'], '실행시각': display_time(r['at']), '자료명': self.ws.sources[r['source_id']]['name']} for m, r in latest.items()])
        self.issue_items = [(r, i) for r in latest.values() for i, _ in enumerate(r['result']['issues'])]
        fill(self.issue_tree, [{'모듈': r['module'], '중요도': r['result']['issues'][i]['severity'], '사유': r['result']['issues'][i]['code'], '내용': r['result']['issues'][i]['message'], '원본행': r['result']['issues'][i]['reference']} for r, i in self.issue_items])
        fill(self.lead_tree, latest.get('원장·리드', {}).get('result', {}).get('tables', {}).get('리드스케줄', []))
        fill(self.cross_tree, self.ws.cross_checks())
        raw = latest.get('원천증빙', {}).get('result')
        if self.active_sector == 'JS':
            scope = '모회사 자체 원장 · 자회사 영업자료·투자주식 평가·연결계산은 포함하지 않습니다.'
        elif raw:
            metrics = raw['metrics']
            scope = ('원천 검사 차단 · ' if raw['blocking'] else '') + 'TB 숫자·현재 실행 연결 요약. 원천 선택 ' + str(metrics.get('선택원천행수', '미확인')) + '행·대상 ' + str(metrics.get('선택대상행수', '미확인')) + '행·배부 ' + str(metrics.get('배부건수', '미확인')) + '건 / 미확인 범위 ' + str(metrics.get('미확인범위수', '미확인')) + '개. 결과 상세 → 원천증빙 → 연결범위를 확인하세요.'
        else:
            scope = '계산 결과와 TB 숫자·현재 실행 연결. 실제 원천 선택 범위와 미확인 항목은 결과 상세에서 확인하세요.'
        self.cross_scope_text.set(scope)
        self.result_modules['values'] = list(latest)
        if self.result_module.get() not in latest:
            self.result_module.set(next(iter(latest), ''))
        self.choose_result_module()
        self.tasks = self.task_list()
        required = self.ws.required_procedures()
        fill(self.proc_tree, [{'ID': t['id'] if not t['id'].startswith('X-') else '예외', '절차': self.ws.procedures.get(t['id'], t)['title'], '현재상태': self.ws.procedure_state(self.ws.procedures[t['id']]) if t['id'] in self.ws.procedures else '미착수', '필수': '필수' if t['id'] in required else '선택'} for t in self.tasks])
        self.evidence_sources = list(self.ws.sources.values())
        self.evidence_list.delete(0, 'end')
        for s in self.evidence_sources:
            self.evidence_list.insert('end', s['name'] + ' / ' + s['id'][:8])
        fill(self.request_tree, list(self.ws.requests.values()))
        self.request_sources = self.evidence_sources
        self.request_evidence.delete(0, 'end')
        for s in self.request_sources:
            self.request_evidence.insert('end', s['name'] + ' / ' + s['id'][:8])
        if self.current_request in self.ws.requests:
            for i, s in enumerate(self.request_sources):
                if s['id'] in self.ws.requests[self.current_request]['source_ids']:
                    self.request_evidence.selection_set(i)
        fill(self.source_tree, [{'자료명': s['name'], '유형': s['role'], '원본파일': s['original'], '사본해시': s['sha256'], '등록시각': s['registered_at']} for s in self.evidence_sources])
        self.note_items = list(self.ws.notes.values())
        fill(self.note_tree, [{'제목': n['title'], '내용': n['body'], '작성자': n['actor'], '해결': '해결' if n['resolved'] else '미해결', '시각': n['at']} for n in self.note_items])
        self.risk_items = self.ws.risk_register()
        fill(self.risk_tree, self.risk_items)
        self.risk_detail.delete('1.0', 'end')
        fill(self.history_tree, self.history_rows())
        self.set_history_text('')
        if self.current_pid and any((t['id'] == self.current_pid for t in self.tasks)):
            self.load_procedure(self.current_pid)
        self.refresh_workflow()
        refresh_dashboard = getattr(self, 'refresh_dashboard', None)
        if callable(refresh_dashboard):
            refresh_dashboard()
