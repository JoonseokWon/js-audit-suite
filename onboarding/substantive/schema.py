"""Explicit empty-table headers for the human-editable Excel gateway."""
BASE = ('record_id', 'source_ref', 'gl_refs')
TABLE_FIELDS = {
    '유형자산증감': {
        'assets': BASE+('asset_id','asset_type','cost_account','accum_account','opening_cost',
                       'closing_cost','opening_accum','closing_accum'),
        'asset_movements': BASE+('asset_id','kind','date','cost_delta','accum_delta','pair_id',
                                'proceeds','gain','cash_account','gain_account'),
    },
    '감사표본선정': {
        'population': BASE+('amount',),
        'specific_items': BASE+('population_id','reason'),
        'errors': BASE+('population_id','book_amount','audited_amount','reviewer','reason'),
    },
    '금융기관조회': {
        'institution_sources': BASE+('institution_id','source_type','field','book_amount','account_code','factor'),
        'requests': BASE+('institution_id','request_id','requested_fields'),
        'responses': BASE+('institution_id','request_id','field','amount','as_of','details',
                          'authenticity','reviewer','reason'),
    },
    '주석구성대사': {
        'note_balances': BASE+('note_id','account_code','factor','category','opening_asis','closing_asis'),
        'note_movements': BASE+('balance_id','kind','amount','evidence_type'),
        'note_components': BASE+('note_id','component_kind','account_code','amount','as_is_amount',
                                'related_id','details','evidence_type'),
    },
    '분류검토': {
        'classification_items': BASE+('account_code','amount','as_is_class','proposed_class',
            'acquisition_date','maturity_date','proposal_actor','proposal_reason'),
        'classification_evidence': BASE+('item_id','criterion','status','observation'),
    },
}
