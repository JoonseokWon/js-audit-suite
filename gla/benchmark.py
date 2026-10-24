"""Measure the declared 10,000-GL-row limit, including a large repeat group.

Synthetic only: TB and controls are recomputed by this same generator. They do
not constitute independent external audit evidence. Input XLSX stays under
gla/verification/benchmark_inputs and must be excluded from distribution.
"""
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
import gc
import json
import os
import platform
import re
import struct
import sys
import time
import traceback

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
import runtime
runtime.configure()
from common import atomic,digest,dumps,sha
from tools.analytics_fixtures import load_base,write_input
import ledger
import gla

CONTEXT={'회사코드':'SYNTH01','시작일':'2026-01-01','기준일':'2026-12-31'}
OUTPUT=ROOT/'gla/verification'
INPUTS=OUTPUT/'benchmark_inputs'


def memory():
    """Optional OS process counters; measurements are not a memory guarantee."""
    if os.name!='nt':return {'available':False,'reason':'Windows process-counter implementation only'}
    try:
        import ctypes
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD),
                *[(n,ctypes.c_size_t) for n in ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage',
                    'QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage')]]
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        psapi=ctypes.WinDLL('psapi',use_last_error=True)
        kernel.GetCurrentProcess.restype=wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
        psapi.GetProcessMemoryInfo.restype=wintypes.BOOL
        c=Counters();c.cb=ctypes.sizeof(c)
        if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(),ctypes.byref(c),c.cb):raise OSError('GetProcessMemoryInfo failed')
        return {'available':True,'working_set_mib':round(c.WorkingSetSize/1024**2,3),
                'process_lifetime_peak_working_set_mib':round(c.PeakWorkingSetSize/1024**2,3)}
    except (ImportError,OSError,AttributeError) as exc:return {'available':False,'reason':str(exc)}


def fingerprint():
    files=['gla/__init__.py','analytics_support.py','common.py','ledger.py','tools/analytics_fixtures.py',
           'samples/통합/통합_v1.3_원장_리드.xlsx']
    return {p:sha(ROOT/p) for p in files}


def make_base():
    base=load_base()
    if len(base['총계정원장'])!=82:raise AssertionError('Pinned base must contain 82 GL rows')
    template=[deepcopy(r) for r in base['총계정원장'] if r['전표ID']=='J-I']
    if len(template)!=2 or sum(r['차변'] for r in template)!=36400 or sum(r['대변'] for r in template)!=36400:
        raise AssertionError('Pinned J-I must be balanced 2-row / 36,400 won')
    clones=(10000-len(base['총계정원장']))//2
    for i in range(clones):
        for original in template:
            row=deepcopy(original)
            row.update(전표ID='J-BENCH-'+str(i+1).zfill(5),전기일='2026-12-30',
                       적요='SYNTHETIC ONLY / 10,000행 반복 검증',작성자='합성벤치작성자')
            row['_row']=len(base['총계정원장'])+2
            base['총계정원장'].append(row)
    recalculate_controls(base)
    return base,clones


def recalculate_controls(base):
    totals=defaultdict(lambda:[0,0,0])
    for row in base['총계정원장']:
        t=totals[row['계정코드']];t[0]+=1;t[1]+=row['차변'];t[2]+=row['대변']
    for row in base['시산표']:
        _,debit,credit=totals[row['계정코드']]
        row.update(당기차변=debit,당기대변=credit,기말잔액=row['기초잔액']+debit-credit)
    beginnings={r['계정코드']:r['기초잔액'] for r in base['시산표']}
    for row in base['독립통제']:
        count,debit,credit=totals[row['계정코드']];beginning=beginnings[row['계정코드']]
        row.update(원장행수=count,차변합계=debit,대변합계=credit,기초잔액=beginning,기말잔액=beginning+debit-credit,
                   추출근거='SYNTHETIC ONLY / 벤치 생성기가 GL에서 재계산. 외부 독립 추출 아님.',
                   작성자='합성벤치통제작성자')


def main():
    OUTPUT.mkdir(parents=True,exist_ok=True);INPUTS.mkdir(parents=True,exist_ok=True)
    started=time.perf_counter();checks=[]
    report={'ok':False,'schema_version':'gla-benchmark-1','environment':{
        'python':platform.python_version(),'implementation':platform.python_implementation(),
        'os':platform.system(),'os_release':platform.release(),'os_version':platform.version(),
        'machine':platform.machine(),'python_bits':struct.calcsize('P')*8,'processor':platform.processor()},
        'scope':{'GL_rows':10000,'claims_100000_or_1000000':False,'external_independent_evidence':False,
                 'mode':'Source Python / offline GLA / all default rules; native UI, EXE and exports not timed'},
        'limitations':['Single run on this Windows development machine; no cross-machine or performance guarantee.',
                      'TB and independent-control worksheet are recalculated by the same synthetic generator.',
                      'Repeated candidates are review prompts; no human work, fraud conclusion, approval or AI inference.',
                      'Benchmark XLSX input files are local verification artifacts, excluded from release assets.'],
        'checks':checks}
    def check(ok,name):
        if not ok:raise AssertionError(name)
        checks.append(name)
    try:
        before=fingerprint();report['source_before']=before
        base_original=load_base();base_original_digest=digest(base_original)
        expected_base_debit=sum(r['차변'] for r in base_original['총계정원장'])
        expected_base_credit=sum(r['대변'] for r in base_original['총계정원장'])
        stage=time.perf_counter();base,clones=make_base()
        report['generator_seconds']=round(time.perf_counter()-stage,6)
        check(clones==4959 and len(base['총계정원장'])==10000,'exact_10000_GL_rows_from_4959_balanced_2row_clones')
        keys={(r['회사코드'],r['전표ID'],r['행ID']) for r in base['총계정원장']}
        check(len(keys)==10000,'all_10000_company_journal_line_keys_unique')
        expected_debit=expected_base_debit+4959*36400
        expected_credit=expected_base_credit+4959*36400
        check(sum(r['차변'] for r in base['총계정원장'])==expected_debit and sum(r['대변'] for r in base['총계정원장'])==expected_credit,'generated_gross_debit_credit_match_fixed_clone_amount')
        stage=time.perf_counter();current=ledger.analyze(deepcopy(base))
        report['current_ledger_seconds']=round(time.perf_counter()-stage,6)
        check(current['blocking']==0,'current_ledger_independent_API_execution_not_blocked')
        check(len(current['tables']['입력_총계정원장'])==10000,'current_ledger_keeps_10000_rows')
        current_digest=digest(current)
        settings=[{'항목':k,'값':v} for k,v in gla.DEFAULT_SETTINGS.items()]
        input_file=INPUTS/'GLA_10000_합성반복.xlsx'
        stage=time.perf_counter();write_input(input_file,gla.EXTRA_SCHEMA,{'GLA설정':settings},base)
        report['xlsx_write_seconds']=round(time.perf_counter()-stage,6)
        input_sha=sha(input_file)
        report['memory_before_analysis']=memory()
        stage=time.perf_counter();out=gla.analyze(input_file,CONTEXT,current)
        report['gla_read_validate_aggregate_candidates_seconds']=round(time.perf_counter()-stage,6)
        report['memory_after_analysis']=memory()
        check(out['blocking']==0 and out['detail']['현재원장연결'] is True,'GLA_10000_rows_valid_bound_input')
        check(out['metrics']['원장행수']==10000 and out['metrics']['전표수']==4993,'GLA_10000_rows_4993_journals_not_truncated')
        observed_keys={(r['회사코드'],r['전표ID'],r['행ID']) for r in out['tables']['입력_총계정원장']}
        check(observed_keys==keys,'all_input_keys_retained_no_omission')
        links=out['tables']['현재원장연결']
        check(len(links)==10059 and all(r['상태']=='일치' for r in links),'current_binding_10000_GL_plus_59_TB_rows_all_match')
        check(sum(r['원장행수'] for r in out['tables']['월별집계'])==10000,'monthly_rows_total_10000')
        check(sum(r['원장행수'] for r in out['tables']['계정별집계'])==10000,'account_rows_total_10000')
        check(sum(r['원장행수'] for r in out['tables']['작성자별집계'])==10000,'author_rows_total_10000')
        for table in ('월별집계','계정별집계','작성자별집계'):
            check(sum(r['차변합계'] for r in out['tables'][table])==expected_debit and sum(r['대변합계'] for r in out['tables'][table])==expected_credit,table+'_gross_debit_credit_complete')
        check(len(out['tables']['전표계정조합'])==4993 and sum(r['원장행수'] for r in out['tables']['전표계정조합'])==10000,'journal_combination_population_complete')
        check(out['metrics']['위험후보수']==4984 and out['metrics']['위험전표수']==4981,'expected_4984_candidates_4981_unique_journals')
        counts={code:sum(r['규칙ID']==code for r in out['tables']['검토후보']) for code in gla.RULES}
        check(counts=={'GLA_WEEKEND':0,'GLA_MONTH_END':21,'GLA_HIGH_AMOUNT':3,'GLA_REPEAT':4960},'fixed_candidate_scope_21_monthend_3_large_4960_repeat')
        check(len({r['후보ID'] for r in out['tables']['검토후보']})==4984,'candidate_IDs_unique')
        journal_rows=defaultdict(set)
        for row in out['tables']['입력_총계정원장']:journal_rows[row['전표ID']].add(row['_row'])
        for candidate in out['tables']['검토후보']:
            origins={int(v) for v in re.findall(r'총계정원장!(\d+)',candidate['원본행'])}
            if origins!=journal_rows[candidate['전표ID']]:raise AssertionError('candidate original rows omitted: '+candidate['후보ID'])
        check(True,'every_candidate_has_complete_own_journal_original_rows')
        coverage={r['규칙ID']:r for r in out['tables']['규칙검토범위']}
        check(all(coverage[c]['검사대상수']==4993 for c in gla.RULES),'all_four_enabled_rules_cover_4993_journals')
        check(all(coverage[c]['미확인수']==4993 for c in ('GLA_MANUAL','GLA_NIGHT','GLA_APPROVAL')),'missing_manual_night_approval_not_inferred')
        groups=out['tables']['반복그룹색인']
        check(len(groups)==1 and groups[0]['전표수']==4960 and len(set(groups[0]['전표ID']))==4960,'one_repeat_group_indexes_4960_journals_once')
        max_reason=max(len(r['사유']) for r in out['tables']['검토후보'])
        check(max_reason<200,'candidate_reason_bounded_under_200_chars')
        repeated=[r for r in out['tables']['검토후보'] if r['규칙ID']=='GLA_REPEAT']
        check(all(r['반복그룹ID']==groups[0]['반복그룹ID'] for r in repeated),'repeat_candidates_link_shared_index')
        check(all(r['수행'] is None and r['결론'] is None and r['검토자'] is None for r in out['tables']['검토후보']),'no_automatic_human_performance_or_conclusion')
        result_bytes=len(dumps(out).encode('utf-8'))
        report['normal']={'input':input_file.relative_to(ROOT).as_posix(),'input_sha256':input_sha,'input_bytes':input_file.stat().st_size,
            'metrics':out['metrics'],'blocking':out['blocking'],'review':out['review'],
            'gross_debit':expected_debit,'gross_credit':expected_credit,'binding_rows':len(links),'binding_omissions':0,
            'candidate_rule_counts':counts,'repeat_index_rows':len(groups),'max_candidate_reason_chars':max_reason,
            'serialized_result_bytes':result_bytes,'serialized_result_mib':round(result_bytes/1024**2,3)}
        check(sha(input_file)==input_sha and digest(current)==current_digest,'benchmark_input_and_current_result_unchanged')
        del out;gc.collect()

        # One extra zero-amount unique journal line remains balanced but exceeds
        # the physical 10,000-row limit. Rejection must happen during input read.
        excessive=deepcopy(base)
        row=deepcopy(base['총계정원장'][-1]);row.update(전표ID='J-BENCH-LIMIT-10001',행ID='1',차변=0,대변=0,
            적요='SYNTHETIC ONLY / 입력행 한도 초과 확인');row['_row']=10002
        excessive['총계정원장'].append(row);recalculate_controls(excessive)
        limit_file=INPUTS/'GLA_10001_행한도초과.xlsx'
        write_input(limit_file,gla.EXTRA_SCHEMA,{'GLA설정':settings},excessive)
        limit_sha=sha(limit_file);stage=time.perf_counter();blocked=gla.analyze(limit_file,CONTEXT,current)
        report['limit_10001_read_rejection_seconds']=round(time.perf_counter()-stage,6)
        check(blocked['blocking']>0 and not blocked['tables']['검토후보'] and blocked['metrics']['원장행수']==0,'10001_rows_blocked_before_candidate_aggregation')
        check(any(i['code']=='GLA_INPUT' and '한도' in i['message'] for i in blocked['issues']),'10001_rows_rejected_by_explicit_input_limit')
        check(sha(limit_file)==limit_sha,'overlimit_input_not_mutated')
        report['over_limit']={'input':limit_file.relative_to(ROOT).as_posix(),'input_sha256':limit_sha,'GL_rows':10001,
            'blocking':blocked['blocking'],'review':blocked['review'],'issues':blocked['issues'],
            'reported_GL_rows':blocked['metrics']['원장행수'],'candidate_count':len(blocked['tables']['검토후보'])}
        check(digest(load_base())==base_original_digest,'original_base_ledger_semantic_values_unchanged')
        after=fingerprint();check(after==before,'original_source_code_and_sample_file_hashes_unchanged')
        report['source_after']=after;report['source_unchanged']=True
        report['ok']=True
    except Exception as exc:
        report.update(error=str(exc),traceback=traceback.format_exc())
    report.update(assertions=len(checks),total_wall_seconds=round(time.perf_counter()-started,6),memory_at_finish=memory())
    atomic(OUTPUT/'benchmark_10000.json',json.dumps(report,ensure_ascii=False,indent=2).encode('utf-8'))
    print(json.dumps({k:report[k] for k in ('ok','assertions','gla_read_validate_aggregate_candidates_seconds','total_wall_seconds','error') if k in report},ensure_ascii=False))
    return 0 if report['ok'] else 1


if __name__=='__main__':raise SystemExit(main())
