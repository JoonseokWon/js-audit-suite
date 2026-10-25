"""Compatibility facade and entry point for the modular native desktop."""
from desktop.shared import *
from desktop.widgets.flow import FlowFrame
from desktop.widgets.tables import tree, fill
from desktop.application import BaseAuditApp
from desktop.shell import DesktopShellMixin


class App(DesktopShellMixin, BaseAuditApp):
    """Small composition root; screens and actions live in desktop/ modules."""


def main():
    from desktop.entry_tests import dispatch
    result=dispatch(sys.argv)
    if result is not None:return result
    if '--tool' in sys.argv:
        tool=sys.argv[sys.argv.index('--tool')+1]
        if tool!='cashflow':raise AuditError('지원하지 않는 별도 도구예요.')
        from desktop.tools.cashflow.entry import main as cashflow_main
        return cashflow_main()
    root=tk.Tk()
    app=App(root)
    if '--workspace' in sys.argv:
        app.call(lambda:app.open_workspace(sys.argv[sys.argv.index('--workspace')+1]))
    if '--module' in sys.argv:
        app.call(lambda:app.route_module(sys.argv[sys.argv.index('--module')+1]))
    root.mainloop()
    return 0


if __name__=='__main__':
    sys.exit(main())
