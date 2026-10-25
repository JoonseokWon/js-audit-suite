"""Process-local DPI policy; called before Tk creates its first HWND."""
import ctypes


def _awareness_mode(user32):
    try:
        get = user32.GetThreadDpiAwarenessContext
        get.restype, get.argtypes = ctypes.c_void_p, []
        context = get()
        equal = getattr(user32, 'AreDpiAwarenessContextsEqual', None)
        if equal is not None:
            equal.restype = ctypes.c_bool
            equal.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            if equal(context, ctypes.c_void_p(-4)):
                return 'per_monitor_v2'
        mode = user32.GetAwarenessFromDpiAwarenessContext
        mode.restype, mode.argtypes = ctypes.c_int, [ctypes.c_void_p]
        return {0:'unaware', 1:'system', 2:'per_monitor'}.get(int(mode(context)), 'unknown')
    except (AttributeError, OSError, ValueError):
        return 'unknown'


def _enable_windows(user32, shcore=None):
    """Prefer PMv2; preserve host/manifest policy; support older Windows safely."""
    aware_modes = ('system', 'per_monitor', 'per_monitor_v2')
    try:
        api = user32.SetProcessDpiAwarenessContext
        api.argtypes, api.restype = [ctypes.c_void_p], ctypes.c_bool
        for value, name in ((-4, 'per_monitor_v2'), (-3, 'per_monitor'), (-2, 'system')):
            if api(ctypes.c_void_p(value)):
                return {'mode':name, 'status':'set', 'enabled':True,
                        'method':'SetProcessDpiAwarenessContext'}
            if ctypes.get_last_error() == 5:
                mode = _awareness_mode(user32)
                return {'mode':mode, 'status':'already_configured',
                        'enabled':mode in aware_modes, 'method':'manifest_or_host'}
    except (AttributeError, OSError):
        pass
    if shcore is not None:
        try:
            api = shcore.SetProcessDpiAwareness
            api.argtypes, api.restype = [ctypes.c_int], ctypes.c_long
            result = int(api(2))
            if result == 0:
                return {'mode':'per_monitor', 'status':'set', 'enabled':True,
                        'method':'SetProcessDpiAwareness'}
            if result in (-2147024891, 2147942405):
                mode = _awareness_mode(user32)
                return {'mode':mode, 'status':'already_configured',
                        'enabled':mode in aware_modes, 'method':'manifest_or_host'}
        except (AttributeError, OSError):
            pass
    try:
        api = user32.SetProcessDPIAware
        api.argtypes, api.restype = [], ctypes.c_bool
        if api():
            return {'mode':'system', 'status':'set', 'enabled':True,
                    'method':'SetProcessDPIAware'}
    except (AttributeError, OSError):
        pass
    mode = _awareness_mode(user32)
    return {'mode':mode, 'status':'not_changed', 'enabled':mode in aware_modes,
            'method':'unavailable_or_host'}
