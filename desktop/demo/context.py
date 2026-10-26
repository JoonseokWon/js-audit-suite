"""Treat the example's creator metadata separately from a human author."""
def has_demo_marker(ws):
    # A damaged marker must not make the example creator a human preparer.
    return bool(ws and (ws.root/'시연_자료목록.json').exists())


def default_preparer(ws):
    return '' if has_demo_marker(ws) else ws.engagement.get('작성자','') if ws else ''
