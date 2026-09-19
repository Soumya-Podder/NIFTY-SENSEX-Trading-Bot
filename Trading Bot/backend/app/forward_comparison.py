"""Prospective reference account. No real-order authority or additive profit claims."""
import copy
import hashlib
import json
import threading
import uuid
from .broker import PaperBroker
from .portfolio_engine import MultiStrategyPaperEngine
from .session import now_ist, local_time, session_state
from .learning_validation import VERSION


class ExperimentStore:
    """All reference-account writes remain in an isolated namespace."""
    def __init__(self,store,identifier):
        self.store=store; self.prefix='forward/'+identifier+'/'
        self.path=store.path+'#'+self.prefix
    def get_record(self,namespace,key,default=None): return self.store.get_record(self.prefix+namespace,key,default)
    def put_record(self,namespace,key,value): return self.store.put_record(self.prefix+namespace,key,value)
    def list_records(self,namespace,limit=100): return self.store.list_records(self.prefix+namespace,limit)
    def save_bundle(self,items): return self.store.save_bundle([(self.prefix+n,k,v) for n,k,v in items])
    def active_learning_policies(self): return {}
    def record_event(self,value): self.put_record('events',str(uuid.uuid4()),value)


class FixedLearning:
    lock=threading.Lock()
    def freeze(self,now): return {'session':str(now.date()),'models':{}}
    def score(self,signal,frozen):
        return {'allowed':True,'status':'FIXED_REFERENCE','probability':None,'reason':'No learned entry filter in the reference account'}


class ReferenceEngine(MultiStrategyPaperEngine):
    def __init__(self,primary,store,broker):
        super().__init__(primary.settings,store,primary.gateway,broker,primary.market)
        self.primary=primary; self.learning=FixedLearning()
    def _sync_inputs(self):
        with self.primary.lock:
            frames=dict(self.primary.frames); quotes=dict(self.primary.quotes)
        with self.lock: self.frames=frames; self.quotes=quotes
    def _request_protection(self,signal,contract): return self.primary._request_protection(signal,contract)
    def cycle(self):
        self._sync_inputs()
        super().cycle()
    def portfolio_cycle(self):
        self._sync_inputs()
        super().portfolio_cycle()
    def publish(self,item):
        # Never publish reference fills as trades in the primary UI/event bus.
        self.store.record_event({**item,'account_role':'forward_reference'})
    def start(self):
        if self.threads: return
        self.stop_event.clear()
        for name,target in (('forward-reference-exits',self._loop),('forward-reference-selector',self._entry_loop)):
            thread=threading.Thread(name=name,target=target,daemon=True)
            self.threads.append(thread); thread.start()


class ForwardComparison:
    def __init__(self,store,primary):
        self.store=store; self.primary=primary; self.reference=None; self.experiment=None
        self.thread=None; self.stop_event=threading.Event(); self.lock=threading.RLock()
        self.current={'status':'STARTING','self_improvement_proven':False}
        self.last_checked_at=None

    def _models(self): return dict(getattr(self.primary,'ml_frozen',{}).get('models',{}))
    def _recording(self):
        recorder=getattr(self.primary.market,'recorder',None)
        return recorder.status() if recorder else {}
    def positions(self):
        return self.reference.broker.positions()['positions'] if self.reference else []

    def _attach(self,experiment):
        account_store=ExperimentStore(self.store,experiment['id'])
        broker=PaperBroker(account_store,self.primary.settings.paper_capital,self.primary.broker.cost,
                           self.primary.settings.max_quote_age_seconds,entry_cutoff=self.primary.settings.entry_cutoff,
                           policy=self.primary.broker.policy)
        self.reference=ReferenceEngine(self.primary,account_store,broker)
        self.experiment=experiment
        self.reference.start()

    def _register(self,now,models):
        day=str(now.date())
        for identifier in models.values():
            model=self.store.get_record('ml_models',identifier,{})
            guard=model.get('overfitting_checks',{})
            if guard.get('version')!=VERSION or not guard.get('passed') or model.get('expires_at','')<=now.isoformat():
                self.current={'status':'MODEL_VALIDATION_REQUIRED','self_improvement_proven':False}; return
        recording=self._recording()
        if not recording.get('worker_alive') or recording.get('error') or not recording.get('run_id'):
            self.current={'status':'WAITING_FOR_QUOTE_RECORDING','self_improvement_proven':False}; return
        with self.primary.broker.lock:
            account=copy.deepcopy(self.primary.broker.state)
        if account['positions'] or account['session_date']!=day or account.get('loss_ledger',{}).get('entries'):
            self.current={'status':'WAITING_FOR_CLEAN_SESSION_START','self_improvement_proven':False}; return
        policy=self.primary.broker.policy.describe()
        signature=hashlib.sha256(json.dumps({'models':models,'policy':policy},sort_keys=True).encode()).hexdigest()
        identifier=day+':'+signature[:20]
        if self.store.get_record('forward_sessions',identifier):
            self.current={'status':'SESSION_ALREADY_RECORDED','self_improvement_proven':False}; return
        experiment={'id':identifier,'session':day,'signature':signature,'models':models,'policy':policy,
                    'registered_at':now.isoformat(),'starting_cash':account['cash'],'status':'RUNNING',
                    'recorder_run':recording['run_id'],'initial_drops':recording['dropped_this_run'],
                    'issues':[],'source':'prospective_reference_account','self_improvement_proven':False}
        scoped=ExperimentStore(self.store,identifier)
        # Copy the already-observed history that conditions the initial EV gate.
        prior=self.store.list_records('episodes',10000)
        items=[(scoped.prefix+'paper','account',account),('forward_sessions',identifier,experiment),
               ('forward_state','active',{'id':identifier})]
        items.extend((scoped.prefix+'episodes',r['id'],r) for r in prior if r.get('id') and r.get('exit_ts') and local_time(r['exit_ts'])<now)
        self.store.save_bundle(items)
        self._attach(experiment)

    def _issue(self,reason):
        if reason not in self.experiment['issues']:
            self.experiment['issues'].append(reason)
            self.store.put_record('forward_sessions',self.experiment['id'],self.experiment)

    def cycle(self,now=None):
        self._cycle(now)
        self.last_checked_at=now_ist()

    def _cycle(self,now=None):
        now=local_time(now or now_ist()); day=str(now.date())
        with self.lock:
            if self.reference is None:
                pointer=self.store.get_record('forward_state','active',{})
                saved=self.store.get_record('forward_sessions',pointer.get('id',''),{})
                if saved.get('status')=='RUNNING':
                    self._attach(saved)
                    self._issue('Process restart: continuous paired-session coverage requires review')
            models=self._models()
            if self.reference is None:
                if not models:
                    self.current={'status':'WAITING_FOR_VALIDATED_MODEL','self_improvement_proven':False}; return
                if session_state(now)!='PREOPEN' or now.strftime('%H:%M')<'09:10':
                    self.current={'status':'WAITING_FOR_PREOPEN_REGISTRATION','self_improvement_proven':False}; return
                self._register(now,models)
                if self.reference is None: return
            experiment=self.experiment
            recording=self._recording()
            if models!=experiment['models'] and getattr(self.primary,'policy_day',None)==day:
                self._issue('Candidate model set changed during comparison')
                self.reference.broker.control(enabled=False)
            if (recording.get('run_id')!=experiment['recorder_run'] or not recording.get('worker_alive')
                    or recording.get('dropped_this_run',0)>experiment['initial_drops'] or recording.get('error')):
                self._issue('Quote recording continuity is incomplete')
            if (not self.reference.threads or any(not t.is_alive() for t in self.reference.threads)
                    or any(self.reference.status.get(k) for k in ('error','selector_error','persistence_error'))):
                self._issue('Reference execution worker unhealthy')
            if (not self.primary.threads or any(not t.is_alive() for t in self.primary.threads)
                    or any(self.primary.status.get(k) for k in ('error','selector_error','persistence_error'))):
                self._issue('Primary execution worker unhealthy')
            if self.primary.broker.policy.describe()!=experiment['policy'] or self.reference.broker.policy.describe()!=experiment['policy']:
                self._issue('Risk policy changed during comparison')
                self.reference.broker.control(enabled=False)
            primary=self.primary.broker.snapshot(); reference=self.reference.broker.snapshot()
            if (primary['enabled']!=reference['enabled'] and models==experiment['models']
                    and 'Risk policy changed during comparison' not in experiment['issues']):
                self._issue('Account enable/pause controls diverged')
                self.reference.broker.control(enabled=primary['enabled'])
            if day!=experiment['session']:
                self._issue('Session did not finalize before the next calendar day')
            closing=day!=experiment['session'] or now.strftime('%H:%M')>=self.primary.settings.session_exit
            if closing and not primary['positions'] and not reference['positions']:
                experiment.update(status='COMPLETE' if not experiment['issues'] else 'INCOMPLETE',finished_at=now.isoformat(),
                                  candidate_net=primary['cash']-experiment['starting_cash'],
                                  reference_net=reference['cash']-experiment['starting_cash'],
                                  candidate_trades=primary.get('loss_ledger',{}).get('entries',0),
                                  reference_trades=reference.get('loss_ledger',{}).get('entries',0))
                experiment['improvement']=experiment['candidate_net']-experiment['reference_net']
                self.store.save_bundle([('forward_sessions',experiment['id'],experiment),('forward_state','active',{})])
                self.reference.stop(); self.reference=None
            self.current={'status':experiment['status'],'session':experiment['session'],'experiment_id':experiment['id'],
                          'models':experiment['models'],'issues':list(experiment['issues']),
                          'reference_positions':len(reference['positions']),'self_improvement_proven':False,
                          'account_role':'isolated_reference; never added to primary profit or risk budgets'}

    def start(self):
        if self.thread and self.thread.is_alive(): return
        self.stop_event.clear()
        self.thread=threading.Thread(target=self._loop,name='forward-comparison',daemon=True); self.thread.start()
    def _loop(self):
        while not self.stop_event.is_set():
            try: self.cycle()
            except Exception as exc: self.current={'status':'ERROR','error_type':type(exc).__name__,'self_improvement_proven':False}
            self.stop_event.wait(5)
    def stop(self):
        self.stop_event.set()
        if self.thread: self.thread.join(timeout=3)
        if self.reference: self.reference.stop()
    def status(self):
        alive=bool(self.thread and self.thread.is_alive())
        age=(now_ist()-self.last_checked_at).total_seconds() if self.last_checked_at else None
        return {**self.current,'worker_alive':alive,'checked_at':self.last_checked_at.isoformat() if self.last_checked_at else None,
                'age_seconds':age,'stale':not alive or age is None or age>30}
