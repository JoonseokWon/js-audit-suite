"""Version and repository constants, independent of application state."""
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2]
PROJECT = SOURCE.parents[1]
QA = PROJECT / '검증/v2.1.0'
WORK = QA / 'github-release'
STATE = WORK / 'release-state.json'
CHECKOUT = WORK / 'checkout'
VERSION = '2.1.0'
TAG = 'v' + VERSION
BASE = '0a9cb33fcf0f551b5ce8937fb871fa2326626fbd'
OWNER = 'JoonseokWon'
REPO = OWNER + '/js-audit-suite'
REPO_ID = 1431735895
REMOTE = 'https://github.com/' + REPO + '.git'
BRANCH = 'main'
EXE = '통합 회계감사 v2.1.0.exe'
SOURCE_NAME = 'js-audit-suite-v2.1.0-source.zip'
WINDOWS_NAME = 'JS-Audit-Suite-v2.1.0-windows.zip'
VALIDATION = 'validation-report.json'
ASSETS = (WINDOWS_NAME, SOURCE_NAME, VALIDATION, 'SHA256SUMS.txt')
BASE_ZIP = PROJECT / '릴리스/v2.0.0/js-audit-suite-v2.0.0-source.zip'
BASE_ZIP_SHA = '5aee469cb1575dd61e5fb43f8538b10f512bddfc934d3ee82f178babe7cd91e0'
BASELINE_COUNT = 1864
MIN_UNIT_TESTS = 895
PREFIX = 'js-audit-suite/'
WINDOWS_PREFIX = 'JS-Audit-Suite-v2.1.0/'
PROOF_SCHEMA = 'audit-suite-v21-final-validation-1'
SCOPE = 'ERP 자료 정리·독립 원장 통제·실증절차 지원·원장 연결 현금흐름표·감사조서 작성 및 검토'
RELEASE_NAME = '통합 회계감사 v2.1.0 · 실무자료와 원장 연결 감사절차'
WORKFLOW = '.github/workflows/audit-suite-v21.yml'
WORKFLOW_NAME = 'JS Audit Suite v2.1.0'
WORKFLOW_SHA256 = 'fac44d46a6620cee9b4770979df7ecf444d74d0f15e7fa0d040ff5bc86e02399'
COVERAGE = tuple('AU'+str(i).zfill(2) for i in range(1,9)) + tuple('CF'+str(i).zfill(2) for i in range(1,9))
GATES = ('human_approval_preserved','input_security','ledger_pin','workpaper_export')
PREVIOUS = {
    'v1.7.0':'2562258ac0e0c02db8f3b9f0d98036740ab67aab',
    'v1.7.1':'fbd5be7f074c1be978a3ba604acd564703e1c3c2',
    'v1.8.0':'c47250b5c092010342462a6a63d23692fd062637',
    'v1.8.1':'d9d3c18459eddce6a01d51b9bafbce441782cc16',
    'v1.9.0':'945bdb4970271f0000998c8ccaadfcdeaad639f7',
    'v2.0.0':BASE,
}
OLD_WORKFLOWS = tuple('.github/workflows/audit-suite-'+x+'.yml' for x in ('v17','v171','v18','v181','v19','v20'))
MUTABLE = {'app.py','common.py','adapters.py','workspace.py','procedures.py','ai_workpapers.py','display_schema.py',
           'desktop/shared.py','desktop/entry_tests.py','desktop/chrome/header.py','desktop/views/inputs.py',
           'desktop/widgets/navigation.py','README.md','AGENTS.md'}
NEW_FIXED = {'tools/build_v21.py','tools/package_v21.py',
             'tools/github_release_v21.py','tools/test_release_v21.py',
             'tools/verify_onboarding_v21.py','tools/verify_headless_v21.py',
             'ci/audit-suite-v21.yml','문서/v2.1_사용안내.md'}
