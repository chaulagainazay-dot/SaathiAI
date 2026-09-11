from datetime import datetime, timezone, timedelta
import pytest
from saathi.platform.backtest.pit import DatasetRevision, visible_revision_at, visible_revisions_at

T=datetime(2025,1,1,tzinfo=timezone.utc)
def rev(i, days, value='h'):
 return DatasetRevision('d',i,'bar-1',T,T+timedelta(days=days),value+ i, 'r'+str(int(i[1:])-1) if int(i[1:])>1 else '')

def test_revision_visibility_selects_latest_known_revision():
 rows=[rev('r1',1),rev('r2',20,'c'),rev('r3',40,'d')]
 assert visible_revision_at(rows,T+timedelta(days=10)).revision_id=='r1'
 assert visible_revision_at(rows,T+timedelta(days=30)).revision_id=='r2'
 assert visible_revision_at(rows,T+timedelta(days=50)).revision_id=='r3'

def test_revision_lineage_and_missing_metadata_fail_closed():
 with pytest.raises(ValueError): DatasetRevision('d','r1','x',T,T,'')
 a=rev('r1',1); b=DatasetRevision('d','r2','bar-1',T,T+timedelta(days=2),'x','r2')
 with pytest.raises(ValueError): visible_revisions_at([a,b],T+timedelta(days=3))
