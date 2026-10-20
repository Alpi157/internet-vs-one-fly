import assert from 'node:assert/strict';
import {impactSentence, impactDetail, impactAnnouncement, isTakeoffEscape, bestTakeoffEscape, shareSentence} from '../src/outcome.ts';
import {outcomes} from './outcome-fixtures.ts';
for (const {name,record,sentence} of outcomes) {
    assert.equal(impactSentence(record),sentence,name);
    assert.equal(impactAnnouncement(record,1,6),`${record.caught?'Caught':'Escaped'}. Hand 1 of 6. ${sentence}`,name);
    assert.equal(isTakeoffEscape(record),name.startsWith('takeoff'),name);
}
assert.equal(impactSentence(null),'Every flash is a recorded spike.');
for (const onset of [0,-1]) {
    const record={caught:false,lead_ms:0,escape_onset_lead_ms:onset};
    assert(!isTakeoffEscape(record));
    assert.equal(impactSentence(record),'It walked out from under your hand. Its escape neuron fired too late to jump.');
}
const takeoff=outcomes[0].record, walk={...outcomes[3].record,lead_ms:100}, withoutGF=outcomes[1].record;
assert.equal(bestTakeoffEscape([walk,takeoff]),takeoff);
assert.equal(bestTakeoffEscape([withoutGF,takeoff]),takeoff);
assert.equal(bestTakeoffEscape([walk]),undefined);
const earlier={...takeoff,lead_ms:100},tie={...earlier};
assert.equal(bestTakeoffEscape([takeoff,earlier,tie]),earlier);
assert.equal(shareSentence([walk,takeoff],0,2),'A simulated fruit fly brain beat my hand by 42.5 ms.');
assert.equal(shareSentence([walk,outcomes[4].record],1,2),'A simulated fruit fly walked out from under my hand.');
assert.equal(shareSentence([withoutGF,walk],0,2),'A simulated fruit fly took off before my hand landed.');
assert.equal(shareSentence([outcomes[4].record],1,1),'I caught the simulated fly 1 time in 1 hand.');
assert.equal(shareSentence([],0,6),'I caught the simulated fly 0 times in 6 hands.');
assert.equal(impactSentence({...takeoff,lead_ms:5555.5}),'It saw your hand coming and jumped 20 ms before it landed.');
assert.equal(impactDetail({...takeoff,lead_ms:5555.5}),'Escape neuron (giant fiber) fired 5,555.5 ms before impact.');
assert.equal(impactDetail(withoutGF),'');
console.log('PASS: 8 wording branches, announcement identity, strict onset boundary, takeoff-first best/ties, every share fallback and fixed English formatting');
