"""SYNTHETIC ONLY release proof/API records. Never production validation evidence."""
from unittest.mock import MagicMock
from . import config,policy

def fixture():
    inputs={'baseline/'+str(i):'b'*64 for i in range(config.BASELINE_COUNT)}
    manifest=policy.manifest_sha256(inputs)
    return {'schema':config.PROOF_SCHEMA,'version':'2.1.0','status':'passed',
        'unit':{'tests':1000,'errors':0,'failures':0,'skipped':0},
        'unit_scope':{'full_suite_snapshot':'current_source','current_source_full_suite_rerun':True,
                      'description':'SYNTHETIC ONLY current-source full-suite proof fixture.',
                      'source_manifest_sha256':manifest},
        'headless':{m:{'ok':True,'version':config.VERSION,'frozen':m=='frozen',
                      'checks':['check'+str(i) for i in range(36)],'coverage':list(config.COVERAGE),
                      'gates':{gate:True for gate in config.GATES},'current_actual_model_calls':0}
                    for m in ('source','frozen')},
        'source_frozen_observations_identical':True,'portable_layout_verified':True,
        'icon_embedded_verified':True,'unicode_roundtrip_verified':True,'bento_navigation_verified':True,
        'dpi_policy_verified':True,'current_actual_model_calls':0,
        'ime':{'current_actual_key_test':False,'scope':'No new physical IME key test.'},
        'exe':{'name':config.EXE,'bytes':200,'sha256':'a'*64},
        'build_inputs':inputs,'source_manifest_sha256':manifest}

def green_ci():
    return {'runs':[{'status':'completed','conclusion':'success','url':'https://github.com/example',
        'jobs':[{'name':'Audit Suite Python '+version,'status':'completed','conclusion':'success',
                 'steps':[{'name':name,'conclusion':'success'} for name in
                          ('Unit tests','Release policy mock tests','Headless integration')]}
                for version in ('3.12','3.14')]}]}

def metadata_api(folder, **own_changes):
    from tools.release_v21.github_api import GitHub
    api=GitHub.__new__(GitHub)
    own={'full_name':config.REPO,'id':config.REPO_ID,'private':False,'visibility':'public',
         'default_branch':'main','permissions':{'push':True},'archived':False}
    own.update(own_changes)
    releases=[{'tag_name':tag,'target_commitish':commit,'draft':False,'id':i,'assets':[]}
              for i,(tag,commit) in enumerate(config.PREVIOUS.items(),1)]
    def call(method,path,**kwargs):
        if method!='GET':raise AssertionError('Read-only metadata inspection attempted a write')
        if path=='https://api.github.com/user':return {'login':config.OWNER}
        if path=='https://api.github.com/repos/'+config.OWNER+'/for-ax-node-project':
            return {'full_name':config.OWNER+'/for-ax-node-project','id':1406782120,'private':False,'visibility':'public'}
        if path=='':return own
        if path=='/branches?per_page=100':return [{'name':'main'}]
        if path=='/tags?per_page=100':return [{'name':tag} for tag in config.PREVIOUS]
        if path=='/releases?per_page=100':return releases
        if path=='/git/ref/heads/main':return {'object':{'sha':config.BASE}}
        if path=='/git/ref/tags/'+config.TAG:return None
        if path.startswith('/git/ref/tags/'):
            tag=path[len('/git/ref/tags/'):]
            return {'object':{'type':'commit','sha':config.PREVIOUS[tag]}}
        raise AssertionError('Unexpected metadata endpoint: '+path)
    api.call=MagicMock(side_effect=call)
    return api

