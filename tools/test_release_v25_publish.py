"""Publication mocks only: no credential helper, clone, push, API, or inference."""
from pathlib import Path
import copy,hashlib,io,json,sys,tempfile,unittest,zipfile
from unittest.mock import MagicMock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.release_v25 import publish as pub,ci,remote,artifacts,downloads,git_ops
from tools.release_v25.config import ASSETS,REPO,TAG,WORKFLOW,REPO_ID

COMMIT='a'*40


def value():
    return {'phase':'STAGED','commit':COMMIT,'release_id':25,'preflight_hash':'h','body':'reviewed notes',
        'source_files':artifacts.git_manifest({'app.py':b'public'}),
        'additional_files':artifacts.git_manifest({WORKFLOW:b'new workflow'}),
        'local_assets':{name:{'bytes':3,'sha256':hashlib.sha256(b'abc').hexdigest()} for name in ASSETS}}


def release():
    v=value()
    return {'id':25,'draft':True,'prerelease':True,'tag_name':TAG,'target_commitish':COMMIT,
        'name':pub.TITLE,'body':v['body'],'html_url':'https://github.com/'+REPO+'/releases/tag/'+TAG,
        'upload_url':'https://uploads.github.com/repos/'+REPO+'/releases/25/assets{?name,label}',
        'assets':[{'id':i,'name':name,'size':3,'digest':'sha256:'+v['local_assets'][name]['sha256'],
            'state':'uploaded','browser_download_url':'https://github.com/'+REPO+'/releases/download/'+TAG+'/'+name}
            for i,name in enumerate(ASSETS,1)]}


def green():
    return {'phase':'STAGED','commit':COMMIT,'runs':[{'id':25,'head_sha':COMMIT,'status':'completed',
        'conclusion':'success','url':'https://github.com/'+REPO+'/actions/runs/25',
        'jobs':[{'name':name,'status':'completed','conclusion':'success','labels':['windows-latest'],
                 'steps':[{'name':step,'conclusion':'success'} for step in ci.STEPS]} for name in sorted(ci.JOBS)]}]}


def tree():
    return {'truncated':False,'tree':[{'path':name,'type':'blob','mode':'100644','size':item['bytes'],
             'sha':item['git_blob_sha']} for name,item in {**value()['source_files'],**value()['additional_files']}.items()]}


class PublicationTests(unittest.TestCase):
    def test_dispatch_requires_explicit_mode_before_credentials(self):
        with patch('tools.release_v22.github_api.GitHub') as helper:
            with self.assertRaises(RuntimeError):pub.dispatch('implicit')
            helper.assert_not_called()

    def test_ci_requires_exact_two_windows_jobs_and_all_three_steps(self):
        ci.gate(green())
        for change in ('wrong_commit','one_job','duplicate_version','linux','missing_step','failed_step','queued'):
            r=green();run=r['runs'][0];job=run['jobs'][0]
            if change=='wrong_commit':run['head_sha']='b'*40
            if change=='one_job':run['jobs'].pop()
            if change=='duplicate_version':run['jobs'][1]['name']=job['name']
            if change=='linux':job['labels']=['ubuntu-latest']
            if change=='missing_step':job['steps'].pop()
            if change=='failed_step':job['steps'][0]['conclusion']='failure'
            if change=='queued':run['status']='in_progress'
            with self.subTest(change=change),self.assertRaises(RuntimeError):ci.gate(r)

    def test_latest_failed_run_cannot_be_replaced_by_old_success(self):
        r=green();old=copy.deepcopy(r['runs'][0]);old['id']=24
        r['runs'][0]['conclusion']='failure';r['runs'].append(old)
        with self.assertRaises(RuntimeError):ci.gate(r)

    def test_ci_status_filters_other_commit_workflow_event_and_branch(self):
        base={'id':25,'head_sha':COMMIT,'name':ci.WORKFLOW_NAME,'event':'push','head_branch':'main',
              'path':WORKFLOW,'status':'completed','conclusion':'success','html_url':'https://example/25'}
        wrong=[{**base,'id':index,**change} for index,change in enumerate(
               ({'head_sha':'b'*40},{'event':'pull_request'},{'head_branch':'other'},
                {'name':'JS Audit Suite v2.2.0'},{'path':'.github/workflows/old.yml'}),1)]
        api=MagicMock();api.call.side_effect=[{'total_count':6,'workflow_runs':wrong+[base]},
                                             {'total_count':2,'jobs':green()['runs'][0]['jobs']}]
        with tempfile.TemporaryDirectory() as folder,patch.object(ci,'WORK',Path(folder)):
            r=ci.status(api,value());self.assertEqual([x['id'] for x in r['runs']],[25]);ci.gate(r)

    def test_server_digests_sizes_sets_and_duplicates_are_required(self):
        self.assertEqual(len(pub.assets_match(release(),value())),4)
        for change in ('digest','size','state','missing','extra','duplicate'):
            r=release()
            if change=='digest':r['assets'][0]['digest']=None
            if change=='size':r['assets'][0]['size']=4
            if change=='state':r['assets'][0]['state']='new'
            if change=='missing':r['assets'].pop()
            if change=='extra':r['assets'].append({**r['assets'][0],'name':'private.db'})
            if change=='duplicate':r['assets'].append(r['assets'][0])
            with self.subTest(change=change),self.assertRaises(RuntimeError):pub.assets_match(r,value())

    def test_remote_inspector_preserves_all_nine_old_release_fingerprints(self):
        old=[]
        for index,(name,commit) in enumerate(remote.PREVIOUS.items(),1):
            item=release();item.update(id=index,tag_name=name,target_commitish=commit,draft=False);old.append(item)
        expected={'releases':{r['tag_name']:{'id':r['id'],'fingerprint':remote.fingerprint(r)} for r in old}}
        calls=[]
        def call(method,path,**kw):
            calls.append(method)
            if path=='https://api.github.com/user':return {'login':remote.OWNER}
            if path=='':return {'id':REPO_ID,'full_name':REPO,'private':False,'visibility':'public',
                               'default_branch':'main','permissions':{'push':True},'archived':False}
            if path=='/branches?per_page=100':return [{'name':'main'}]
            if path=='/tags?per_page=100':return [{'name':name} for name in remote.PREVIOUS]
            if path=='/releases?per_page=100':return old
            if path=='/git/ref/heads/main':return {'object':{'sha':remote.BASE}}
            if path=='/git/ref/tags/'+TAG:return None
            if path.startswith('/git/ref/tags/'):return {'object':{'type':'commit','sha':remote.PREVIOUS[path.rsplit('/',1)[1]]}}
            raise AssertionError(path)
        api=MagicMock();api.call.side_effect=call
        with patch.object(remote,'preflight',return_value=expected):
            self.assertEqual(remote.inspect(api)['head'],remote.BASE)
            old[0]['body']+=' changed'
            with self.assertRaisesRegex(RuntimeError,'이력 변경'):remote.inspect(api)
        self.assertEqual(set(calls),{'GET'})

    def test_remote_git_requires_one_parent_exact_files_and_no_submodules(self):
        for change in ('parent','blob','extra','submodule','truncated'):
            commit={'parents':[{'sha':remote.BASE}],'tree':{'sha':'tree'}};t=tree()
            if change=='parent':commit['parents'].append({'sha':'b'*40})
            if change=='blob':t['tree'][0]['sha']='b'*40
            if change=='extra':t['tree'].append({**t['tree'][0],'path':'private.db'})
            if change=='submodule':t['tree'].append({'type':'commit','path':'submodule'})
            if change=='truncated':t['truncated']=True
            api=MagicMock();api.call.side_effect=[commit,t]
            with self.subTest(change=change),self.assertRaises(RuntimeError):pub.check_tree(api,value())

    def test_zip_extra_or_changed_bytes_are_rejected(self):
        for data in ({'a.py':b'public','private.db':b'private'},{'a.py':b'changed'}):
            stream=io.BytesIO()
            with zipfile.ZipFile(stream,'w') as z:
                for name,raw in data.items():z.writestr(name,raw)
            with self.assertRaises(RuntimeError):artifacts.zip_match(stream.getvalue(),{'a.py':b'public'})

    def test_public_download_is_unauthenticated_and_hash_checked(self):
        assets=pub.assets_match(release(),value());opener=MagicMock()
        opener.open.side_effect=lambda *a,**k:io.BytesIO(b'abc')
        with patch.object(downloads.urllib.request,'build_opener',return_value=opener):
            self.assertEqual(len(downloads.verify_public(assets)),4)
        self.assertTrue(all('Authorization' not in call.args[0].headers for call in opener.open.call_args_list))
        assets[ASSETS[0]]['sha256']='0'*64
        with patch.object(downloads.urllib.request,'build_opener',return_value=opener),self.assertRaises(RuntimeError):
            downloads.verify_public(assets)

    def test_public_download_rejects_foreign_url_and_redirect(self):
        assets=pub.assets_match(release(),value());assets[ASSETS[0]]['url']='https://other.example/file'
        with patch.object(downloads.urllib.request,'build_opener') as opener,self.assertRaises(RuntimeError):
            downloads.verify_public(assets)
        opener.return_value.open.assert_not_called()
        request=downloads.urllib.request.Request('https://github.com/')
        with self.assertRaises(RuntimeError):downloads.PublicRedirect().redirect_request(request,None,302,'',{},'https://evil.example/')

    def test_publish_failure_before_green_ci_never_mutates_remote(self):
        api=MagicMock();r=green();r['runs'][0]['status']='in_progress'
        with patch.object(pub,'load',return_value=value()),patch.object(pub,'check_pins'),patch.object(pub,'status',return_value=r):
            with self.assertRaises(RuntimeError):pub.publish(api)
        api.call.assert_not_called()

    def test_stage_resumes_two_assets_without_publishing_or_pushing(self):
        v=value();v['phase']='PUSHED';r=release();r['assets']=r['assets'][:2]
        remote_state={'head':COMMIT,'tag':None,'release':r,'preflight_hash':'h'};api=MagicMock()
        api.call.side_effect=lambda method,path,**kw:release() if method=='GET' else None
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);state=base/'state';state.touch();out=base/'릴리스'/TAG;out.mkdir(parents=True)
            for name in ASSETS:(out/name).write_bytes(b'abc')
            with patch.object(pub,'STATE',state),patch.object(pub,'PROJECT',base),patch.object(pub,'load',return_value=v),\
                 patch.object(pub,'check_pins'),patch.object(pub,'inspect',return_value=remote_state),\
                 patch.object(pub,'check_commit'),patch.object(pub,'save'),patch.object(git_ops,'push') as push:
                self.assertEqual(pub.stage(api)['phase'],'STAGED');push.assert_not_called()
        posts=[c for c in api.call.call_args_list if c.args[0]=='POST']
        self.assertEqual(len(posts),2);self.assertTrue(all(c.args[1].startswith('https://uploads.github.com/repos/'+REPO+'/') for c in posts))
        self.assertFalse(any(c.args[0]=='PATCH' for c in api.call.call_args_list))

    def test_publication_only_after_gate_then_verification_download_failure_is_not_verified(self):
        api=MagicMock();r=release();r['draft']=False
        state={'head':COMMIT,'tag':{'object':{'type':'commit','sha':COMMIT}},'release':r}
        with tempfile.TemporaryDirectory() as folder,patch.object(pub,'WORK',Path(folder)),\
             patch.object(pub,'load',return_value=value()),patch.object(pub,'check_pins'),\
             patch.object(pub,'inspect',return_value=state),patch.object(pub,'status',return_value=green()),\
             patch.object(pub,'check_tree'),patch.object(pub,'save') as save,\
             patch.object(pub,'verify_public',side_effect=RuntimeError('public hash mismatch')):
            with self.assertRaises(RuntimeError):pub.verify(api)
            save.assert_not_called();self.assertFalse((Path(folder)/'release-verified.json').exists())


if __name__=='__main__':unittest.main()
