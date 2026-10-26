"""Independent local adapters with persistent faults and circuit state."""
import asyncio
from app.services.operations import utcnow

SOURCES=('egrul','fns','bki','financials','turnover','issuance')
MODES=('success','missing','negative','unavailable','timeout','malformed','transient')

class SourceFailure(Exception):pass


class MockAdapter:
    def __init__(self,name,setting,timeout):self.name,self.setting,self.timeout=name,setting,timeout

    async def get(self,application,attempt):
        mode=self.setting.get('mode','success')
        scenario=application.get('mock_scenario','success')
        # Legacy per-application scenario affects only BKI, independent of other sources.
        if self.name=='bki' and scenario!='success':mode=scenario
        if mode=='transient':mode='unavailable' if attempt==1 else 'success'
        if self.setting.get('open',False):raise SourceFailure(self.name+': circuit_open')
        if mode=='timeout':
            try:await asyncio.wait_for(asyncio.sleep(self.timeout+1),timeout=self.timeout)
            except TimeoutError as exc:raise SourceFailure(self.name+': timeout') from exc
        if mode in {'unavailable','malformed'}:raise SourceFailure(self.name+': '+mode)
        payload={
            'egrul':{'active':mode!='negative','found':mode!='missing'},
            'fns':{'tax_debt':100000 if mode=='negative' else 0,'disqualified_director':mode=='negative'},
            'bki':{'overdue':mode=='negative','monthly_debt_payment':application.get('debt_payment',0)},
            'financials':{'revenue_monthly':application.get('revenue'),'expenses_monthly':application.get('expenses'),'derived_from':'synthetic_application'},
            'turnover':{'monthly_turnover':application.get('revenue'),'synthetic':True},
            'issuance':{'registered':True,'reference':application.get('id')},
        }[self.name]
        return dict(source='mock_'+self.name+'_v2',status=mode,synthetic=True,received_at=utcnow().isoformat(),data=None if mode=='missing' else payload)
