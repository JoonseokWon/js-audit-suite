"""Pure shared GUI/actual-harness request defaults. Importing never opens UI or calls AI."""
from copy import deepcopy
from ai_provider import DEFAULT_MODEL

POLICY_VERSION = 'ai-request-policy-1'
_PACKET_OPTIONS = (('max_chars', 24000), ('max_references', 70),
                   ('rows_per_table', 3), ('max_tables', 8), ('cell_chars', 300))


def packet_options():
    """A fresh copy prevents a caller from silently changing another request."""
    return dict(_PACKET_OPTIONS)


def build_packet(ws, pid, catalog=None):
    """Evidence preview, GUI generation and real validation use this same final packet."""
    return ws.ai_packet(pid, catalog, limits=packet_options())


def default_config(endpoint, user_values=None):
    """Defaults only: preserve explicit choices, including a CPU diagnostic override.

    No num_gpu key means Ollama selects hardware automatically. Endpoint/model
    security and all option validation remain in the existing pinned runtime and
    provider; this function does not redirect them or alter saved preferences.
    """
    value = {'provider': 'ollama', 'model': DEFAULT_MODEL, 'endpoint': endpoint,
             'num_ctx': 32768, 'timeout_seconds': 300}
    if user_values is not None:
        value.update(deepcopy(user_values))
    return value


def configuration_summary(config):
    hardware = '명시적 CPU 진단 설정' if config.get('num_gpu') == 0 else '하드웨어 자동 선택'
    return (hardware + ' · ' + format(config.get('num_ctx', 32768), ',') +
            ' 토큰 문맥 · 요청 제한 ' + str(config.get('timeout_seconds', 300)) +
            '초. 기본 근거 범위는 24,000자·70개 참조이며, 명시한 사용자 설정은 유지합니다. '
            '설치·모델은 EXE와 별도로 최초 준비합니다.')
