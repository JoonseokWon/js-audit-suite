"""Desktop design tokens. Every surface is painted at native DPI, without images."""
from tkinter import ttk, font

COLORS = {
    'page': '#F4F6FA', 'surface': '#FFFFFF', 'ink': '#191F28',
    'secondary': '#6B7684', 'muted': '#8B95A1', 'border': '#E5E8EB',
    'blue': '#246BEB', 'blue_hover': '#1557CE', 'blue_soft': '#EAF2FF',
    'green': '#167D52', 'green_soft': '#EAF8F0',
    'amber': '#A45B0A', 'amber_soft': '#FFF4E0',
    'red': '#C83B3B', 'red_soft': '#FFF0F0',
}
FONTS = {'AuditTitle': (24, 'bold'), 'AuditSection': (15, 'bold'),
         'AuditMetric': (27, 'bold'), 'AuditBrand': (17, 'bold')}


def apply_theme(root, display):
    """Apply semantic styles; font points and layout pixels have separate roles."""
    style = ttk.Style(root)
    if style.theme_use() != 'clam':
        style.theme_use('clam')
    owners = getattr(root, '_audit_design_fonts', {})
    for name, (size, weight) in FONTS.items():
        if name not in owners or name not in font.names(root):
            owners[name] = (font.nametofont(name, root=root) if name in font.names(root)
                            else font.Font(root=root, name=name))
        current = owners[name]
        current.configure(family=display.family, size=size, weight=weight)
    root._audit_design_fonts = owners
    c, px = COLORS, display.px
    root.configure(background=c['page'])
    style.configure('.', background=c['surface'], foreground=c['ink'],
                    font=display.font, bordercolor=c['border'],
                    lightcolor=c['border'], darkcolor=c['border'], focuscolor=c['blue'])
    for name, color in (('TFrame','surface'),('Card.TFrame','surface'),
                        ('Page.TFrame','page'),('Sidebar.TFrame','surface')):
        style.configure(name, background=c[color])
    style.configure('TLabel', background=c['surface'], foreground=c['ink'])
    style.configure('Page.TLabel', background=c['page'])
    style.configure('Muted.TLabel', foreground=c['secondary'])
    style.configure('PageMuted.TLabel', background=c['page'], foreground=c['secondary'])
    style.configure('Title.TLabel', font='AuditTitle')
    style.configure('Section.TLabel', font='AuditSection')
    style.configure('Metric.TLabel', font='AuditMetric')
    style.configure('Brand.TLabel', font='AuditBrand')
    style.configure('TButton', padding=(px(13), px(9)), background=c['surface'],
                    foreground=c['ink'], borderwidth=1, relief='flat')
    style.map('TButton', background=[('disabled', c['page']), ('pressed', '#DDE5EF'),
                                   ('active', '#F0F4F9')],
              foreground=[('disabled', c['muted'])])
    for name, bg, fg, hover in (
        ('Primary.TButton', c['blue'], '#FFFFFF', c['blue_hover']),
        ('Secondary.TButton', '#F2F4F6', c['ink'], '#E5E8EB'),
        ('Soft.TButton', c['blue_soft'], c['blue'], '#DCEAFF'),
        ('Quiet.TButton', c['surface'], c['secondary'], '#F1F4F8'),
    ):
        style.configure(name, background=bg, foreground=fg, borderwidth=0)
        style.map(name, background=[('disabled', c['page']), ('active', hover)],
                  foreground=[('disabled', c['muted']), ('active', fg)])
    style.configure('TEntry', fieldbackground=c['surface'], padding=(px(9),px(8)),
                    borderwidth=1, insertcolor=c['ink'])
    style.configure('TCombobox', fieldbackground=c['surface'], padding=(px(8),px(7)))
    style.map('TCombobox', fieldbackground=[('readonly', c['surface'])],
              selectbackground=[('readonly', c['surface'])],
              selectforeground=[('readonly', c['ink'])])
    style.configure('Treeview', background=c['surface'], fieldbackground=c['surface'],
                    foreground=c['ink'], borderwidth=0, rowheight=display.metrics['row_height'])
    style.map('Treeview', background=[('selected', c['blue_soft'])],
              foreground=[('selected', c['blue'])])
    style.configure('Treeview.Heading', background='#F7F9FC', foreground='#4E5968',
                    relief='flat', padding=(px(10),px(9)), borderwidth=0)
    style.map('Treeview.Heading', background=[('active', '#EDF1F6')])
    style.configure('TNotebook', background=c['page'], borderwidth=0, tabmargins=0)
    style.configure('TNotebook.Tab', background='#EDF1F6', padding=(px(13),px(9)))
    style.map('TNotebook.Tab', background=[('selected',c['surface'])],
              foreground=[('selected',c['blue'])])
    style.layout('Bento.TNotebook', [('Notebook.client', {'sticky':'nswe'})])
    style.layout('Bento.TNotebook.Tab', [])
    style.configure('Vertical.TScrollbar', background='#CFD6DF', troughcolor=c['page'],
                    borderwidth=0, arrowsize=px(13))
    style.configure('Horizontal.TScrollbar', background='#CFD6DF', troughcolor=c['page'],
                    borderwidth=0, arrowsize=px(13))
    return style
