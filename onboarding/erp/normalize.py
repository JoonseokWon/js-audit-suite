"""Preserve signed original amounts and source rows while making nonnegative GL sides."""
from collections import defaultdict
import re
from common import AuditError, cancelled, day, digest, issue, text
from .schema import REQUIRED_TARGETS, OPTIONAL_TARGETS, PROVENANCE, integer, rows, rowref


def normalize(payload, context, config, issues, event=None):
    originals=rows(payload,'source_rows')
    if config.get('source_origin')=='value_only_xlsx':
        if digest(originals)!=config.get('source_rows_sha256') or any(
                r.get('source_sha256')!=config.get('source_file_sha256') or
                r.get('source_sheet')!=config.get('source_sheet') or
                r.get('source_file')!=config.get('source_filename') for r in originals):
            raise AuditError('가져온 원본 파일·행 해시와 자료가 다릅니다. 원본 Excel을 다시 가져오세요.')
    columns = {}
    required = REQUIRED_TARGETS | ({'debit','credit'} if config['amount_mode']=='two_columns' else {'amount'})
    for r in rows(payload, 'column_mapping'):
        target, source = text(r.get('target')), text(r.get('source'))
        if target in columns or source in columns.values() or target not in required | OPTIONAL_TARGETS:
            raise AuditError('열 매핑이 중복되거나 지원하지 않는 필드입니다: ' + target)
        columns[target] = source
    if not required <= columns.keys():
        raise AuditError('필수 원본 열 매핑이 없습니다: ' + ', '.join(sorted(required-columns.keys())))
    coa = {}
    canonical = set()
    for r in rows(payload, 'coa_mapping'):
        source = text(r.get('source_account')); account = text(r.get('account_code'))
        if source in coa or account in canonical:
            raise AuditError('계정 매핑 중복: ' + source)
        for f in ('account_name', 'lead_code', 'lead_name'):text(r.get(f), f)
        if r.get('statement_type') not in ('BS','PL'):raise AuditError('BS/PL 매핑이 필요합니다.')
        coa[source] = r; canonical.add(account)
    converted=[]; trace=[]; seen=set(); physical=set(); original={}; versions=defaultdict(set)
    totals=defaultdict(lambda:[0,0,0,0,0])
    for n, raw in enumerate(originals,2):
        cancelled(event)
        if any(key not in raw for key in columns.values()):raise AuditError('원본 매핑 열 누락: '+str(n))
        for field in ('source_file','source_sha256','source_sheet'):text(raw.get(field),field)
        if not re.fullmatch('[0-9a-f]{64}', str(raw['source_sha256'])):raise AuditError('원본 SHA256 형식 오류')
        source_row=integer(raw['source_row'],False)
        if source_row<1:raise AuditError('원본 행번호는 1 이상이어야 합니다.')
        pkey=tuple(raw[f] for f in PROVENANCE)
        if pkey in physical:issue(issues,'ERP_SOURCE_DUP','같은 원본 행을 두 번 등록했습니다.',rowref(raw))
        physical.add(pkey)
        versions[raw['source_file']].add(raw['source_sha256'])
        v={target:raw[source] for target,source in columns.items()}
        jid=text(v['journal_id']); lid=text(v['line_id']); key=jid+'/'+lid
        if '/' in jid or '/' in lid:raise AuditError('전표·행ID에는 /를 사용할 수 없습니다.')
        if key in seen:issue(issues,'ERP_ROW_DUP','전표ID/행ID 중복',key)
        seen.add(key)
        account=coa.get(text(v['source_account']))
        if not account:raise AuditError('미매핑 원본 계정: '+str(v['source_account']))
        code=account['account_code']; dt=day(v['posting_date']).isoformat()
        if not day(context['시작일']) <= day(dt) <= day(context['기준일']):
            issue(issues,'ERP_PERIOD','업무 기간 밖 원본 행',rowref(raw))
        if config['amount_mode']=='two_columns':
            d=integer(v['debit']); c=integer(v['credit'])
            if d and c:issue(issues,'ERP_BOTH_SIDES','원본 한 행에 두 금액열이 모두 있습니다.',key)
        else:
            d=integer(v['amount'])*integer(config['signed_debit_factor']); c=0
        unit=integer(config['source_unit'],False)
        debit=(max(d,0)+max(-c,0))*unit; credit=(max(c,0)+max(-d,0))*unit
        item={'회사코드':context['회사코드'],'전표ID':jid,'행ID':lid,'전기일':dt,
              '계정코드':code,'차변':debit,'대변':credit,'적요':str(v['description'] or ''),
              '작성자':text(v['author']),'_row':n,'_sheet':'총계정원장'}
        converted.append(item)
        record={'원장행ID':key,'원본행':rowref(raw),'원본SHA256':raw['source_sha256'],
                '원본계정':v['source_account'],'계정코드':code,'전기일':dt,'부문':str(v.get('department') or '미지정'),
                '원본차변':d,'원본대변':c,'원본단위':unit,'차변':debit,'대변':credit,
                '순변동':debit-credit,'취소대상':str(v.get('cancel_of') or ''),
                '변환규칙':'원본 부호 보존 · 음수 금액은 반대편으로 이동'}
        trace.append(record); original[key]=record
        t=totals[code];t[0]+=1;t[1]+=d;t[2]+=c;t[3]+=debit;t[4]+=credit
    cancellations=defaultdict(list)
    for r in trace:
        ref=r['취소대상']
        if not ref:continue
        cancellations[ref].append(r['원장행ID']); source=original.get(ref)
        if not source or source['원장행ID']==r['원장행ID'] or source['취소대상'] or (
                source['계정코드']!=r['계정코드'] or source['순변동']!=-r['순변동']):
            issue(issues,'ERP_CANCEL_LINK','동일 계정 원전표와 취소 금액을 확인하세요.',r['원장행ID'])
    for ref, found in cancellations.items():
        if len(found)>1:issue(issues,'ERP_CANCEL_DUP','원본 한 행을 여러 번 취소했습니다.',ref+' → '+', '.join(found))
    for filename, hashes in versions.items():
        if len(hashes)>1:issue(issues,'ERP_SOURCE_VERSION','같은 원본 파일명에 서로 다른 버전 해시가 섞였습니다.',filename)
    if not converted or not coa:issue(issues,'ERP_EMPTY','원본 모집단·계정 매핑이 비어 있습니다.')
    return converted,trace,coa,totals
