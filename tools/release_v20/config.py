"""Version and repository constants, independent of application state."""
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2]
PROJECT = SOURCE.parents[1]
QA = PROJECT / '검증/v2.0.0'
WORK = QA / 'github-release'
STATE = WORK / 'release-state.json'
CHECKOUT = WORK / 'checkout'
VERSION = '2.0.0'
TAG = 'v' + VERSION
BASE = '945bdb4970271f0000998c8ccaadfcdeaad639f7'
OWNER = 'JoonseokWon'
REPO = OWNER + '/js-audit-suite'
REPO_ID = 1431735895
REMOTE = 'https://github.com/' + REPO + '.git'
BRANCH = 'main'
EXE = '통합 회계감사 v2.0.0.exe'
SOURCE_NAME = 'js-audit-suite-v2.0.0-source.zip'
WINDOWS_NAME = 'JS-Audit-Suite-v2.0.0-windows.zip'
VALIDATION = 'validation-report.json'
ASSETS = (WINDOWS_NAME, SOURCE_NAME, VALIDATION, 'SHA256SUMS.txt')
BASE_ZIP = PROJECT / '릴리스/v1.9.0/js-audit-suite-v1.9.0-source.zip'
BASE_ZIP_SHA = '610bb35da0a144625a7897baa685ebbfacbb30c82826caf04f068d0ea6b40873'
PREFIX = 'js-audit-suite/'
WINDOWS_PREFIX = 'JS-Audit-Suite-v2.0.0/'
PROOF_SCHEMA = 'audit-suite-v20-final-validation-1'
SCOPE = '화면 개선·감사업무 진행관리·감사조서 작성 및 검토·감사파일 보관'
RELEASE_NAME = '통합 회계감사 v2.0.0 · 화면 개선 및 감사업무 진행관리'
WORKFLOW = '.github/workflows/audit-suite-v20.yml'
WORKFLOW_NAME = 'JS Audit Suite v2.0.0'
WORKFLOW_SHA256 = '5ff7979c051c122bab57eed028b1dec37caaa68f4889c0a57789c0ced8a19a24'
PREVIOUS = {
    'v1.7.0':'2562258ac0e0c02db8f3b9f0d98036740ab67aab',
    'v1.7.1':'fbd5be7f074c1be978a3ba604acd564703e1c3c2',
    'v1.8.0':'c47250b5c092010342462a6a63d23692fd062637',
    'v1.8.1':'d9d3c18459eddce6a01d51b9bafbce441782cc16',
    'v1.9.0':BASE,
}
OLD_WORKFLOWS = tuple('.github/workflows/audit-suite-'+x+'.yml' for x in ('v17','v171','v18','v181','v19'))
MUTABLE = {'app.py','desktop_display.py','ai_desktop.py','workflow_desktop.py','common.py','windows.manifest','AuditSuite.spec',
           'README.md','AGENTS.md'}
NEW_FIXED = {'test_bento_desktop.py','tools/build_v20.py','tools/package_v20.py',
             'tools/github_release_v20.py','tools/test_release_v20.py',
             'tools/verify_bento_v20.py','tools/verify_headless_v20.py',
             'ci/audit-suite-v20.yml','문서/v2.0_사용안내.md'}
