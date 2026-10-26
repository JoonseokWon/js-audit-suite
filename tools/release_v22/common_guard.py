"""Allow only a version and declarative procedure-registry extension in common.py."""
import ast
from .config import VERSION
from .policy import require

ONBOARDING = dict(zip(('D01','D02','D03','D04','D05','D06','D07'),
    ('실무자료·원장','유형자산증감','감사표본선정','금융기관조회','주석구성대사','분류검토','현금흐름표연결')))


def partition(raw, current=False):
    module=ast.parse(raw.decode('utf-8-sig'));keep=[];registry={};version=None;imported=False
    for node in module.body:
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name):
            name=node.targets[0].id
            if name=='VERSION':version=ast.literal_eval(node.value);continue
            if name=='PROCEDURE_MODULES':registry.update(ast.literal_eval(node.value));continue
        if isinstance(node,ast.ImportFrom) and node.module=='onboarding':
            require(current and [(n.name,n.asname) for n in node.names]==[
                ('MODULES','ONBOARDING_MODULES'),('PROCEDURES','ONBOARDING_PROCEDURES')],
                'common.py에서 허용하지 않은 onboarding import')
            require(not imported,'common.py onboarding import 중복');imported=True;continue
        if isinstance(node,ast.Expr) and isinstance(node.value,ast.Call):
            call=node.value
            if (isinstance(call.func,ast.Attribute) and isinstance(call.func.value,ast.Name)
                    and call.func.value.id=='PROCEDURE_MODULES' and call.func.attr=='update'):
                require(len(call.args)==1 and not call.keywords,'common.py 절차 update 형식 오류')
                arg=call.args[0]
                if isinstance(arg,ast.Name):
                    require(current and imported and arg.id=='ONBOARDING_PROCEDURES',
                            'common.py 절차 update는 확정 목록만 허용합니다.')
                    registry.update(ONBOARDING)
                else:registry.update(ast.literal_eval(arg))
                continue
        keep.append(node)
    return ast.dump(ast.Module(body=keep,type_ignores=[])),registry,version


def validate_common(old,new):
    before,registry,_=partition(old,True)
    after,current,version=partition(new,True)
    require(before==after,'common.py 계산·입력·직렬화 정책은 변경할 수 없습니다.')
    require(version==VERSION and current==dict(registry,**ONBOARDING),
            'common.py는 현재 버전과 기존 절차+신규 7개 절차 목록이어야 합니다.')
