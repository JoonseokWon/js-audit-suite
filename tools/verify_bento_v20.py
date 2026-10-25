"""Same symbolic lifecycle for source and EXE; all workspaces are isolated fixtures."""
from pathlib import Path
import json
import sys
import traceback

def self_test(report_path):
    from verify_v19 import self_test as previous
    report_path=Path(report_path).resolve()
    # Retain all 36 preceding engine, native Unicode and HITL assertions.
    code=previous(report_path)
    if code:return code
    record=json.loads(report_path.read_text(encoding='utf-8'))
    root=None;app=None;cashflow=None;cashflow_root=None
    try:
        import tkinter as tk
        from app import App
        from adapters import MODULES
        root=tk.Tk();root.withdraw()
        app=App(root,sector_home=report_path.parent/'bento-isolated-sectors')
        def check(value,name):
            if not value:raise AssertionError(name)
            record['checks'].append(name)
        check(root.state()=='withdrawn','bento_test_root_stays_hidden')
        from desktop_display import DPI_POLICY,enable_dpi_awareness,display_metrics
        awareness=enable_dpi_awareness()
        check(DPI_POLICY=='per_monitor_v2' and awareness['enabled'],
              'process_DPI_policy_is_explicit_and_enabled')
        check(all(display_metrics(dpi,100)['factor']==dpi/96 and
                  display_metrics(dpi,100)['row_height']>=round(30*dpi/96)
                  for dpi in (96,120,144,192)),
              'logical_DPI_metrics_cover_100_125_150_200_percent')
        check('업무 요약' in app.tabs and len(app.tabs)==10,'bento_home_and_all_nine_workflows_exist')
        check(app.nb.select()==str(app.tabs['업무 요약']),'bento_starts_at_home')
        check(set(app.sidebar.buttons)==set(app.tabs),'sidebar_reaches_every_workflow')
        check(len(app.dashboard.grid.items)>=4,'dashboard_has_multiple_bento_cards')
        before=(app.ws,app.sector_home.exists())
        for module in MODULES:
            check(app.route_module(module) is True and app.module.get()==module
                  and app.nb.select()==str(app.tabs['자료·검사']),'module_route_'+str(MODULES.index(module)))
        check((app.ws,app.sector_home.exists())==before,'module_routes_never_create_data_or_workspaces')
        check(app.navigate('업무 요약') is True and app.sidebar.active=='업무 요약','sidebar_returns_home')
        check(len(app.tab_scrolls)==9,'every_non_editor_tab_keeps_its_scroll_container')
        check(not app.ws,'dashboard_does_not_invent_engagement')
        app.open_workspace(record['workflow_workspace']);head=app.ws.head;basis=app.ws.basis()
        app.refresh_dashboard()
        check(app.ws.head==head and app.ws.basis()==basis,'dashboard_refresh_is_read_only')
        for tab in app.tabs:
            check(app.navigate(tab) is True,'navigate_'+str(list(app.tabs).index(tab)))
        check(app.ws.head==head,'navigation_never_records_performance_or_approval')
        from desktop.tools.cashflow.entry import CashFlowApp
        cashflow_root=tk.Tk();cashflow_root.withdraw();cashflow=CashFlowApp(cashflow_root)
        check(cashflow_root.state()=='withdrawn','cashflow_test_root_stays_hidden')
        check(cashflow.source_path is None and cashflow.example is None and cashflow.result is None
              and not cashflow.running,'cashflow_starts_without_loading_or_calculating_data')
        check(not hasattr(cashflow,'ws') and app.ws.head==head,'cashflow_does_not_link_or_mutate_engagement')
        check(not cashflow.diff_tree.get_children() and not cashflow.line_tree.get_children(),
              'cashflow_default_result_is_empty')
        record.update(ok=True,bento_navigation_verified=True,dpi_policy_verified=True,
                      current_actual_model_calls=0,current_actual_key_test=False,
                      frozen=bool(getattr(sys,'frozen',False)),
                      dpi_awareness=awareness,dpi_policy=DPI_POLICY,
                      scope='Existing synthetic lifecycle plus Bento navigation and read-only dashboard; no physical IME/model test.')
    except Exception as exc:
        record.update(ok=False,error=str(exc),traceback=traceback.format_exc())
    finally:
        if cashflow is not None:cashflow.close()
        elif cashflow_root is not None:
            from window_capture import destroy_test_window
            destroy_test_window(cashflow_root)
        if app is not None:app.shutdown_ai()
        if root is not None:
            from window_capture import destroy_test_window
            destroy_test_window(root)
    report_path.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(record,ensure_ascii=False));return 0 if record['ok'] else 1
