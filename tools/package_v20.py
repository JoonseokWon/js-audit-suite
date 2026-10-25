"""Package an already verified v2 candidate. No inference, build or remote action."""
from pathlib import Path
import json
import argparse
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.release_v20.config import *
from tools.release_v20.policy import require,sha,json_bytes,write_zip,safe_file
from tools.release_v20.proof import current,summary
from tools.release_v20.artifacts import record,validate_set

def write_identical(folder,name,raw):
    path=safe_file(folder,name)
    if path.exists():
        require(path.is_file() and path.read_bytes()==raw,'기존 다른 배포 파일은 덮어쓰지 않습니다: '+name)
    else:
        with path.open('xb') as stream:stream.write(raw)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--candidate-executable',type=Path,help='Explicit already-verified staged candidate EXE')
    args=parser.parse_args()
    proof,files,old,exe,config=current(args.candidate_executable)
    QA.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='package-',dir=QA) as temp:
        stage=Path(temp)
        write_zip(stage/SOURCE_NAME,files,PREFIX)
        public=summary(proof,files,old,sha((stage/SOURCE_NAME).read_bytes()))
        validation=json_bytes(public)
        windows={'실행파일/'+EXE:exe,'실행파일/portable-config.json':config,
                 'README.md':files['README.md'],VALIDATION:validation}
        for relative,raw in files.items():
            if relative.startswith(('문서/','라이선스/')):windows[relative]=raw
            if relative.startswith('sector_resources/'):
                windows['데이터/업종별_합성원천자료/'+relative[len('sector_resources/'):]]=raw
        windows['문서/회사별업무_보관안내.txt']=(
            '실행파일/'+EXE+'와 portable-config.json을 함께 보관하세요.\n'
            '데이터/회사별업무는 새 업무를 위한 빈 폴더입니다. 기존 업무를 덮어쓰지 않습니다.\n'
            '상단 회사 선택 또는 업무 열기로 업무를 열고, 분석 모듈과 조서를 선택하세요.\n').encode('utf-8')
        windows['파일목록_SHA256.json']=json_bytes([{'file':p,'bytes':len(v),'sha256':sha(v)} for p,v in sorted(windows.items())])
        write_zip(stage/WINDOWS_NAME,windows,WINDOWS_PREFIX,empty=('데이터/회사별업무/',))
        (stage/VALIDATION).write_bytes(validation)
        assets=record({name:(stage/name).read_bytes() for name in ASSETS[:3]})
        (stage/'SHA256SUMS.txt').write_bytes(''.join(assets[name]['sha256']+'  '+name+'\n' for name in ASSETS[:3]).encode())
        expected,_=validate_set(stage)
        for folder in (SOURCE/'배포',PROJECT/'릴리스'/TAG):
            safe_file(folder.parent,folder.name);folder.mkdir(parents=True,exist_ok=True)
            for name in ASSETS:write_identical(folder,name,(stage/name).read_bytes())
            require(validate_set(folder)[0]==expected,'복사 후 배포 해시 불일치')
    report={'version':VERSION,'status':'passed','source_files':len(files),'previous_public_paths_preserved':len(old),
            'current_actual_model_calls':0,'supported_scope':SCOPE,'remote_operations_performed':False,
            'assets':list(expected.values())}
    (QA/'package-validation.json').write_bytes(json_bytes(report));print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0

if __name__=='__main__':raise SystemExit(main())
