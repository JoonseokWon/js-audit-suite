"""Only exact catalog objects can enter the typed fact channel."""
from .catalog import build_catalog
from .headers import response_context
from .versions import FIELDS


def response_schema(packet):
    catalog=build_catalog(packet);context=response_context(packet)
    return {'type':'object','additionalProperties':False,
        'required':['context','claims','proposals','citations'],'properties':{
        'context':{'type':'object','additionalProperties':False,'required':list(context),
            'properties':{key:{'type':'string','enum':[value]} for key,value in context.items()}},
        'claims':{'type':'array','minItems':max(1,len(catalog['required_ids'])),
            'maxItems':len(catalog['claims']),'uniqueItems':True,
            'items':{'enum':catalog['claims']}},
        'proposals':{'type':'object','additionalProperties':False,'required':list(FIELDS),
            'properties':{field:{'type':'string','minLength':1,'maxLength':6000} for field in FIELDS}},
        'citations':{'type':'object','additionalProperties':False,'required':list(FIELDS),
            'properties':{field:{'type':'array','minItems':1,'maxItems':70,'uniqueItems':True,
                'items':{'type':'string','enum':[ref['id'] for ref in packet['references']]}}
                for field in FIELDS}}}}
