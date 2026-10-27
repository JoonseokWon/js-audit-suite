"""Explicit source-company identity checks; context is never a missing-row fallback."""
from common import AuditError, issue, text
from .schema import rows


def identifier(value):
    if isinstance(value,bool) or value is None:return ''
    if isinstance(value,int):return str(value)
    if isinstance(value,float):return str(int(value)) if value.is_integer() else ''
    if isinstance(value,str):return value.strip()
    return ''


class CompanyScope:
    def __init__(self,payload,columns,context,issues):
        self.column=columns.get('company_id');self.expected=text(context['회사코드'])
        self.issues=issues;self.seen=set();self.mapping={}
        for row in rows(payload,'company_mapping'):
            source=identifier(row.get('source_company'));target=identifier(row.get('company_code'))
            if not source or not target or source in self.mapping:
                raise AuditError('원본 회사코드 매핑의 공백·중복·자료형을 확인하세요.')
            self.mapping[source]=target
        if not self.column:
            issue(issues,'ERP_COMPANY_UNVERIFIED',
                '원본 회사 열이 연결되지 않아 회사 소속을 자동 확인할 수 없습니다. '
                '회사코드와 추출 범위를 확인하고 열·회사코드 매핑을 다시 입력하세요.',blocking=False)

    def resolve(self,raw,ref):
        if not self.column:return None,'','회사열 미연결·미확인'
        value=raw.get(self.column);source=identifier(value)
        if not source:
            issue(self.issues,'ERP_COMPANY_EMPTY','원본 회사코드가 공백이거나 지원하지 않는 값입니다.',ref)
            return value,'','회사코드 공백·미확인'
        self.seen.add(source)
        mapped=self.mapping.get(source,source)
        if mapped!=self.expected:
            issue(self.issues,'ERP_COMPANY_MISMATCH',
                '원본 회사코드의 명시 매핑 결과가 현재 업무 회사와 다릅니다.',ref)
            return value,mapped,'다른 회사·차단'
        return value,mapped,'명시 회사열·매핑 일치'

    def finish(self):
        if len(self.seen)>1:
            issue(self.issues,'ERP_COMPANY_MIXED',
                '하나의 ERP 모집단에 서로 다른 원본 회사코드가 섞였습니다. 회사별 원본·통제를 분리해 확인하세요.')


def verified(converted,context,issues):
    return bool(converted) and all(r['회사코드']==context['회사코드'] for r in converted) and not any(
        i['code'].startswith('ERP_COMPANY_') for i in issues)
