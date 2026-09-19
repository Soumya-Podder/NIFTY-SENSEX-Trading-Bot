"""Isolated lifecycle evidence; fake accounts never reach the live broker."""
import copy
from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.forward_comparison import ForwardComparison, ExperimentStore
from app.session import local_time,now_ist
from app.store import Store


class Broker:
    def __init__(self):
        self.value={'positions':[],'cash':30000.,'enabled':True,'loss_ledger':{'entries':0}}
        self.policy_value={'trade_risk':600}
        self.policy=SimpleNamespace(describe=lambda:dict(self.policy_value))
    def snapshot(self): return copy.deepcopy(self.value)
    def control(self,enabled): self.value['enabled']=enabled
    def positions(self): return {'positions':self.value['positions']}


def running(tmp_path):
    store=Store(tmp_path/'forward.db')
    recording={'run_id':'tape','worker_alive':True,'dropped_this_run':0,'error':None}
    alive=SimpleNamespace(is_alive=lambda:True)
    primary=SimpleNamespace(broker=Broker(),threads=[alive],status={},policy_day='2026-09-15',
                            ml_frozen={'models':{'scope':'candidate'}},
                            settings=SimpleNamespace(session_exit='15:05'),
                            market=SimpleNamespace(recorder=SimpleNamespace(status=lambda:dict(recording))))
    reference=SimpleNamespace(broker=Broker(),threads=[alive],status={},stopped=False)
    reference.stop=lambda:setattr(reference,'stopped',True)
    service=ForwardComparison(store,primary)
    service.reference=reference
    service.experiment={'id':'test','session':'2026-09-15','models':{'scope':'candidate'},
                        'policy':{'trade_risk':600},'recorder_run':'tape','initial_drops':0,
                        'starting_cash':30000.,'status':'RUNNING','issues':[]}
    return service,recording


@pytest.mark.parametrize('fault',['recorder_stopped','recorder_restarted','dropped','reference_persistence','primary_dead','reference_dead','risk_change'])
def test_faults_cannot_finalize_as_complete(tmp_path,fault):
    service,recording=running(tmp_path)
    if fault=='recorder_stopped': recording['worker_alive']=False
    elif fault=='recorder_restarted': recording['run_id']='other'
    elif fault=='dropped': recording['dropped_this_run']=1
    elif fault=='reference_persistence': service.reference.status['persistence_error']='disk failure'
    elif fault=='primary_dead': service.primary.threads=[]
    elif fault=='reference_dead': service.reference.threads=[]
    else: service.primary.broker.policy_value['trade_risk']=900
    reference=service.reference
    service.cycle(local_time('2026-09-15T15:05:00+05:30'))
    saved=service.store.get_record('forward_sessions','test')
    assert saved['status']=='INCOMPLETE' and saved['issues']
    assert reference.stopped and service.reference is None
    if fault=='risk_change': assert not reference.broker.value['enabled']


def test_healthy_comparison_records_paired_results_without_profit_claim(tmp_path):
    service,_=running(tmp_path)
    service.primary.broker.value['cash']=30200
    service.reference.broker.value['cash']=30100
    service.cycle(local_time('2026-09-15T15:05:00+05:30'))
    saved=service.store.get_record('forward_sessions','test')
    assert saved['status']=='COMPLETE' and saved['improvement']==100
    assert service.status()['self_improvement_proven'] is False


def test_pending_exit_is_not_finalized_at_deadline(tmp_path):
    service,_=running(tmp_path)
    service.reference.broker.value['positions']=[{'id':'unfilled'}]
    service.cycle(local_time('2026-09-15T15:05:00+05:30'))
    assert service.reference is not None and service.experiment['status']=='RUNNING'
    assert not service.store.get_record('forward_sessions','test')


def test_alive_thread_with_old_cycle_is_stale(tmp_path):
    service,_=running(tmp_path)
    service.thread=SimpleNamespace(is_alive=lambda:True)
    service.last_checked_at=now_ist()-timedelta(seconds=40)
    assert service.status()['stale']
    service.cycle(local_time('2026-09-15T10:00:00+05:30'))
    assert not service.status()['stale']


def test_reference_writes_are_isolated(tmp_path):
    store=Store(tmp_path/'namespaces.db'); reference=ExperimentStore(store,'trial')
    store.put_record('paper','account',{'cash':30000})
    reference.save_bundle([('paper','account',{'cash':29000})])
    assert store.get_record('paper','account')['cash']==30000
    assert reference.get_record('paper','account')['cash']==29000
