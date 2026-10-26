"""Version and repository constants, independent of application state."""
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2]
PROJECT = SOURCE.parents[1]
QA = PROJECT / '검증/v2.2.0'
WORK = QA / 'github-release'
STATE = WORK / 'release-state.json'
CHECKOUT = WORK / 'checkout'
VERSION = '2.2.0'
TAG = 'v' + VERSION
BASE = 'f6d32f5972a28f27efafef5f6ff90c740d5269bd'
OWNER = 'JoonseokWon'
REPO = OWNER + '/js-audit-suite'
REPO_ID = 1431735895
REMOTE = 'https://github.com/' + REPO + '.git'
BRANCH = 'main'
EXE = '통합 회계감사 v2.2.0.exe'
SOURCE_NAME = 'js-audit-suite-v2.2.0-source.zip'
WINDOWS_NAME = 'JS-Audit-Suite-v2.2.0-windows.zip'
VALIDATION = 'validation-report.json'
ASSETS = (WINDOWS_NAME, SOURCE_NAME, VALIDATION, 'SHA256SUMS.txt')
BASE_ZIP = PROJECT / '릴리스/v2.1.0/js-audit-suite-v2.1.0-source.zip'
BASE_ZIP_SHA = '34f6df64e7877233f292955bc90dabc5b2b339140d6b5e1d1b6da71888e0261e'
BASELINE_COUNT = 1940
MIN_UNIT_TESTS = 1052
PREFIX = 'js-audit-suite/'
WINDOWS_PREFIX = 'JS-Audit-Suite-v2.2.0/'
PROOF_SCHEMA = 'audit-suite-v22-final-validation-1'
SCOPE = '실제 로컬 AI 조서 생성·근거 검증·JS전자 오류 시연·사람 수정과 승인·Excel 연결'
RELEASE_NAME = '통합 회계감사 v2.2.0 · 로컬 AI 조서와 JS전자 감사 시연'
WORKFLOW = '.github/workflows/audit-suite-v22.yml'
WORKFLOW_NAME = 'JS Audit Suite v2.2.0'
WORKFLOW_SHA256 = 'b1d50f7f37626ccb83db2d7fdccb31a29a5069ad24a879c8a954b0c3ddd4aa5d'
COVERAGE = tuple('AU'+str(i).zfill(2) for i in range(1,9)) + tuple('CF'+str(i).zfill(2) for i in range(1,9))
GATES = ('human_approval_preserved','input_security','ledger_pin','workpaper_export')
PREVIOUS = {
    'v1.7.0':'2562258ac0e0c02db8f3b9f0d98036740ab67aab',
    'v1.7.1':'fbd5be7f074c1be978a3ba604acd564703e1c3c2',
    'v1.8.0':'c47250b5c092010342462a6a63d23692fd062637',
    'v1.8.1':'d9d3c18459eddce6a01d51b9bafbce441782cc16',
    'v1.9.0':'945bdb4970271f0000998c8ccaadfcdeaad639f7',
    'v2.0.0':'0a9cb33fcf0f551b5ce8937fb871fa2326626fbd',
    'v2.1.0':BASE,
}
OLD_WORKFLOWS = tuple('.github/workflows/audit-suite-'+x+'.yml' for x in ('v17','v171','v18','v181','v19','v20','v21'))
MUTABLE = {'app.py','common.py','adapters.py','workspace.py','procedures.py','ai_workpapers.py','display_schema.py',
           'desktop/shared.py','desktop/entry_tests.py','desktop/chrome/header.py','desktop/views/inputs.py',
           'desktop/widgets/navigation.py','README.md','AGENTS.md','ai_provider.py','local_ai_runtime.py'}
NEW_FIXED = {'tools/build_v22.py','tools/package_v22.py',
             'tools/github_release_v22.py','tools/test_release_v22.py',
             'tools/verify_flow_v22.py','tools/verify_headless_v22.py','tools/verify_ai_v22.py',
             'ci/audit-suite-v22.yml','문서/v2.2_사용안내.md'}

ACTUAL_MODEL = 'qwen3:4b-instruct-2507-q4_K_M'
ACTUAL_MODEL_DIGEST = '0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0'
