"""Readable human-led registers; full immutable records remain in evidence JSON."""

MS_LABELS={'id':'검토기록ID','description':'차이·검토내용','assessment':'왜곡표시 해당 판단',
    'classification':'분류','period':'기초·당기','amount':'대표 검토금액','correction_state':'수정·미수정',
    'company_position':'회사 수용·이견','company_note':'회사 의견','tax_effect':'세효과',
    'tax_basis':'세효과 근거','qualitative':'정성적 중요성','qualitative_note':'정성 검토내용',
    'judgment':'감사인 판단 기록','projection_basis':'추정·투영 근거','group_id':'동일오류 그룹ID',
    'counted':'대표금액 집계 포함','current':'현재 자료 기준','missing':'보완할 사항',
    'verification_state':'실제 GL 수정 대사','candidate_ids':'자동후보ID','procedure_ids':'연결 조서ID',
    'evidence_ids':'증거ID','run_refs':'원실행·결과해시','baseline_ledger':'수정 전 원장',
    'actor':'기록자','at':'기록시각 UTC','revision':'기록 버전','input_basis':'입력 기준',
    'below_trivial':'사소기준 미만 참고','trivial_policy':'사소금액 처리 원칙'}

LINK_LABELS={'id':'기록ID','risk_id':'위험ID','procedure_id':'절차ID','response_id':'대응ID',
    'assertions':'사람이 분류한 경영진주장','inherent_rating':'고유위험 등급',
    'inherent_reason':'고유위험 평가 근거','control_rating':'통제위험 등급',
    'control_reason':'통제위험 평가 근거','significant_risk':'유의적위험 해당 판단',
    'significant_reason':'유의적위험 판단 근거','nature':'절차 성격','timing':'수행 시기',
    'extent':'범위','sources':'원본별 회사·기간·위치·관련성','runs':'실행·결과해시',
    'performed':'사람 수행기록','performed_date':'사람 입력 수행일','performer':'수행기록자',
    'sufficiency':'사람의 증거 충분성 판단','sufficiency_reason':'충분성·적합성 판단 근거',
    'workpaper_id':'수행 조서ID','f03_id':'왜곡표시 집계 조서','misstatement_ids':'왜곡표시ID',
    'note_ids':'검토의견ID','paper_hash':'조서 내용 해시','edit_revision':'조서 개정ID',
    'actor':'기록자','at':'기록시각 UTC','revision':'기록 버전','pin':'입력 기준'}


def details(records,labels):
    for record in records:
        for key,value in record.items():
            yield {'기록ID':record['id'],'항목':labels.get(key,key),'기록':value}


def add_registers(add,snapshot):
    ms=snapshot.get('misstatements',{})
    if ms.get('records'):
        add('왜곡표시검토대장',[{label:r.get(key) for key,label in MS_LABELS.items()
            if key in ('id','description','assessment','classification','period','amount','correction_state',
                       'company_position','tax_effect','qualitative','group_id','counted','current',
                       'verification_state','missing','procedure_ids','evidence_ids')}
            for r in ms['records']])
        add('왜곡표시상세기록',list(details(ms['records'],MS_LABELS)),['기록ID','항목','기록'])
        add('왜곡표시금액집계',[{'기초·당기':r['period'],'분류':r['classification'],
            '수정·미수정':r['correction_state'],'대표 건수':r['count'],'절대금액 합계':r['gross_amount'],
            '양수 금액':r['positive_amount'],'음수 절대금액':r['negative_amount_abs'],
            '세효과 양수':r['tax_positive'],'세효과 음수 절대금액':r['tax_negative_abs'],
            '세효과 미확인 건수':r.get('tax_unknown_count',0),
            '집계 원칙':r['policy']} for r in ms['summary']])
        add('동일오류그룹',ms['groups'])
        add('왜곡표시계정영향',ms['account_impacts'])
        add('수정분개실제GL대사',ms['verifications'])
        add('왜곡표시재확인',ms['reconfirmations'])
    linked=snapshot.get('audit_links',{})
    if linked.get('active'):
        add('위험절차연결점검',[{'위험ID':r['risk_id'],'절차ID':r['procedure_id'],
            '대응ID':r['response_id'],'상태':r['status'],'점검코드':r['code'],'내용':r['message']}
            for r in linked['rows']])
        for key,name in (('assessments','경영진주장위험평가'),('responses','위험대응절차'),
                         ('performances','사람수행기록'),('workpapers','위험대응조서연결')):
            records=list(linked[key].values())
            add(name,[{LINK_LABELS.get(k,k):v for k,v in r.items()} for r in records])
            add(name+'상세',list(details(records,LINK_LABELS)),['기록ID','항목','기록'])
