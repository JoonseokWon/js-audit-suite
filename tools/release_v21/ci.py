"""Only this commit's latest push run, with two complete Windows matrix jobs."""
from .config import *
from .policy import require,json_bytes

def status(api,value):
    if 'commit' not in value:return {'phase':value['phase'],'commit':None,'runs':[]}
    response=api.call('GET','/actions/runs?head_sha='+value['commit']+'&per_page=100')
    found=[]
    for run in response['workflow_runs']:
        if (run['head_sha']!=value['commit'] or run['name']!=WORKFLOW_NAME or run.get('event')!='push'
                or run.get('head_branch')!=BRANCH or run.get('path','').split('@')[0]!=WORKFLOW):continue
        jobs=api.call('GET','/actions/runs/'+str(run['id'])+'/jobs?per_page=100')
        require(jobs.get('total_count',0)<=100,'CI 작업 한도 초과')
        found.append({'id':run['id'],'status':run['status'],'conclusion':run['conclusion'],'url':run['html_url'],
            'jobs':[{'name':j['name'],'status':j['status'],'conclusion':j['conclusion'],
                     'steps':[{'name':s['name'],'conclusion':s.get('conclusion')} for s in j['steps']]} for j in jobs['jobs']]})
    result={'phase':value['phase'],'commit':value['commit'],'runs':sorted(found,key=lambda r:r['id'],reverse=True)}
    (WORK/'github-actions.json').write_bytes(json_bytes(result));return result

def gate(report):
    import re
    require(report['runs'],'새 커밋의 v2.1.0 push CI 필요')
    run=report['runs'][0]
    require(run['status']=='completed' and run['conclusion']=='success' and len(run['jobs'])==2,'CI 성공 전 게시 차단')
    versions=set()
    for job in run['jobs']:
        require(job['status']=='completed' and job['conclusion']=='success','Python matrix 미완료/실패')
        found=re.findall(r'(?<![\d.])3\.(?:12|14)(?![\d.])',job['name'])
        require(len(found)==1,'Python matrix 이름 확인 실패');versions.add(found[0])
        steps={s['name']:s['conclusion'] for s in job['steps']}
        require(all(steps.get(name)=='success' for name in ('Unit tests','Release policy mock tests','Headless integration')),
                '세 검증 단계 성공 전 게시 차단')
    require(versions=={'3.12','3.14'},'Python 3.12/3.14 양쪽 필요')
    return run
