"""Reject forbidden new text; visibly escape legacy XML-invalid characters."""
import unicodedata
from common import AuditError


def invalid_xml_positions(value):
    for index,ch in enumerate(str(value)):
        cp=ord(ch)
        if (cp<32 and cp not in (9,10,13)) or 0xD800<=cp<=0xDFFF or cp in (0xFFFE,0xFFFF):
            yield index,cp


def require_xml_text(value,field_label='본문'):
    """Do not normalize source text or change legacy records on read."""
    if not isinstance(value,str):return value
    bad=next(invalid_xml_positions(value),None)
    if bad:
        index,cp=bad;line=value.count('\n',0,index)+1
        column=index-value.rfind('\n',0,index)
        name=unicodedata.name(chr(cp),'제어문자 또는 XML 금지문자')
        raise AuditError(f'{field_label}: 문자 위치 {index+1} ({line}행 {column}열), U+{cp:04X} {name}은 저장할 수 없습니다. 문자를 제거하거나 수정하세요.')
    return value


def display_text(value):
    """Only the rendered copy changes; complete raw JSON remains authoritative."""
    bad={index:cp for index,cp in invalid_xml_positions(value)}
    return ''.join(f'⟦U+{bad[i]:04X}⟧' if i in bad else ch for i,ch in enumerate(str(value))) if bad else str(value)


def validate_structure(value,label='기록'):
    if isinstance(value,str):require_xml_text(value,label)
    elif isinstance(value,dict):
        for key,item in value.items():
            require_xml_text(str(key),label+' 항목명');validate_structure(item,label+'.'+str(key))
    elif isinstance(value,(list,tuple)):
        for index,item in enumerate(value):validate_structure(item,f'{label}[{index+1}]')
    return value
