"""Static, lazy self-test imports keep frozen builds and old CLI contracts intact."""
from pathlib import Path


def dispatch(arguments):
    def report():return Path(arguments[arguments.index('--report')+1])
    if '--self-test-v20' in arguments:
        from tools.verify_bento_v20 import self_test
        return self_test(report())
    if '--self-test-ime' in arguments:
        from verify_ime_patch import self_test
        return self_test(report(),Path(arguments[arguments.index('--workspace')+1]))
    if '--self-test-ai-real' in arguments:
        from verify_ai_actual import self_test
        return self_test(report(),Path(arguments[arguments.index('--ai-runtime')+1]))
    if '--self-test-v19' in arguments:
        from verify_v19 import self_test
        return self_test(report())
    if '--self-test-v18' in arguments:
        from verify_v18 import self_test
        return self_test(report())
    if '--self-test-v171' in arguments:
        from verify_v171 import self_test
        return self_test(report())
    if '--self-test-v17' in arguments:
        from verify_v17 import self_test
        return self_test(report())
    if '--self-test-v16' in arguments:
        from verify_v16 import self_test
        return self_test(report())
    if '--self-test-v15' in arguments:
        from verify_v15 import self_test
        return self_test(report())
    if '--self-test-v14' in arguments:
        from verify_v14 import self_test
        return self_test(report())
    if '--self-test' in arguments:
        from verify import self_test
        return self_test(report())
    return None
