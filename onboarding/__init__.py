"""Auditor-controlled data preparation and substantive audit workbench."""

MODULES = ('실무자료·원장', '유형자산증감', '감사표본선정', '금융기관조회',
           '주석구성대사', '분류검토', '현금흐름표연결')
PROCEDURES = dict(zip(('D01', 'D02', 'D03', 'D04', 'D05', 'D06', 'D07'), MODULES))
SCHEMA = 'js-audit-onboarding-1'
