"""The opt-in integrated proof uses the same pure policy functions as the GUI."""
from copy import deepcopy


def build_request(ws,pid,endpoint,catalog=None):
    from desktop.ai import request_policy
    return (request_policy.build_packet(ws,pid,catalog),
            request_policy.default_config(endpoint))


def describe_request(packet,config,endpoint,cpu_diagnostic=False):
    from desktop.ai import request_policy
    limits=request_policy.packet_options();default=request_policy.default_config(endpoint)
    expected=deepcopy(default)
    if cpu_diagnostic:expected['num_gpu']=0
    limits_match=packet.get('limits')==limits
    requested_match=limits_match and config==expected
    gui_match=limits_match and config==default
    if not requested_match:
        raise AssertionError('The actual request drifted from the shared GUI policy or explicit CPU diagnostic.')
    if not cpu_diagnostic and not gui_match:
        raise AssertionError('The actual default request differs from the GUI default.')
    return {'origin':'desktop.ai.request_policy','version':request_policy.POLICY_VERSION,
        'packet_limits':deepcopy(packet['limits']),'num_ctx':config.get('num_ctx'),
        'hardware_selection':'explicit_cpu_diagnostic' if cpu_diagnostic else 'automatic_default',
        'matches_gui_default':gui_match,'matches_requested_policy':requested_match}


def transport_matches_request(config,options):
    return (options.get('num_ctx')==config.get('num_ctx') and
            (options.get('num_gpu')==config['num_gpu'] if 'num_gpu' in config else 'num_gpu' not in options))
