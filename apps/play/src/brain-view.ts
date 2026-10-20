import { decodeArbors, type Arbors } from './anatomy.ts';
import type { Frame } from './game.ts';
export const ANATOMY_CAPTION = 'Brain: front view. Nerve cord: underside view. Real MaleCNS neuron skeletons, simplified for display.';
/** Display smoothing only: never writes into a frame or simulation state. */
export function spikeAlpha(nowTick: number, spikeTick: number, tauMs = 60) { return spikeTick > nowTick ? 0 : Math.exp(-(nowTick - spikeTick) * .5 / tauMs); }
export class BrainView {
    canvas: HTMLCanvasElement;
    overlay: HTMLCanvasElement;
    mode = 'brain';
    ready = false;
    loadMs = 0;
    lod: string;
    private anatomy!: Arbors;
    private rois: any;
    private nodes: any[];
    private display: any;
    private gl: WebGL2RenderingContext | null;
    private fallback: CanvasRenderingContext2D | null = null;
    private staticLayers = new Map<string, HTMLCanvasElement>();
    private ranges: number[][] = [];
    private activeIndices!: WebGLBuffer;
    private indexScratch = new Uint32Array(0);
    private activityTexture!: WebGLTexture;
    private activity = new Float32Array(0);
    private somaBuffer!: WebGLBuffer;
    private somaCount = 0;
    private lineCount = 0;
    private texture!: WebGLTexture;
    private lines!: WebGLBuffer;
    private quad!: WebGLBuffer;
    private lineProgram!: WebGLProgram;
    private texProgram!: WebGLProgram;
    private bounds: number[] = [];
    private scale = 1;
    private offset = [0, 0];
    private shownFrame?: Frame;
    private shownFrames: Frame[] = [];
    private shownDim = false;
    private lastTick = -1;
    private lastMode = '';
    private circuit: string;
    private quality: { resolutionScale: number; glow: boolean };
    constructor(host: HTMLElement, base: string, nodes: any[], display: any, circuit = 'T1b', quality = { resolutionScale: 1, glow: true }) {
        this.circuit = circuit;
        this.quality = quality;
        this.nodes = nodes;
        this.display = display;
        this.lod = matchMedia('(pointer: coarse)').matches || innerWidth < 900 ? 'phone' : 'desktop';
        host.innerHTML = `<div class="segments" role="radiogroup" aria-label="Anatomy view"><label><input type="radio" name="brain-mode" value="brain" checked>Brain</label><label><input type="radio" name="brain-mode" value="whole"><span class="phone-hint">Whole CNS</span><span class="desktop-hint">Whole nervous system</span></label></div><div class="brain-image"><canvas aria-label="Recorded neural activity on MaleCNS anatomy"></canvas><canvas class="brain-labels" aria-hidden="true"></canvas><span class="brain-loading" role="status">Loading real neuron skeletons…</span></div><p class="anatomy-caption">${ANATOMY_CAPTION}</p>`;
        this.canvas = host.querySelector('canvas')!;
        host.querySelectorAll<HTMLInputElement>('input').forEach(input => input.name = `${host.id}-brain-mode`);
        this.overlay = host.querySelector('.brain-labels')!;
        this.gl = this.canvas.getContext('webgl2', { alpha: false, antialias: false, preserveDrawingBuffer: true });
        if (!this.gl)
            this.fallback = this.canvas.getContext('2d')!;
        host.querySelectorAll<HTMLInputElement>('input').forEach(input => input.onchange = () => { this.mode = input.value; this.lastTick = -1; host.classList.toggle('whole', this.mode === 'whole'); });
        void this.load(base).then(() => { host.querySelector('.brain-loading')!.remove(); this.ready = true; }).catch(e => { host.querySelector('.brain-loading')!.textContent = 'Anatomy unavailable: ' + String(e); });
    }
    private async load(base: string) {
        const start = performance.now();
        const root = base + 'data/anatomy/';
        const [manifest, rois] = await Promise.all([fetch(root + 'manifest.json').then(r => r.json()), fetch(root + 'neuropils.json').then(r => r.json()), document.fonts.load('600 24px Atkinson')]);
        this.rois = rois;
        const asset = manifest.assets.find((a: any) => a.circuit === this.circuit && a.lod === this.lod);
        const response = await fetch(root + asset.file);
        const buffer = await new Response(response.body!.pipeThrough(new DecompressionStream('gzip'))).arrayBuffer();
        this.anatomy = decodeArbors(buffer);
        if (this.anatomy.neurons.some((n, i) => String(n.bodyId) !== this.nodes[i].body_id))
            throw new Error('Anatomy / executed neuron order mismatch');
        if (this.gl)
            this.setupGL();
        this.loadMs = performance.now() - start;
    }
    private program(vertex: string, fragment: string) { const gl = this.gl!; const p = gl.createProgram()!; for (const [type, source] of [[gl.VERTEX_SHADER, vertex], [gl.FRAGMENT_SHADER, fragment]] as const) {
        const s = gl.createShader(type)!;
        gl.shaderSource(s, source);
        gl.compileShader(s);
        if (!gl.getShaderParameter(s, gl.COMPILE_STATUS))
            throw new Error(gl.getShaderInfoLog(s)!);
        gl.attachShader(p, s);
    } gl.linkProgram(p); if (!gl.getProgramParameter(p, gl.LINK_STATUS))
        throw new Error(gl.getProgramInfoLog(p)!); return p; }
    private setupGL() {
        const gl = this.gl!;
        this.lineProgram = this.program(`#version 300 es\nin vec2 p;in float neuron;in float panel;uniform bool brainOnly;uniform vec4 transform;uniform sampler2D activity;uniform float pointSize;out float a;void main(){a=brainOnly&&panel>.5?0.:texelFetch(activity,ivec2(int(neuron),0),0).r;gl_Position=a<.02?vec4(2,2,0,1):vec4(p*transform.xy+transform.zw,0,1);gl_PointSize=pointSize;}`, `#version 300 es\nprecision mediump float;in float a;uniform float glow;uniform bool dots;out vec4 color;void main(){float falloff=1.;if(dots){float d=length(gl_PointCoord-vec2(.5));if(d>.5)discard;falloff=1.-d*2.;}color=vec4(.388,.949,.604,a*glow*falloff);}`);
        this.texProgram = this.program(`#version 300 es\nin vec2 p;out vec2 uv;void main(){gl_Position=vec4(p,0,1);uv=vec2((p.x+1.)*.5,(1.-p.y)*.5);}`, `#version 300 es\nprecision mediump float;in vec2 uv;uniform sampler2D layer;out vec4 color;void main(){color=texture(layer,uv);}`);
        this.quad = gl.createBuffer()!;
        gl.bindBuffer(gl.ARRAY_BUFFER, this.quad);
        gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
        const vertices: number[] = [], somata: number[] = [];
        for (const [i, n] of this.anatomy.neurons.entries()) {
            const first = vertices.length / 4;
            if (this.nodes[i].group === 'interior') {
                if (n.soma)
                    somata.push(...n.soma, i, n.somaPanel);
                this.ranges.push([first, 0]);
                continue;
            }
            for (let j = n.firstSegment; j < n.firstSegment + n.segmentCount; j++) {
                const parent = this.anatomy.parents[j];
                if (parent >= 0 && !this.anatomy.bridges[j])
                    vertices.push(...this.anatomy.point(parent), i, this.anatomy.panels[parent], ...this.anatomy.point(j), i, this.anatomy.panels[j]);
            }
            this.ranges.push([first, vertices.length / 4 - first]);
        }
        this.lineCount = vertices.length / 4;
        this.somaCount = somata.length / 4;
        this.indexScratch = new Uint32Array(this.lineCount);
        this.activeIndices = gl.createBuffer()!;
        this.lines = gl.createBuffer()!;
        gl.bindBuffer(gl.ARRAY_BUFFER, this.lines);
        gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(vertices), gl.STATIC_DRAW);
        this.somaBuffer = gl.createBuffer()!;
        gl.bindBuffer(gl.ARRAY_BUFFER, this.somaBuffer);
        gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(somata), gl.STATIC_DRAW);
        this.activity = new Float32Array(this.nodes.length);
        this.activityTexture = gl.createTexture()!;
        gl.activeTexture(gl.TEXTURE1);
        gl.bindTexture(gl.TEXTURE_2D, this.activityTexture);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.R32F, this.nodes.length, 1, 0, gl.RED, gl.FLOAT, this.activity);
        gl.activeTexture(gl.TEXTURE0);
        this.texture = gl.createTexture()!;
        gl.bindTexture(gl.TEXTURE_2D, this.texture);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    }
    private point(p: number[]) { return [p[0] * this.scale + this.offset[0], p[1] * this.scale + this.offset[1]]; }
    private prepare() {
        const resolutionScale = this.gl ? this.quality.resolutionScale : 1;
        const width = 720, height = this.mode === 'brain' ? 424 : 1040;
        this.canvas.width = Math.round(width * resolutionScale);
        this.canvas.height = Math.round(height * resolutionScale);
        this.overlay.width = width;
        this.overlay.height = height;
        const contours = this.rois.rois.filter((r: any) => this.mode === 'whole' || r.panel === 0).flatMap((r: any) => r.contours_um).flat();
        this.bounds = [Math.min(...contours.map((p: number[]) => p[0])), Math.min(...contours.map((p: number[]) => p[1])), Math.max(...contours.map((p: number[]) => p[0])), Math.max(...contours.map((p: number[]) => p[1]))];
        const [x0, y0, x1, y1] = this.bounds;
        this.scale = Math.min((width - 48) / (x1 - x0), (height - 80) / (y1 - y0));
        this.offset = [(width - (x1 - x0) * this.scale) / 2 - x0 * this.scale, 46 - y0 * this.scale];
        let layer = this.staticLayers.get(this.mode);
        if (!layer) {
            layer = document.createElement('canvas');
            layer.width = width;
            layer.height = height;
            const c = layer.getContext('2d')!;
            c.fillStyle = '#000';
            c.fillRect(0, 0, width, height);
            c.fillStyle = '#c24fb82b';
            c.strokeStyle = '#c24fb828';
            c.lineWidth = 1;
            for (const roi of this.rois.rois) {
                if (this.mode === 'brain' && roi.panel !== 0)
                    continue;
                const path = new Path2D();
                for (const contour of roi.contours_um) {
                    contour.forEach((p: number[], i: number) => { const q = this.point(p); i ? path.lineTo(q[0], q[1]) : path.moveTo(q[0], q[1]); });
                    path.closePath();
                }
                c.shadowColor = '#c24fb8';
                c.shadowBlur = 7;
                c.fill(path, 'evenodd');
                c.shadowBlur = 0;
                c.strokeStyle = '#00000035';
                c.stroke(path);
            }
            // Deterministic fine grain, clipped to the actual tissue alpha mask.
            const pixels = c.getImageData(0, 0, width, height);
            for (let i = 0; i < pixels.data.length; i += 4) {
                if (pixels.data[i] > 0) {
                    const grain = ((Math.imul(i + 1, 2654435761) >>> 23) / 512 - .5) * 14;
                    for (let k = 0; k < 3; k++)
                        pixels.data[i + k] = Math.max(0, pixels.data[i + k] + grain);
                }
            }
            c.putImageData(pixels, 0, 0);
            const interior = new Path2D(), highlighted = new Path2D(), layout = new Path2D();
            for (let i = 0; i < this.anatomy.neurons.length; i++) {
                const n = this.anatomy.neurons[i];
                c.strokeStyle = this.nodes[i].group === 'interior' ? '#c9d0c812' : '#c9d0c83b';
                c.fillStyle = c.strokeStyle;
                c.lineWidth = .55;
                if (!this.gl) {
                    if (n.soma && (this.mode === 'whole' || n.somaPanel === 0)) {
                        const [x, y] = this.point(n.soma);
                        c.fillRect(x, y, 1.8, 1.8);
                    }
                    continue;
                }
                const path = new Path2D(), bridges = new Path2D();
                for (let j = n.firstSegment; j < n.firstSegment + n.segmentCount; j++) {
                    const parent = this.anatomy.parents[j];
                    if (parent < 0 || (this.mode === 'brain' && (this.anatomy.panels[j] !== 0 || this.anatomy.panels[parent] !== 0)))
                        continue;
                    const [x, y] = this.point(this.anatomy.point(j)), [px, py] = this.point(this.anatomy.point(parent));
                    const target = this.anatomy.bridges[j] ? bridges : path;
                    target.moveTo(px, py);
                    target.lineTo(x, y);
                }
                (this.nodes[i].group === 'interior' ? interior : highlighted).addPath(path);
                layout.addPath(bridges);
            }
            if (this.gl) {
                const ink = document.createElement('canvas');
                ink.width = width;
                ink.height = height;
                const g = ink.getContext('2d')!;
                g.strokeStyle = '#c9d0c8';
                g.lineWidth = .55;
                for (const [path, alpha] of [[interior, .07], [highlighted, .22], [layout, .04]] as const) {
                    g.clearRect(0, 0, width, height);
                    g.stroke(path);
                    c.globalAlpha = alpha;
                    c.drawImage(ink, 0, 0);
                }
                c.globalAlpha = 1;
            }
            this.staticLayers.set(this.mode, layer);
        }
        const c = this.overlay.getContext('2d')!;
        c.clearRect(0, 0, width, height);
        c.font = '600 24px Atkinson';
        c.fillStyle = '#c9d0c8';
        c.strokeStyle = '#000';
        c.lineWidth = 5;
        for (const [slot, group] of ['giant fiber', 'LC4', 'LPLC2'].entries()) {
            const ns = this.anatomy.neurons.filter((n, i) => this.nodes[i].group === group && n.soma && n.somaPanel === 0);
            if (!ns.length)
                continue;
            let anchor: number[];
            if (group === 'giant fiber')
                anchor = ns[0].soma!;
            else {
                const points: number[][] = [];
                for (const n of ns)
                    for (let j = n.firstSegment; j < n.firstSegment + n.segmentCount; j++)
                        if (this.anatomy.panels[j] === 0)
                            points.push(this.anatomy.point(j));
                anchor = [points.reduce((s, p) => s + p[0], 0) / points.length, points.reduce((s, p) => s + p[1], 0) / points.length];
            }
            const x = 24 + slot * 245, y = 25, label = group === 'giant fiber' ? 'Escape neuron' : group;
            const q = this.point(anchor);
            c.strokeText(label, x, y);
            c.fillText(label, x, y);
            c.strokeStyle = '#9ba59c';
            c.lineWidth = .6;
            c.beginPath();
            c.moveTo(x + 30, y + 8);
            c.lineTo(q[0], q[1]);
            c.stroke();
            c.strokeStyle = '#000';
            c.lineWidth = 5;
        }
        const bar = this.display.anatomy_scale_bar_um * this.scale;
        c.fillRect(width - 24 - bar, height - 22, bar, 2);
        c.font = '24px Atkinson';
        c.fillText(`${this.display.anatomy_scale_bar_um} µm`, width - 24 - bar, height - 30);
        if (this.gl) {
            const gl = this.gl;
            gl.bindTexture(gl.TEXTURE_2D, this.texture);
            gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, layer);
        }
    }
    draw(frame: Frame, frames: Frame[], dim = false) {
        if (!this.ready)
            return;
        if (this.lastTick === frame.tick && this.lastMode === this.mode)
            return;
        this.shownFrame=frame;this.shownFrames=frames;this.shownDim=dim;
        if (this.lastMode !== this.mode)
            this.prepare();
        this.lastTick = frame.tick;
        this.lastMode = this.mode;
        const last = new Map<number, number>();
        const cutoff = frame.tick + 2 * this.display.spike_decay_tau_ms * Math.log(this.display.spike_alpha_threshold);
        for (const f of frames)
            if (f.tick >= cutoff && f.tick <= frame.tick)
                for (const e of f.spikes)
                    if (e.tick <= frame.tick)
                        for (const i of e.indices)
                            last.set(i, e.tick);
        const gl = this.gl;
        if (gl) {
            gl.viewport(0, 0, this.canvas.width, this.canvas.height);
            gl.disable(gl.BLEND);
            const neuronLoc = gl.getAttribLocation(this.lineProgram, 'neuron');
            gl.disableVertexAttribArray(neuronLoc);
            gl.disableVertexAttribArray(gl.getAttribLocation(this.lineProgram, 'panel'));
            gl.useProgram(this.texProgram);
            gl.bindBuffer(gl.ARRAY_BUFFER, this.quad);
            let loc = gl.getAttribLocation(this.texProgram, 'p');
            gl.enableVertexAttribArray(loc);
            gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
            gl.bindTexture(gl.TEXTURE_2D, this.texture);
            gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
            this.activity.fill(0);
            for (const [i, tick] of last)
                this.activity[i] = spikeAlpha(frame.tick, tick, this.display.spike_decay_tau_ms) * (dim ? .45 : 1);
            gl.activeTexture(gl.TEXTURE1);
            gl.bindTexture(gl.TEXTURE_2D, this.activityTexture);
            gl.texSubImage2D(gl.TEXTURE_2D, 0, 0, 0, this.nodes.length, 1, gl.RED, gl.FLOAT, this.activity);
            gl.activeTexture(gl.TEXTURE0);
            gl.useProgram(this.lineProgram);
            gl.uniform1i(gl.getUniformLocation(this.lineProgram, 'activity'), 1);
            gl.uniform1i(gl.getUniformLocation(this.lineProgram, 'brainOnly'), this.mode === 'brain' ? 1 : 0);
            gl.uniform4f(gl.getUniformLocation(this.lineProgram, 'transform'), 2 * this.scale / this.overlay.width, -2 * this.scale / this.overlay.height, 2 * this.offset[0] / this.overlay.width - 1, 1 - 2 * this.offset[1] / this.overlay.height);
            gl.enable(gl.BLEND);
            const bind = (buffer: WebGLBuffer) => { gl.bindBuffer(gl.ARRAY_BUFFER, buffer); const p = gl.getAttribLocation(this.lineProgram, 'p'), n = gl.getAttribLocation(this.lineProgram, 'neuron'); gl.enableVertexAttribArray(p); gl.vertexAttribPointer(p, 2, gl.FLOAT, false, 16, 0); gl.enableVertexAttribArray(n); gl.vertexAttribPointer(n, 1, gl.FLOAT, false, 16, 8); const panel = gl.getAttribLocation(this.lineProgram, 'panel'); gl.enableVertexAttribArray(panel); gl.vertexAttribPointer(panel, 1, gl.FLOAT, false, 16, 12); };
            bind(this.lines);
            gl.uniform1i(gl.getUniformLocation(this.lineProgram, 'dots'), 0);
            gl.uniform1f(gl.getUniformLocation(this.lineProgram, 'glow'), 1);
            gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
            let count = 0;
            for (const [i] of last) {
                if (this.activity[i] < this.display.spike_alpha_threshold)
                    continue;
                const [first, length] = this.ranges[i];
                for (let j = first; j < first + length; j++)
                    this.indexScratch[count++] = j;
            }
            gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, this.activeIndices);
            gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, this.indexScratch.subarray(0, count), gl.STREAM_DRAW);
            gl.drawElements(gl.LINES, count, gl.UNSIGNED_INT, 0);
            bind(this.somaBuffer);
            gl.uniform1i(gl.getUniformLocation(this.lineProgram, 'dots'), 1);
            if (this.quality.glow) {
            gl.uniform1f(gl.getUniformLocation(this.lineProgram, 'pointSize'), 7);
            gl.uniform1f(gl.getUniformLocation(this.lineProgram, 'glow'), .25);
            gl.blendFunc(gl.SRC_ALPHA, gl.ONE);
            gl.drawArrays(gl.POINTS, 0, this.somaCount);
            }
            gl.uniform1f(gl.getUniformLocation(this.lineProgram, 'pointSize'), 3);
            gl.uniform1f(gl.getUniformLocation(this.lineProgram, 'glow'), 1);
            gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
            gl.drawArrays(gl.POINTS, 0, this.somaCount);
        }
        else {
            const c = this.fallback!;
            c.drawImage(this.staticLayers.get(this.mode)!, 0, 0);
            c.globalCompositeOperation = 'lighter';
            for (const [i, tick] of last) {
                const n = this.anatomy.neurons[i];
                if (!n?.soma || (this.mode === 'brain' && n.somaPanel !== 0))
                    continue;
                const a = spikeAlpha(frame.tick, tick, this.display.spike_decay_tau_ms);
                if (a < this.display.spike_alpha_threshold)
                    continue;
                const [x, y] = this.point(n.soma);
                c.globalAlpha = a * (dim ? .45 : 1);
                c.fillStyle = '#63f29a';
                c.shadowColor = '#63f29a';
                c.shadowBlur = 5;
                c.beginPath();
                c.arc(x, y, 2, 0, Math.PI * 2);
                c.fill();
            }
            c.shadowBlur = 0;
            c.globalAlpha = 1;
            c.globalCompositeOperation = 'source-over';
        }
    }
    snapshotAt(frame: Frame, frames: Frame[], mode = 'brain') {
        const previous = { frame: this.shownFrame, frames: this.shownFrames, dim: this.shownDim, mode: this.mode };
        this.mode = mode; this.lastTick = -1; this.draw(frame, frames);
        const snapshot = this.snapshot();
        this.mode = previous.mode; this.lastTick = -1;
        if (previous.frame) this.draw(previous.frame, previous.frames, previous.dim);
        return snapshot;
    }
    snapshot() { const c = document.createElement('canvas'); c.width = this.canvas.width; c.height = this.canvas.height; const g = c.getContext('2d')!; g.drawImage(this.canvas, 0, 0); g.drawImage(this.overlay, 0, 0, c.width, c.height); return c; }
    get renderer() { return this.gl ? 'WebGL2' : 'Canvas soma fallback'; }
}
