"""UI-03 deterministic batch outcomes; no model, native UI or real customer data."""
import queue,threading,unittest
from pathlib import Path
from unittest.mock import patch
from common import cancelled
from desktop.actions.execution_status import run_batch,batch_message
from desktop.actions.execution import ExecutionActions


def run_record(blocking=0,review=0,cancelled=False):
    return {'result':{'blocking':blocking,'review':review},'cancelled':cancelled}


class BatchStatusTests(unittest.TestCase):
    def run_case(self,execute,amount=3,event=None):
        event=event or threading.Event();messages=[]
        class WS:pass
        ws=WS();ws.execute=execute
        state=run_batch(ws,[('SYNTHETIC',Path('SYNTHETIC_ONLY.xlsx'))]*amount,event,
                        lambda kind,data:messages.append((kind,data)))
        self.assertEqual(messages[-1],('batch_done',state));return state

    def test_cancel_before_first_execution_has_zero_completed(self):
        event=threading.Event();event.set()
        with patch.object(self,'run_case',wraps=self.run_case):
            state=self.run_case(lambda *args:self.fail('must not execute'),event=event)
        self.assertEqual((state['started'],state['completed'],state['unstarted']),(0,0,3))
        self.assertIn('실행 전 취소',batch_message(state));self.assertNotIn('검사 완료',batch_message(state))

    def test_partial_cancel_retains_one_completed_and_two_unstarted(self):
        event=threading.Event()
        def execute(*args):event.set();return run_record()
        state=self.run_case(execute,event=event)
        self.assertEqual((state['completed'],state['saved_runs'],state['unstarted']),(1,1,2))
        self.assertIn('일부 검사 후 취소',batch_message(state))

    def test_cancellation_exception_and_saved_cancelled_run_are_interrupted_not_completed(self):
        for saved in (False,True):
            event=threading.Event()
            def execute(*args):
                event.set()
                if saved:return run_record(cancelled=True)
                cancelled(event)
            state=self.run_case(execute,event=event)
            self.assertEqual((state['completed'],state['failed'],state['interrupted']),(0,0,1))

    def test_failure_after_a_success_keeps_failed_and_unstarted_separate(self):
        count=0
        def execute(*args):
            nonlocal count
            count+=1
            if count==2:raise ValueError('SYNTHETIC ONLY bad input')
            return run_record()
        state=self.run_case(execute)
        self.assertEqual((state['completed'],state['failed'],state['unstarted']),(1,1,1))
        self.assertIn('검사 실패',batch_message(state))

    def test_cancel_does_not_hide_an_unrelated_failure(self):
        event=threading.Event()
        def execute(*args):event.set();raise ValueError('SYNTHETIC failure')
        state=self.run_case(execute,event=event)
        self.assertTrue(state['cancelled']);self.assertEqual(state['failed'],1)

    def test_cancel_after_the_last_success_keeps_completed_count_without_claiming_partial_execution(self):
        event=threading.Event()
        def execute(*args):event.set();return run_record()
        state=self.run_case(execute,amount=1,event=event)
        self.assertEqual(state['completed'],1);self.assertEqual(state['unstarted'],0)
        self.assertIn('종료 후 취소 요청',batch_message(state));self.assertNotIn('일부 검사',batch_message(state))

    def test_finished_with_blocking_issues_is_not_clean_or_human_complete(self):
        state=self.run_case(lambda *args:run_record(2,1),amount=2)
        self.assertEqual((state['completed'],state['blocking_runs'],state['blocking_issues'],state['review_issues']),(2,2,4,2))
        self.assertIn('차단 항목 있음',batch_message(state));self.assertIn('별도로',batch_message(state))

    def test_empty_selection_is_not_reported_as_completed_work(self):
        state=self.run_case(lambda *args:self.fail('must not execute'),amount=0)
        self.assertIn('실행할 검사 없음',batch_message(state))

    def test_ui_launch_and_poll_do_not_turn_pre_execution_cancel_into_done(self):
        class Value:
            def set(self,value):self.value=value
        class Root:
            def after(self,*args):return 'SYNTHETIC_TIMER'
        class Host:
            closing=False
            def __init__(self):self.queue=queue.Queue();self.cancel=threading.Event();self.ws=object();self.status=Value();self.root=Root()
            def guard(self):pass
            def set_busy(self,value):self.busy=value
            def call(self,fn):fn()
            def refresh(self):pass
        host=Host()
        host.poll=lambda:None
        class Thread:
            def __init__(self,target,**kwargs):self.target=target
            def start(self):host.cancel.set();self.target()
        with patch('desktop.actions.execution.threading.Thread',Thread):
            ExecutionActions.launch(host,[('SYNTHETIC',Path('SYNTHETIC_ONLY.xlsx'))])
        ExecutionActions.poll(host)
        self.assertFalse(host.busy);self.assertEqual(host.last_batch_result['completed'],0)
        self.assertIn('실행 전 취소',host.status.value)
