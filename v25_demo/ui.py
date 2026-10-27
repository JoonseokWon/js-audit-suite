"""Read-only hidden navigation. No physical keyboard, IME, DPI or model interaction."""
from pathlib import Path
import tempfile
from unittest.mock import patch
from common import digest


def verify_user_ui(ws, check):
    import runtime
    runtime.configure(); runtime.configure_tk_libraries()
    import tkinter as tk
    from app import App
    from window_capture import destroy_test_window
    before = ws.head; approval_hash = digest(ws.ai_approvals); previous = tk._default_root
    root = tk.Tk(); root.withdraw(); original = tk.Toplevel; tops = []; app = None
    def hidden(*args, **kwargs):
        win = original(*args, **kwargs); win.withdraw(); tops.append(win); return win
    try:
        with tempfile.TemporaryDirectory(prefix='v25-hidden-navigation-') as temp, patch.object(tk, 'Toplevel', side_effect=hidden):
            app = App(root, sector_home=Path(temp)/'not-created-store'); app.open_workspace(ws.root); app.load_procedure('A04')
            check(app.proc_vars['preparer'].get() == '' and app.proc_vars['performed_date'].get() == '',
                  'v25_hidden_UI_does_not_fill_user_preparer_or_performance_date')
            from desktop.audit_links import open_dialog as risk_dialog
            dialog = risk_dialog(app)
            check(dialog.win.state() == 'withdrawn' and not dialog.win.audit_links_state['active'],
                  'v25_risk_navigation_is_hidden_and_does_not_activate_human_assessment')
            dialog.close(force=True)
            from desktop.misstatements import open_dialog as ms_dialog
            dialog = ms_dialog(app)
            check(dialog.win.state() == 'withdrawn', 'v25_misstatement_navigation_stays_hidden')
            dialog.close(force=True)
            check(root.state() == 'withdrawn' and all(w.state() == 'withdrawn' for w in tops if w.winfo_exists()),
                  'v25_all_navigation_windows_stay_hidden_without_physical_UI_control')
        ws.refresh()
        check(ws.head == before and digest(ws.ai_approvals) == approval_hash and not ws.procedures,
              'v25_hidden_navigation_creates_no_procedure_approval_or_history')
    finally:
        if app: app.shutdown_ai()
        for win in reversed(tops):
            if win.winfo_exists(): win.destroy()
        destroy_test_window(root); tk._default_root = previous

