"""An isolated invented engagement; real company folders are never altered."""
from pathlib import Path
from common import atomic,dumps,text
from onboarding import MODULES,PROCEDURES
from onboarding.demo import CONTEXT,ledger_tables
from onboarding.integration import sample
from onboarding.confirmation import confirm_input
from onboarding.workbooks import save_ledger,save_input


def create_demo(folder,*,confirmed=False,actor='',reason=''):
    from workspace import Workspace
    from procedures import task_definitions
    import runtime,json
    context=dict(CONTEXT)
    if confirmed:text(actor,'가상 입력 확인자');text(reason,'가상 입력 확인 사유')
    engagement=dict(context,회사명='JS전자 · 실무절차 예제',회계체계='K-IFRS',
        감사기준='가상 실무절차 검증용 · 실제 감사수행 아님',작성자='가상 작성자',더미업무=True)
    ws=Workspace(folder,create=engagement)
    inputs=ws.root/'예제입력';inputs.mkdir()
    core=save_ledger(ledger_tables(context),inputs/'독립통제_원장.xlsx')
    ws.execute('원장·리드',core)
    records={}
    for index,module in enumerate(MODULES,1):
        payload=sample(module,context)
        save_input(module,payload,inputs/(f'{index:02}_'+module+'_입력.xlsx'))
        if confirmed:payload=confirm_input(module,payload,actor,reason)
        path=inputs/(f'{index:02}_'+module+'.json');atomic(path,dumps(payload).encode('utf-8'))
        records[module]=ws.execute(module,path)
    catalog=json.loads((runtime.configure()/'procedure_catalog.json').read_text(encoding='utf-8'))
    for task in task_definitions(ws,catalog):
        if task['id'] not in PROCEDURES:continue
        ws.save_procedure({**task,'preparer':'가상 작성자','performed':'','conclusion':'',
            'performed_date':'','evidence':'가상자료 · 실제 감사증거 아님'})
    atomic(ws.root/'예제_안내.txt',(
        'JS전자 가상 20전표·44행 자료입니다. 실제 회사 자료가 아닙니다.\n'
        '예상 당기순이익 137,000원, 영업현금 103,000원, 투자현금 -55,000원, 재무현금 40,000원, 기말현금 1,088,000원.\n'
        '입력정책 확인은 실무절차 입력·검사 화면에서 직접 기록하세요. 조서 수행·결론·승인·검토는 비워 두었습니다.\n'
    ).encode('utf-8'))
    return ws,records
