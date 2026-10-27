"""Require this commit's latest push run and both complete Windows matrix jobs."""
from .config import WORK,WORKFLOW,REPO_ID
from .policy import require,json_bytes

WORKFLOW_NAME='JS Audit Suite v2.5.0'
STEPS=('Unit tests','Release policy mock tests','Headless integration')
JOBS={'Audit v2.5 Python 3.12','Audit v2.5 Python 3.14'}


def status(api,value):
    if 'commit' not in value:return {'phase':value['phase'],'commit':None,'runs':[]}
    response=api.call('GET','/actions/runs?head_sha='+value['commit']+'&per_page=100')
    require(response.get('total_count',0)<=100,'CI 목록 한도 초과')
    found=[]
    for run in response['workflow_runs']:
        if (run['head_sha']!=value['commit'] or run['name']!=WORKFLOW_NAME or run.get('event')!='push'
                or run.get('head_branch')!='main' or run.get('path','').split('@')[0]!=WORKFLOW):continue
        require(run.get('head_repository',{}).get('id',REPO_ID)==REPO_ID,'CI 대상 저장소 불일치')
        jobs=api.call('GET','/actions/runs/'+str(run['id'])+'/jobs?per_page=100')
        require(jobs['total_count']<=100 and len(jobs['jobs'])==jobs['total_count'],'CI 작업 목록 잘림')
        found.append({'id':run['id'],'head_sha':run['head_sha'],'attempt':run.get('run_attempt',1),
            'status':run['status'],'conclusion':run['conclusion'],'url':run['html_url'],
            'jobs':[{'name':j['name'],'status':j['status'],'conclusion':j['conclusion'],'labels':j.get('labels',[]),
                     'steps':[{'name':s['name'],'conclusion':s.get('conclusion')} for s in j['steps']]} for j in jobs['jobs']]})
    result={'phase':value['phase'],'commit':value['commit'],'runs':sorted(found,key=lambda r:(r['id'],r['attempt']),reverse=True)}
    WORK.mkdir(parents=True,exist_ok=True);(WORK/'github-actions.json').write_bytes(json_bytes(result));return result


def gate(report):
    require(report['runs'],'새 커밋의 v2.5.0 push CI 필요')
    run=report['runs'][0]
    require(run['head_sha']==report['commit'] and run['status']=='completed' and run['conclusion']=='success'
            and len(run['jobs'])==2 and {j['name'] for j in run['jobs']}==JOBS,'CI 양쪽 matrix 성공 전 게시 차단')
    for job in run['jobs']:
        require(job['status']=='completed' and job['conclusion']=='success' and 'windows-latest' in job['labels'],
                'Windows Python 3.12/3.14 양쪽 성공 필요')
        steps={s['name']:s['conclusion'] for s in job['steps']}
        require(len(steps)==len(job['steps']) and all(steps.get(name)=='success' for name in STEPS),'세 필수 검증 단계 성공 전 게시 차단')
    return run
