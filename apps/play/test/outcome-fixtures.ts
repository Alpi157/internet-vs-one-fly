// Impact metadata fixtures for presentation branch coverage, not neural records.
export const outcomes = [
    { name: 'takeoff-gf', record: { caught: false, lead_ms: 42.5, escape_onset_lead_ms: 20 }, sentence: 'Its giant fiber fired 42.5 ms before your hand landed. Takeoff began 20 ms before impact.' },
    { name: 'takeoff-no-gf', record: { caught: false, lead_ms: null, escape_onset_lead_ms: 20 }, sentence: 'Takeoff began 20 ms before impact.' },
    { name: 'walkout-no-gf', record: { caught: false, lead_ms: null, escape_onset_lead_ms: null }, sentence: 'It walked out from under your hand. Its giant fiber did not fire.' },
    { name: 'walkout-late-gf', record: { caught: false, lead_ms: 10.5, escape_onset_lead_ms: null }, sentence: 'It walked out from under your hand. Its giant fiber fired 10.5 ms before impact, too late to take off.' },
    { name: 'caught-no-gf-no-onset', record: { caught: true, lead_ms: null, escape_onset_lead_ms: null }, sentence: 'Its giant fiber did not fire before your hand landed.' },
    { name: 'caught-gf-no-onset', record: { caught: true, lead_ms: 10.5, escape_onset_lead_ms: null }, sentence: 'Its giant fiber fired 10.5 ms before your hand landed.' },
    { name: 'caught-no-gf-onset', record: { caught: true, lead_ms: null, escape_onset_lead_ms: 5 }, sentence: 'Its giant fiber did not fire before your hand landed. Takeoff began 5 ms before impact.' },
    { name: 'caught-gf-onset', record: { caught: true, lead_ms: 42.5, escape_onset_lead_ms: 20 }, sentence: 'Its giant fiber fired 42.5 ms before your hand landed. Takeoff began 20 ms before impact.' },
];
