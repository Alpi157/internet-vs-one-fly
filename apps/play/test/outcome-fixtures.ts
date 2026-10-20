// Impact metadata fixtures for presentation branch coverage, not neural records.
export const outcomes = [
    { name: 'takeoff-gf', record: { caught: false, lead_ms: 42.5, escape_onset_lead_ms: 20 }, sentence: 'It saw your hand coming and jumped 20 ms before it landed.' },
    { name: 'takeoff-no-gf', record: { caught: false, lead_ms: null, escape_onset_lead_ms: 20 }, sentence: 'It saw your hand coming and jumped 20 ms before it landed.' },
    { name: 'walkout-no-gf', record: { caught: false, lead_ms: null, escape_onset_lead_ms: null }, sentence: 'It walked out from under your hand.' },
    { name: 'walkout-late-gf', record: { caught: false, lead_ms: 10.5, escape_onset_lead_ms: null }, sentence: 'It walked out from under your hand. Its escape neuron fired too late to jump.' },
    { name: 'caught-no-gf-no-onset', record: { caught: true, lead_ms: null, escape_onset_lead_ms: null }, sentence: 'It never saw it coming.' },
    { name: 'caught-gf-no-onset', record: { caught: true, lead_ms: 10.5, escape_onset_lead_ms: null }, sentence: 'Too quick for it. It saw your hand only 10.5 ms before it landed.' },
    { name: 'caught-no-gf-onset', record: { caught: true, lead_ms: null, escape_onset_lead_ms: 5 }, sentence: 'It never saw it coming.' },
    { name: 'caught-gf-onset', record: { caught: true, lead_ms: 42.5, escape_onset_lead_ms: 20 }, sentence: 'Too quick for it. It saw your hand only 42.5 ms before it landed.' },
];
