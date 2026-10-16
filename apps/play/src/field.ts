import type { Frame } from './game.ts';
export class MicroscopeField {
    canvas: HTMLCanvasElement;
    private c: CanvasRenderingContext2D;
    private layer = document.createElement('canvas');
    private sprite = document.createElement('canvas');
    private dpr = 0;
    private cachedArenaPixels = 0;
    private image = new Image();
    private profile: any;
    private display: any;
    constructor(canvas: HTMLCanvasElement, profile: any, display: any, base: string, onReady: () => void = () => { }) { this.canvas = canvas; this.c = canvas.getContext('2d')!; this.profile = profile; this.display = display; this.image.onload = () => { this.cache(); onReady(); }; void this.loadFly(base); this.cache(); }
    private async loadFly(base: string) {
        const source = await fetch(base + 'art/fly.svg').then(r => r.text());
        const doc = new DOMParser().parseFromString(source, 'image/svg+xml');
        const svg = doc.documentElement, defs = svg.querySelector('defs')!, original = defs.querySelector('#fly')!;
        svg.setAttribute('viewBox', '0 8 960 124');
        svg.querySelector(':scope > use')!.remove();
        // One SVG atlas and one rasterization per DPR: the approved art's actual
        // legs and wings change pose; the body heading is never animated away.
        for (let pose = 0; pose < 8; pose++) {
            const fly = original.cloneNode(true) as Element; fly.id = 'pose-' + pose;
            const swing = pose > 0 && pose < 7 ? Math.sin((pose - 1) / 6 * Math.PI * 2) * 4 : 0;
            const legs = fly.querySelectorAll('[href="#legL"]');
            legs[0].setAttribute('transform', `rotate(${swing} 54 51)`);
            legs[1].setAttribute('transform', `translate(120 0) scale(-1 1) rotate(${-swing} 54 51)`);
            if (pose === 7) {
                const wings = fly.querySelectorAll('[href="#wingL"]');
                wings[0].setAttribute('transform', 'rotate(35 52.5 49)');
                wings[1].setAttribute('transform', 'translate(120 0) scale(-1 1) rotate(35 52.5 49)');
            }
            fly.querySelectorAll('[id]').forEach(e => e.removeAttribute('id')); defs.append(fly);
            const use = doc.createElementNS('http://www.w3.org/2000/svg', 'use'); use.setAttribute('href', '#pose-' + pose); use.setAttribute('transform', `translate(${pose * 120} 0)`); svg.append(use);
        }
        this.image.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(new XMLSerializer().serializeToString(svg));
    }
    // The chamber margin is outside the playable radius, on every viewport.
    get arenaPixels() { return innerWidth < 900 ? 304 : 329; }
    point(x: number, y: number) { const scale = this.arenaPixels / this.profile.arena_radius; return [350 + x * scale, 350 - y * scale]; }
    aim(clientX: number, clientY: number) { const r = this.canvas.getBoundingClientRect(), scale = this.profile.arena_radius / this.arenaPixels; return this.clamp({ x: ((clientX - r.left) / r.width * 700 - 350) * scale, y: (350 - (clientY - r.top) / r.height * 700) * scale }); }
    clamp(p: {
        x: number;
        y: number;
    }) { const d = Math.hypot(p.x, p.y), r = this.profile.arena_radius; if (d > r) {
        p.x *= r / d * (1 - Number.EPSILON);
        p.y *= r / d * (1 - Number.EPSILON);
    } return p; }
    private cache() {
        const dpr = Math.min(devicePixelRatio || 1, 3);
        this.dpr = dpr;
        this.cachedArenaPixels = this.arenaPixels;
        if (this.canvas.width !== 700 * dpr) {
            this.canvas.width = 700 * dpr;
            this.canvas.height = 700 * dpr;
        }
        this.layer.width = this.canvas.width;
        this.layer.height = this.canvas.height;
        const c = this.layer.getContext('2d')!;
        c.scale(dpr, dpr);
        c.clearRect(0, 0, 700, 700);
        const grad = c.createRadialGradient(320, 290, 20, 350, 350, 348);
        for (const [pos, color] of [[0, '#f2f2ec'], [.55, '#e6e7e0'], [.82, '#cfd2ca'], [1, '#9da39b']] as const)
            grad.addColorStop(pos, color);
        c.fillStyle = grad;
        c.beginPath();
        c.arc(350, 350, 348, 0, Math.PI * 2);
        c.fill();
        c.strokeStyle = '#262b27';
        c.lineWidth = 3;
        c.stroke();
        c.strokeStyle = '#1e231f38';
        c.lineWidth = 2;
        c.beginPath();
        c.arc(350, 350, this.arenaPixels, 0, Math.PI * 2);
        c.stroke();
        // Static specimen dust: deterministic decoration, never a neural observation.
        c.fillStyle = '#4b584220';
        for (let i = 0; i < 130; i++) {
            const x = (i * 137.51) % 680 + 10, y = (i * i * 51.73) % 680 + 10;
            if (Math.hypot(x - 350, y - 350) > 333)
                continue;
            c.beginPath();
            c.arc(x, y, .6 + (i % 4) * .4, 0, Math.PI * 2);
            c.fill();
        }
        c.strokeStyle = '#52624925';
        c.lineWidth = 1;
        c.beginPath();
        c.moveTo(90, 490);
        c.bezierCurveTo(130, 470, 150, 500, 190, 474);
        c.moveTo(520, 590);
        c.bezierCurveTo(530, 609, 555, 598, 569, 620);
        c.stroke();
        const l = this.display.fly_length_arena_units * this.arenaPixels / this.profile.arena_radius;
        c.strokeStyle = '#1e231f';
        c.lineWidth = 2;
        c.beginPath();
        c.moveTo(350 - l / 2, 623);
        c.lineTo(350 + l / 2, 623);
        c.moveTo(350 - l / 2, 618);
        c.lineTo(350 - l / 2, 628);
        c.moveTo(350 + l / 2, 618);
        c.lineTo(350 + l / 2, 628);
        c.stroke();
        c.font = '700 23px Atkinson';
        c.fillStyle = '#1e231f';
        c.textAlign = 'center';
        c.fillText(this.display.scale_bar_label, 350, 652);
        this.sprite.width = 160 * 8 * dpr;
        this.sprite.height = 166 * dpr;
        if (this.image.complete && this.image.naturalWidth)
            this.sprite.getContext('2d')!.drawImage(this.image, 0, 0, this.sprite.width, this.sprite.height);
    }
    draw(f: Frame, options: {
        reduced: boolean;
        frames: Frame[];
        aim: {
            x: number;
            y: number;
        };
        reticle: boolean;
        holdMs: number | null;
        lastImpact: any;
    }, output: HTMLCanvasElement = this.canvas) {
        if (this.dpr !== Math.min(devicePixelRatio || 1, 3) || this.cachedArenaPixels !== this.arenaPixels)
            this.cache();
        if (output !== this.canvas && output.width !== this.canvas.width) { output.width = this.canvas.width; output.height = this.canvas.height; }
        const c = output === this.canvas ? this.c : output.getContext('2d')!;
        c.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
        c.clearRect(0, 0, 700, 700);
        c.drawImage(this.layer, 0, 0, 700, 700);
        c.save();
        c.beginPath();
        c.arc(350, 350, 347, 0, Math.PI * 2);
        c.clip();
        const s = f.strike;
        if (s && f.tick <= s.impact_tick) {
            const [x, y] = this.point(s.aim_x, s.aim_y), progress = Math.max(0, Math.min(1, (f.tick - s.start_tick) / (s.impact_tick - s.start_tick))), radius = s.radius * this.arenaPixels / this.profile.arena_radius;
            c.save();
            c.translate(x, y);
            c.fillStyle = `rgba(20,24,20,${.08 + .2 * progress})`;
            c.filter = `blur(${3 + 12 * (1 - progress)}px)`;
            for (let i = 0; i < 4; i++) {
                c.beginPath();
                c.ellipse(radius * (-.75 + i * .5), -radius * (1.3 + (.4 - Math.abs(1.5 - i) * .2)), radius * .19, radius * .9, -.35, 0, Math.PI * 2);
                c.fill();
            }
            c.filter = 'none';
            const r = radius * (.4 + .6 * progress), g = c.createRadialGradient(0, 0, r * .65, 0, 0, r + 10 * (1 - progress));
            g.addColorStop(0, `rgba(20,24,20,${.15 + .55 * progress})`);
            g.addColorStop(1, progress === 1 ? 'rgba(20,24,20,.7)' : '#14181400');
            c.fillStyle = g;
            c.beginPath();
            c.arc(0, 0, r + 10 * (1 - progress), 0, Math.PI * 2);
            c.fill();
            c.strokeStyle = '#1e231fa6';
            c.lineWidth = 1.5;
            c.setLineDash([5, 5]);
            c.beginPath();
            c.arc(0, 0, radius, 0, Math.PI * 2);
            c.stroke();
            c.restore();
        }
        if (f.air && !options.reduced) {
            c.strokeStyle = '#1e231f30';
            c.lineWidth = 3;
            c.beginPath();
            let first = true;
            for (const v of options.frames)
                if (v.tick <= f.tick && v.tick > f.tick - 160 && v.air) {
                    const [x, y] = this.point(v.body.x, v.body.y);
                    first ? c.moveTo(x, y) : c.lineTo(x, y);
                    first = false;
                }
            c.stroke();
        }
        const [x, y] = this.point(f.body.x, f.body.y);
        const length = this.display.fly_length_arena_units * this.arenaPixels / this.profile.arena_radius;
        const air = f.air && !options.reduced;
        c.save();
        c.translate(x, y);
        c.rotate(-Math.atan2(f.body.heading_y, f.body.heading_x) + Math.PI / 2);
        if (air) {
            c.fillStyle = '#1e231f20';
            c.beginPath();
            c.ellipse(8, 10, length * .3, length * .45, 0, 0, Math.PI * 2);
            c.fill();
            c.scale(1.06, 1.06);
        }
        const pose = options.reduced ? 0 : f.air ? 7 : f.gait > 0 ? 1 + Math.floor(f.gait * 12) % 6 : 0;
        c.drawImage(this.sprite, pose * 160 * this.dpr, 0, 160 * this.dpr, 166 * this.dpr,
            -length * 120 / 124 / 2, -length / 2, length * 120 / 124, length);
        c.restore();
        if (options.reticle || options.holdMs !== null) {
            const [ax, ay] = this.point(options.aim.x, options.aim.y);
            c.strokeStyle = '#1e231f';
            c.lineWidth = 2;
            c.beginPath();
            c.arc(ax, ay, 15, 0, Math.PI * 2);
            c.moveTo(ax - 22, ay);
            c.lineTo(ax + 22, ay);
            c.moveTo(ax, ay - 22);
            c.lineTo(ax, ay + 22);
            c.stroke();
            if (options.holdMs !== null) {
                const ms = options.holdMs, t = this.profile.hold_thresholds_ms;
                c.lineWidth = 4;
                c.beginPath();
                c.arc(ax, ay, 30, -Math.PI / 2, -Math.PI / 2 + Math.min(1, ms / (t[1] * 1.6)) * Math.PI * 2);
                c.stroke();
                c.fillStyle = '#1e231f';
                c.font = '700 20px Atkinson';
                c.textAlign = 'center';
                const name = this.profile.strikes[ms < t[0] ? 0 : ms < t[1] ? 1 : 2].name;
                c.fillText(name[0].toUpperCase() + name.slice(1), ax, ay + 57);
            }
        }
        c.restore();
        c.strokeStyle = '#e9ede6';
        c.lineWidth = 3;
        c.beginPath();
        c.arc(350, 350, 348, -Math.PI / 2, -Math.PI / 2 + Math.max(0, 1 - f.tick * .5 / this.profile.round_ms) * Math.PI * 2);
        c.stroke();
    }
}
