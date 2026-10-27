"""Actual-harness policy adapters, tested without inference or physical UI."""
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
from desktop.ai import request_policy
from ai_quality.gui_policy_v25 import build_request,describe_request,transport_matches_request

ENDPOINT='http://127.0.0.1:11437'


class ActualGUIPolicyAdapterTests(unittest.TestCase):
    def test_actual_adapter_calls_the_GUI_packet_and_default_config_functions(self):
        packet={'limits':request_policy.packet_options()};ws=SimpleNamespace(ai_packet=Mock(return_value=packet))
        catalog={'fixture':'synthetic-only'}
        with patch.object(request_policy,'build_packet',wraps=request_policy.build_packet) as builder,patch.object(
                request_policy,'default_config',wraps=request_policy.default_config) as defaults:
            returned,config=build_request(ws,'A04',ENDPOINT,catalog)
        builder.assert_called_once_with(ws,'A04',catalog);defaults.assert_called_once_with(ENDPOINT)
        ws.ai_packet.assert_called_once_with('A04',catalog,limits=request_policy.packet_options())
        self.assertIs(returned,packet);self.assertEqual(config['num_ctx'],32768)
        self.assertNotIn('num_gpu',config)

    def test_effective_default_request_is_compared_with_GUI_not_copied_constants(self):
        packet={'limits':request_policy.packet_options()};config=request_policy.default_config(ENDPOINT)
        before=deepcopy((packet,config));metadata=describe_request(packet,config,ENDPOINT)
        self.assertEqual(metadata['version'],request_policy.POLICY_VERSION)
        self.assertEqual(metadata['origin'],'desktop.ai.request_policy')
        self.assertTrue(metadata['matches_gui_default']);self.assertTrue(metadata['matches_requested_policy'])
        self.assertEqual(metadata['packet_limits'],packet['limits'])
        self.assertEqual(metadata['hardware_selection'],'automatic_default')
        self.assertEqual((packet,config),before)

    def test_packet_context_or_unrequested_CPU_drift_is_rejected_without_transport(self):
        for drift in ('packet','context','cpu','model'):
            packet={'limits':request_policy.packet_options()};config=request_policy.default_config(ENDPOINT)
            if drift=='packet':packet['limits']['max_chars']=12000
            elif drift=='context':config['num_ctx']=16384
            elif drift=='cpu':config['num_gpu']=0
            else:config['model']='other-local-model'
            with self.subTest(drift=drift),patch('ai_provider._post_json') as transport:
                with self.assertRaisesRegex(AssertionError,'drifted'):describe_request(packet,config,ENDPOINT)
                transport.assert_not_called()

    def test_explicit_CPU_diagnostic_is_reported_separately_from_GUI_default(self):
        packet={'limits':request_policy.packet_options()};config=request_policy.default_config(ENDPOINT)
        config['num_gpu']=0;metadata=describe_request(packet,config,ENDPOINT,cpu_diagnostic=True)
        self.assertFalse(metadata['matches_gui_default']);self.assertTrue(metadata['matches_requested_policy'])
        self.assertEqual(metadata['hardware_selection'],'explicit_cpu_diagnostic')
        self.assertNotIn('endpoint',metadata);self.assertNotIn('config',metadata)

    def test_captured_transport_context_and_hardware_are_checked_independently(self):
        config=request_policy.default_config(ENDPOINT)
        self.assertTrue(transport_matches_request(config,{'num_ctx':32768,'temperature':0}))
        self.assertFalse(transport_matches_request(config,{'num_ctx':16384}))
        self.assertFalse(transport_matches_request(config,{'num_ctx':32768,'num_gpu':0}))
        config['num_gpu']=0
        self.assertFalse(transport_matches_request(config,{'num_ctx':32768}))
        self.assertTrue(transport_matches_request(config,{'num_ctx':32768,'num_gpu':0}))


if __name__=='__main__':unittest.main()
