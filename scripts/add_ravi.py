import sys
sys.path.insert(0,'.')
import os
os.environ.setdefault('DATABASE_URL','sqlite:///./test_local.db')
from backend.app.db.database import SessionLocal
from backend.app.db.models import SourceModel, RecordModel
from backend.app.services.normalization import normalize_record
db=SessionLocal()
src=db.query(SourceModel).filter(SourceModel.name=='Demo Spec - Ravi').first()
if not src:
    src=SourceModel(name='Demo Spec - Ravi', source_type='csv', config={'benchmark':'spec'})
    db.add(src)
    db.commit()
    db.refresh(src)
    print(f'created {src.id}')
else:
    print(f'exists {src.id}')
recs=[
    {'customer_id':'C10482','name':'Ravi Kumar','email':'ravi@gmail.com','phone':'+91 9876543210','system':'CRM'},
    {'customer_id':'10482','name':'RAVI KUMAR','email':'ravi@gmail.com','phone':'9876543210','system':'ERP'},
    {'customer_id':'C-10482','name':'Ravi K.','email':'ravi@gmail.com','phone':None,'system':'Accounting'},
]
for r in recs:
    exists=db.query(RecordModel).filter(RecordModel.source_id==src.id, RecordModel.source_record_id==r['customer_id']).first()
    if exists:
        continue
    d={'customer_id':r['customer_id'],'name':r['name'],'email':r['email'],'phone':r['phone']}
    nd=normalize_record(d)
    rec=RecordModel(source_id=src.id, source_record_id=r['customer_id'], data=d, raw_data=r, normalized_data=nd)
    db.add(rec)
    print(f"added {r['customer_id']}")
db.commit()
from backend.app.db.models import RecordModel as RM
all_recs=db.query(RM).filter(RM.source_id==src.id).all()
print(f"total {len(all_recs)}")
for rec in all_recs:
    print(rec.source_record_id, rec.data)
db.close()
