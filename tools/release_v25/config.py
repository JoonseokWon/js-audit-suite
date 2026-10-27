from pathlib import Path

SOURCE=Path(__file__).resolve().parents[2]
PROJECT=SOURCE.parents[1]
QA=PROJECT/'검증/v2.5.0'
VERSION='2.5.0'
TAG='v'+VERSION
REPO='JoonseokWon/js-audit-suite'
REPO_ID=1431735895
REMOTE='https://github.com/'+REPO+'.git'
BASE_ZIP=PROJECT/'릴리스/v2.3.0/js-audit-suite-v2.3.0-source.zip'
BASE_SHA='2b60f539360f16ee1988eb2cd27175841134422c0f84ea2a133555424fc8b111'
BASE_COUNT=1994
PREFIX='js-audit-suite/'
EXE='통합 회계감사 v2.5.0.exe'
SOURCE_NAME='js-audit-suite-v2.5.0-source.zip'
WINDOWS_NAME='JS-Audit-Suite-v2.5.0-windows.zip'
ASSETS=(WINDOWS_NAME,SOURCE_NAME,'validation-report.json','SHA256SUMS.txt')
WORKFLOW='.github/workflows/audit-suite-v25.yml'
WORK=QA/'github-release'
CHECKOUT=WORK/'checkout'

V24_ADDITIONS=set('''ai_contract/__init__.py ai_contract/catalog.py ai_contract/events.py
ai_contract/headers.py ai_contract/render.py ai_contract/schema.py ai_contract/source_read.py
ai_contract/validation.py ai_contract/versions.py ai_evidence_inventory/__init__.py
ai_evidence_inventory/coverage.py ai_evidence_inventory/encoding.py ai_evidence_inventory/hashing.py
ai_quality/actual_v24.py data_controls/__init__.py data_controls/attribution.py data_controls/reader.py
desktop/actions/execution_status.py desktop/ai/draft_sections.py desktop/ai/inventory.py
export_support/__init__.py export_support/builder.py export_support/layout.py export_support/text.py
human_input.py onboarding/erp/company.py test_review_ai_contract.py test_review_ai_helpers.py
test_review_ai_source_limits.py test_review_data_accrual.py test_review_data_company.py
test_review_data_limits.py test_review_export.py test_review_export_status.py test_review_export_ui.py
test_review_inventory.py test_review_storage.py tools/verify_ai_v24.py
문서/v2.4_독립리뷰수정.md'''.split())

MUTABLE=set('''AGENTS.md README.md accruals.py adapters.py ai_provider.py ai_workpapers.py
audit_workflow.py common.py export_streaming.py exporter.py input_limits.py onboarding/ai_evidence.py ai_quality/capture.py
onboarding/erp/__init__.py onboarding/erp/normalize.py onboarding/erp/samples.py onboarding/erp/schema.py
onboarding/workbooks.py test_ai_desktop.py test_ai_provider.py test_ai_workpapers.py
test_onboarding_workspace.py verify_v18.py windows_text.py workspace.py
app.py procedures.py display_schema.py desktop/entry_tests.py AuditSuite.spec demo_case/verification.py'''.split())
PACKAGES=('ai_contract','ai_quality','audit_links','misstatements','v25_demo',
          'desktop/audit_links','desktop/misstatements','tools/release_v25')
FIXED={'audit_extensions.py','desktop/actions/audit_extensions.py','export_support/audit_registers.py',
       'tools/verify_ai_v25.py','tools/verify_flow_v25.py','tools/verify_headless_v25.py',
       'tools/release_v25.py','tools/test_release_v25.py','tools/test_release_v25_publish.py',
       'ci/audit-suite-v25.yml','문서/v2.5_사용안내.md'}
