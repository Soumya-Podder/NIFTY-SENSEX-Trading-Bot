import assert from 'node:assert/strict';
import { test } from 'node:test';
import { decisionReviewView } from '../src/decisionReview.ts';

const now=Date.parse('2026-09-28T10:00:00+05:30');
const review={evaluated_at:new Date(now).toISOString(),decision:'PUT',phase:'CANDIDATE',reason:'Reviewed',
 checks:{risk:{status:'PASS'},momentum:{status:'PASS'}},agents:{Momentum:{status:'PASS'},News:{status:'DATA_UNAVAILABLE'}}};
const data=(r=review)=>({engine:{session:'ENTRY_WINDOW'},strategies:{reviews:{NIFTY:r}}});

test('four or even eight generic passes never fabricate a CALL decision',()=>{
 const d={pipelines:{NIFTY:Array.from({length:8},()=>({status:'PASS'}))}};
 assert.equal(decisionReviewView(d,'NIFTY',true,now).stance,'AWAITING REVIEW');
 assert.equal(decisionReviewView(data(),'NIFTY',true,now).stance,'PUT');
 assert.equal(decisionReviewView(data(),'SENSEX',true,now).stance,'AWAITING REVIEW');
});

test('stale, future, disconnected, blocked and closed-session evidence is not a trade proposal',()=>{
 for(const offset of [-121000,1000]) assert.equal(decisionReviewView(data({...review,evaluated_at:new Date(now+offset).toISOString()}),'NIFTY',true,now).stance,'AWAITING REVIEW');
 assert.equal(decisionReviewView(data(),'NIFTY',false,now).stance,'OFFLINE');
 assert.equal(decisionReviewView({...data(),engine:{session:'WEEKEND'}},'NIFTY',true,now).stance,'WAIT');
 assert.equal(decisionReviewView({...data(),engine:{session:'ENTRY_WINDOW',selector_error:'failed'}},'NIFTY',true,now).stance,'BLOCKED');
 assert.equal(decisionReviewView(data({...review,checks:{risk:{status:'BLOCKED'}}}),'NIFTY',true,now).stance,'WAIT');
 assert.equal(decisionReviewView({...data(),account:{open_positions:1}},'NIFTY',true,now).stance,'MANAGING');
});
