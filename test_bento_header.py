"""Real Tk geometry for the header in an isolated, always-withdrawn host.

DPI is an explicit metric input. These tests never change OS display settings,
open an engagement, run a command, or claim physical mixed-monitor coverage.
"""
import sys
import threading
import unittest
from types import SimpleNamespace


class HeaderFixture:
    def __init__(self, logical_width=1000, dpi=96, zoom=100):
        import runtime
        runtime.configure(); runtime.configure_tk_libraries()
        import tkinter as tk
        from tkinter import ttk
        from desktop_display import DisplayManager, enable_dpi_awareness
        from desktop.design import apply_theme
        from desktop.chrome.header import build_header
        enable_dpi_awareness()
        self.tk, self.ttk = tk, ttk
        self.root = tk.Tk(); self.root.withdraw()
        self.display = DisplayManager(self.root, dpi=dpi, scale=zoom)
        self.root.audit_display = self.display
        apply_theme(self.root, self.display)
        self.shell = ttk.Frame(self.root)
        # An explicitly sized child gets real geometry while its root stays
        # withdrawn; packing directly into a withdrawn root can remain 1x1.
        self.shell.place(x=0, y=0)
        self.shell.columnconfigure(1, weight=1)
        self.shell.rowconfigure(0, weight=1)
        self.side = ttk.Frame(self.shell, width=self.display.px(224))
        self.side.grid(row=0, column=0, sticky='ns')
        self.side.grid_propagate(False)
        self.content = ttk.Frame(self.shell)
        self.content.grid(row=0, column=1, sticky='nsew')
        noop = lambda *args, **kw: None
        self.host = SimpleNamespace(display=self.display, cancel=threading.Event(),
            sector_options=[{'name': 'JS전자', 'code': 'electronics'}], ws=None,
            call=lambda fn: fn(), select_sector=noop, open_workpaper_draft=noop,
            open_workflow_view=noop, export_dialog=noop, set_ui_zoom=noop,
            new_dialog=noop, open_dialog=noop, new_sector=noop,
            open_raw_data=noop, copy_templates=noop, case_dialog=noop,
            open_ai_settings=noop, navigate=noop)
        self.header = build_header(self.host, self.content)
        self.set_viewport(logical_width)

    def close(self):
        from window_capture import destroy_test_window
        self.display.close(); destroy_test_window(self.root)

    def settle(self):
        import _tkinter
        # Bound event processing: an after_idle geometry oscillation fails
        # instead of hanging update_idletasks() and hiding the regression.
        count = 0
        while self.root.tk.dooneevent(_tkinter.ALL_EVENTS | _tkinter.DONT_WAIT):
            count += 1
            if count > 5000:
                raise AssertionError('Header geometry did not reach idle')
        return count

    def set_viewport(self, logical_width):
        self.logical_width = logical_width
        physical = round(logical_width * self.display.dpi / 96)
        self.root.minsize(1, 1)
        self.root.geometry(f'{physical}x1400+30000+30000')
        self.shell.place(width=physical, height=1400)
        self.settle()

    def change_metrics(self, dpi, zoom):
        from desktop.design import apply_theme
        self.display.dpi = dpi
        self.display.apply(zoom)
        apply_theme(self.root, self.display)
        self.side.configure(width=self.display.px(224))
        self.host.company_bar.schedule(); self.host.toolbar.schedule()
        self.set_viewport(self.logical_width)

    @staticmethod
    def rect(widget, parent):
        x, y, current = 0, 0, widget
        while current is not parent:
            x += current.winfo_x(); y += current.winfo_y()
            current = current.master
        return [x, y, widget.winfo_width(), widget.winfo_height()]

    def report(self):
        h = self.host
        return {'logical_width': self.logical_width, 'metric_dpi': self.display.dpi,
                'text_zoom': self.display.percent, 'root_state': self.root.state(),
                'physical_width': self.root.winfo_width(),
                'content_width': self.content.winfo_width(),
                'header_height': self.header.winfo_height(),
                'description': self.rect(h.company_description_label, self.header),
                'description_wrap': int(h.company_description_label.cget('wraplength')),
                'flows': [{'width': flow.winfo_width(), 'height': flow.winfo_height(),
                    'items': [{'text': str(w.cget('text')) if 'text' in w.keys() else '',
                               'rect': self.rect(w, flow)}
                              for w in flow.items if w.winfo_manager() == 'place']}
                          for flow in (h.company_bar, h.toolbar)]}


@unittest.skipUnless(sys.platform == 'win32', 'Windows native Tk geometry')
class BentoHeaderGeometryTests(unittest.TestCase):
    def assert_layout(self, fixture):
        self.assertEqual(fixture.root.state(), 'withdrawn')
        self.assertIsNone(fixture.host.ws)
        for flow, count in ((fixture.host.company_bar, 3), (fixture.host.toolbar, 4)):
            self.assertEqual(len(flow.items), count)
            self.assertTrue(all(w.winfo_manager() == 'place' for w in flow.items))
        report = fixture.report()
        for flow in report['flows']:
            boxes = [item['rect'] for item in flow['items']]
            for x, y, width, height in boxes:
                self.assertGreater(width, 1); self.assertGreater(height, 1)
                self.assertGreaterEqual(x, 0); self.assertGreaterEqual(y, 0)
                self.assertLessEqual(x + width, flow['width'] + 1)
                self.assertLessEqual(y + height, flow['height'] + 1)
            for index, a in enumerate(boxes):
                for b in boxes[index + 1:]:
                    overlap = (min(a[0]+a[2], b[0]+b[2]) > max(a[0], b[0])
                               and min(a[1]+a[3], b[1]+b[3]) > max(a[1], b[1]))
                    self.assertFalse(overlap, (a, b, report))
                    if min(a[1]+a[3], b[1]+b[3]) > max(a[1], b[1]):
                        self.assertLessEqual(abs(a[1]+a[3]/2-(b[1]+b[3]/2)), 1)
        for compound in (fixture.host.sector_box.master, fixture.host.zoom_box.master):
            centers = []
            for child in compound.winfo_children():
                x, y, width, height = fixture.rect(child, compound)
                self.assertGreaterEqual(x, 0)
                self.assertLessEqual(x+width, compound.winfo_width()+1)
                self.assertLessEqual(y+height, compound.winfo_height()+1)
                centers.append(y+height/2)
            self.assertLessEqual(max(centers)-min(centers), 1)
        label = fixture.host.company_description_label
        self.assertEqual(label.winfo_manager(), 'pack')
        self.assertGreater(len(fixture.host.sector_description.get()), 0)
        self.assertEqual(int(label.cget('wraplength')), label.winfo_width())
        self.assertGreaterEqual(label.winfo_height(), label.winfo_reqheight())
        for flow, last in ((fixture.host.company_bar, fixture.host.sector_cancel),
                           (fixture.host.toolbar, fixture.host.zoom_box.master)):
            x, _, width, _ = fixture.rect(last, flow)
            self.assertLessEqual(abs(flow.winfo_width() - x - width - fixture.display.px(1)), 1)
        before = fixture.report()
        for _ in range(3):
            fixture.settle()
            self.assertEqual(before, fixture.report(), 'Header height/layout oscillates')

    def test_header_fits_shell_viewports_dpi_and_text_zoom(self):
        for width in (800, 1000, 1280):
            for dpi in (96, 144):
                for zoom in (100, 150):
                    with self.subTest(width=width, dpi=dpi, zoom=zoom):
                        fixture = HeaderFixture(width, dpi, zoom)
                        try: self.assert_layout(fixture)
                        finally: fixture.close()

    def test_long_description_stays_visible_and_wraps_after_resize(self):
        fixture = HeaderFixture(1000, 144, 100)
        try:
            original = fixture.host.sector_description.get()
            fixture.host.sector_description.set(original * 12)
            fixture.settle(); large_height = fixture.host.company_description_label.winfo_height()
            fixture.set_viewport(800); self.assert_layout(fixture)
            self.assertGreaterEqual(fixture.host.company_description_label.winfo_height(), large_height)
            fixture.host.sector_description.set(original)
            fixture.settle(); self.assert_layout(fixture)
        finally: fixture.close()

    def test_metrics_and_viewport_changes_reach_a_stable_layout(self):
        fixture = HeaderFixture()
        try:
            for dpi, zoom, width in ((144, 150, 800), (96, 100, 1280), (144, 100, 1000), (96, 150, 800)):
                fixture.logical_width = width
                fixture.change_metrics(dpi, zoom); self.assert_layout(fixture)
        finally: fixture.close()

    def test_flow_textvariable_growth_and_shrink_relayout_without_user_input(self):
        from desktop.widgets.flow import FlowFrame
        fixture = HeaderFixture(800, 96, 100)
        try:
            flow = FlowFrame(fixture.content); flow.pack(fill='x')
            value = fixture.tk.StringVar(value='자료')
            button = flow.add(fixture.ttk.Button(flow, textvariable=value))
            other = flow.add(fixture.ttk.Button(flow, text='조서'))
            fixture.settle(); original_width = button.winfo_width()
            value.set('연결된 원본자료와 대사 결과 전체 확인 ' * 4)
            fixture.settle()
            self.assertGreater(button.winfo_width(), original_width)
            self.assertLessEqual(button.winfo_x()+button.winfo_width(), flow.winfo_width())
            self.assertGreater(other.winfo_y(), button.winfo_y())
            value.set('자료'); fixture.settle()
            self.assertEqual(button.winfo_width(), original_width)
            self.assertEqual(button.winfo_y(), other.winfo_y())
            flow.destroy(); value.set('정리 후 변경')
            fixture.settle()
        finally: fixture.close()


if __name__ == '__main__':
    unittest.main()
