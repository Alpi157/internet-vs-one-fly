/** Presentation uses the impact record; it never infers escape from GF activity. */
export interface ImpactOutcome {
    caught: boolean;
    lead_ms: number | null;
    escape_onset_lead_ms: number | null;
}
const ms = (n: number) => n.toLocaleString('en-US', { maximumFractionDigits: 10 });
export const isTakeoffEscape = (impact: ImpactOutcome) => !impact.caught && impact.escape_onset_lead_ms !== null && impact.escape_onset_lead_ms > 0;
export function impactSentence(impact: ImpactOutcome | null): string {
    if (!impact) return 'Every flash is a recorded spike.';
    const gf = impact.lead_ms === null ? 'Its giant fiber did not fire before your hand landed.' : `Its giant fiber fired ${ms(impact.lead_ms)} ms before your hand landed.`;
    if (impact.caught) return gf + (impact.escape_onset_lead_ms === null ? '' : ` Takeoff began ${ms(impact.escape_onset_lead_ms)} ms before impact.`);
    if (isTakeoffEscape(impact)) return (impact.lead_ms === null ? '' : gf + ' ') + `Takeoff began ${ms(impact.escape_onset_lead_ms!)} ms before impact.`;
    return 'It walked out from under your hand. ' + (impact.lead_ms === null ? 'Its giant fiber did not fire.' : `Its giant fiber fired ${ms(impact.lead_ms)} ms before impact, too late to take off.`);
}
/** Preserve the highest GF lead rule, within pre-impact takeoff escapes first. */
export function bestTakeoffEscape<T extends ImpactOutcome>(impacts: T[]): T | undefined {
    return impacts.filter(isTakeoffEscape).sort((a, b) => (b.lead_ms ?? -Infinity) - (a.lead_ms ?? -Infinity))[0];
}
export function shareSentence(impacts: ImpactOutcome[], catches: number, used: number): string {
    const best = bestTakeoffEscape(impacts);
    if (best) return best.lead_ms === null ? 'A simulated fruit fly took off before my hand landed.' : `A simulated fruit fly brain beat my hand by ${ms(best.lead_ms)} ms.`;
    if (impacts.some(i => !i.caught)) return 'A simulated fruit fly walked out from under my hand.';
    return `I caught the simulated fly ${ms(catches)} ${catches === 1 ? 'time' : 'times'} in ${ms(used)} ${used === 1 ? 'hand' : 'hands'}.`;
}
export const impactAnnouncement = (impact: ImpactOutcome, hand: number, total: number) => `${impact.caught ? 'Caught' : 'Escaped'}. Hand ${ms(hand)} of ${ms(total)}. ${impactSentence(impact)}`;
