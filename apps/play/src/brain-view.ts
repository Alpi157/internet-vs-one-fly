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
    private allIndices = new Uint32Array(0);
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
    private mirrorRaster?: HTMLVideoElement | HTMLCanvasElement;
    private capture?: MediaStream;
    private mirrorDest=[0,0,0,0];
    private mirroring=false;
    private mirrorKey='';
    private mirrorTick=-1;
    private presentedMirrorFrames=0;
    private mirrorCallback=0;
    private mirrorStarted=0;
    private mirrorLastCall=0;
    private mirrorUnavailable=false;
    private panelBounds: number[][] = [];
    private panelOffsets: number[][] = [[0,0],[0,0]];
    private layoutKey = '';
    private landscape = false;
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
        host.innerHTML = `<div class="anatomy-toolbar"><div class="segments" role="radiogroup" aria-label="Anatomy view"><label><input type="radio" name="brain-mode" value="brain" checked>Brain</label><label><input type="radio" name="brain-mode" value="whole"><span class="phone-hint">Whole CNS</span><span class="desktop-hint">Whole nervous system</span></label></div><button class="brain-expand icon" aria-label="Expand anatomy">⛶</button></div><div class="brain-image"><canvas aria-label="Recorded neural activity on MaleCNS anatomy"></canvas><canvas class="brain-labels" aria-hidden="true"></canvas><span class="brain-loading" role="status">Loading real neuron skeletons…</span></div><p class="anatomy-caption">${ANATOMY_CAPTION}</p>`;
        this.canvas = host.querySelector('canvas')!;
        host.querySelectorAll<HTMLInputElement>('input').forEach(input => input.name = `${host.id}-brain-mode`);
        this.overlay = host.querySelector('.brain-labels')!;
        this.gl = this.canvas.getContext('webgl2', { alpha: false, antialias: false, preserveDrawingBuffer: true });
        if (!this.gl)
            this.fallback = this.canvas.getContext('2d')!;
        host.querySelectorAll<HTMLInputElement>('input').forEach(input => input.onchange = () => { this.mode = input.value; this.lastTick = -1; host.classList.toggle('whole', this.mode === 'whole'); });
        const expand=host.querySelector<HTMLButtonElement>('.brain-expand')!;
        expand.onclick=()=>{
            const dialog=document.createElement('dialog');dialog.className='brain-fullscreen';dialog.setAttribute('aria-label','Expanded nervous system');
            const close=document.createElement('button');close.className='brain-collapse';close.textContent='Close expanded view';
            const container=document.createElement('div');container.className='expanded-brain';container.classList.toggle('whole',this.mode==='whole');
            const children=Array.from(host.childNodes);container.append(...children);dialog.append(close,container);document.body.append(dialog);expand.hidden=true;
            dialog.onclose=()=>{dialog.remove();requestAnimationFrame(()=>expand.focus());};
            const finish=()=>{host.append(...children);expand.hidden=false;dialog.close();this.lastTick=-1;};
            close.onclick=finish;dialog.oncancel=e=>{e.preventDefault();finish();};
            dialog.onkeydown=e=>{if(e.key!=='Tab')return;const nodes=Array.from(dialog.querySelectorAll<HTMLElement>('button,input')).filter(e=>e.checkVisibility());if(e.shiftKey&&document.activeElement===nodes[0]){e.preventDefault();nodes.at(-1)?.focus();}else if(!e.shiftKey&&document.activeElement===nodes.at(-1)){e.preventDefault();nodes[0].focus();}};
            dialog.showModal();close.focus();this.lastTick=-1;
        };
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
        this.panelBounds=[[Infinity,Infinity,-Infinity,-Infinity],[Infinity,Infinity,-Infinity,-Infinity]];
        for(let i=0;i<this.anatomy.parents.length;i++){const p=this.anatomy.point(i),b=this.panelBounds[this.anatomy.panels[i]];b[0]=Math.min(b[0],p[0]);b[1]=Math.min(b[1],p[1]);b[2]=Math.max(b[2],p[0]);b[3]=Math.max(b[3],p[1]);}
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
        this.lineProgram = this.program(`#version 300 es\nin vec2 p;in float neuron;in float panel;uniform bool brainOnly;uniform vec4 transform;uniform vec2 cordOffset;uniform sampler2D activity;uniform float pointSize;out float a;void main(){a=brainOnly&&panel>.5?0.:texelFetch(activity,ivec2(int(neuron),0),0).r;gl_Position=a<.02?vec4(2,2,0,1):vec4((p+(panel>.5?cordOffset:vec2(0)))*transform.xy+transform.zw,0,1);gl_PointSize=pointSize;}`, `#version 300 es\nprecision mediump float;in float a;uniform float glow;uniform bool dots;out vec4 color;void main(){float falloff=1.;if(dots){float d=length(gl_PointCoord-vec2(.5));if(d>.5)discard;falloff=1.-d*2.;}color=vec4(.388,.949,.604,a*glow*falloff);}`);
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
        this.allIndices = Uint32Array.from({length:this.lineCount},(_,i)=>i);
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
    private point(p: number[], panel=0) { const d=this.panelOffsets[panel];return [(p[0]+d[0])*this.scale+this.offset[0],(p[1]+d[1])*this.scale+this.offset[1]]; }
    private prepare() {
        const resolutionScale = this.gl ? this.quality.resolutionScale : 1;
        const box=this.canvas.parentElement!.getBoundingClientRect();
        const width=720,height=Math.max(180,Math.round(720*box.height/Math.max(1,box.width)));
        this.landscape=this.mode==='whole'&&box.width>box.height;
        this.canvas.width=Math.round(width*resolutionScale);this.canvas.height=Math.round(height*resolutionScale);
        this.overlay.width=width;this.overlay.height=height;
        const points=(panel:number)=>this.rois.rois.filter((r:any)=>r.panel===panel).flatMap((r:any)=>r.contours_um).flat();
        const bounds=(points:number[][])=>[Math.min(...points.map(p=>p[0])),Math.min(...points.map(p=>p[1])),Math.max(...points.map(p=>p[0])),Math.max(...points.map(p=>p[1]))];
        const union=(i:number)=>{const a=bounds(points(i)),b=this.panelBounds[i];return [Math.min(a[0],b[0]),Math.min(a[1],b[1]),Math.max(a[2],b[2]),Math.max(a[3],b[3])];};
        const b=union(0),cord=union(1);
        this.panelOffsets=[[0,0],this.landscape?[b[2]+50-cord[0],b[1]-cord[1]]:[0,0]];
        const contours=this.rois.rois.filter((r:any)=>this.mode==='whole'||r.panel===0).flatMap((r:any)=>r.contours_um.flat().map((p:number[])=>[p[0]+this.panelOffsets[r.panel][0],p[1]+this.panelOffsets[r.panel][1]]));
        const extra=[b, ...(this.mode==='whole'?[cord]:[])].flatMap((b,i)=>[[b[0]+this.panelOffsets[i][0],b[1]+this.panelOffsets[i][1]],[b[2]+this.panelOffsets[i][0],b[3]+this.panelOffsets[i][1]]]);
        this.bounds=bounds([...contours,...extra]);const [x0,y0,x1,y1]=this.bounds;
        const font=14*width/Math.max(1,box.width),narrow=box.width<330,top=font*(narrow?5.6:2.8),bottom=font*2.5;
        this.scale=Math.min((width-48)/(x1-x0),(height-top-bottom)/(y1-y0));
        this.offset=[(width-(x1-x0)*this.scale)/2-x0*this.scale,top+(height-top-bottom-(y1-y0)*this.scale)/2-y0*this.scale];
        this.layoutKey=`${this.mode}:${width}:${height}:${Math.round(box.width)}`;
        const caption=this.canvas.parentElement!.parentElement!.querySelector('.anatomy-caption');
        if(caption)caption.textContent=this.landscape?'Brain: front view. Nerve cord: underside view. Placed side by side for display.':ANATOMY_CAPTION;
        let layer = this.staticLayers.get(this.layoutKey);
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
                    contour.forEach((p: number[], i: number) => { const q = this.point(p,roi.panel); i ? path.lineTo(q[0], q[1]) : path.moveTo(q[0], q[1]); });
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
                        const [x, y] = this.point(n.soma,n.somaPanel);
                        c.fillRect(x, y, 1.8, 1.8);
                    }
                    continue;
                }
                const path = new Path2D(), bridges = new Path2D();
                for (let j = n.firstSegment; j < n.firstSegment + n.segmentCount; j++) {
                    const parent = this.anatomy.parents[j];
                    if (parent < 0 || (this.mode === 'brain' && (this.anatomy.panels[j] !== 0 || this.anatomy.panels[parent] !== 0)))
                        continue;
                    const [x, y] = this.point(this.anatomy.point(j),this.anatomy.panels[j]), [px, py] = this.point(this.anatomy.point(parent),this.anatomy.panels[parent]);
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
            this.staticLayers.clear();this.staticLayers.set(this.layoutKey, layer);
        }
        this.drawLabels(width,height,font,narrow,cord);
        if (this.gl) {
            const gl = this.gl;
            gl.bindTexture(gl.TEXTURE_2D, this.texture);
            gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, layer);
        }
    }
    private drawLabels(width:number,height:number,font:number,narrow:boolean,cord:number[]){
        const c = this.overlay.getContext('2d')!;
        c.clearRect(0, 0, width, height);
        c.font = `600 ${font}px Atkinson`;
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
            const x = narrow?18:18 + slot * (width-36)/3, y = font*(1.25+(narrow?slot*1.4:0)), label = group === 'giant fiber' ? 'Escape neuron' : group;
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
        if(this.mode==='whole'){const q=this.point([(cord[0]+cord[2])/2,cord[3]],1);c.textAlign='center';c.fillText('Nerve cord',q[0],Math.min(height-font*2.3,q[1]+font*1.4));c.textAlign='left';}
        const bar = this.display.anatomy_scale_bar_um * this.scale;
        c.fillRect(width - 24 - bar, height - font*.8, bar, 2);
        c.font = `${font}px Atkinson`;
        c.textAlign='right';c.fillText(`${this.display.anatomy_scale_bar_um} µm`, width - 24, height - font*1.3);c.textAlign='left';
    }
    /** Two views of the same lab recording may share rasterized anatomy/activity.
     * Each box retains its own fixed-size labels and display transform. */
    mirrorFrom(source:BrainView,frame:Frame,frames:Frame[]){
        const box=this.canvas.parentElement!.getBoundingClientRect(),other=source.canvas.parentElement!.getBoundingClientRect();
        if(!this.ready||!source.ready||this.mode!==source.mode||box.width<330||other.width<330||(this.mode==='whole'&&(box.width>box.height)!==(other.width>other.height))){this.draw(frame,frames);return;}
        // WebKit's GPU canvas readback stalls the compositor; its local stream is faster.
        // Chromium and Firefox use a synchronous copy, which avoids stream encoding overhead.
        const streaming=navigator.vendor==='Apple Computer, Inc.'&&'captureStream' in source.canvas;
        if(streaming&&this.mirrorUnavailable){this.draw(frame,frames);return;}
        const now=performance.now();
        if(!this.mirroring||now-this.mirrorLastCall>250)this.mirrorStarted=now;
        this.mirrorLastCall=now;
        if(streaming&&this.mirrorRaster&&performance.now()-this.mirrorStarted>5000){this.mirrorUnavailable=true;this.draw(frame,frames);return;}
        if(!this.mirrorRaster){
            this.mirrorStarted=performance.now();
            this.mirrorRaster=document.createElement(streaming?'video':'canvas');this.mirrorRaster.className='brain-mirror';this.mirrorRaster.setAttribute('aria-hidden','true');
            this.mirrorRaster.style.cssText='position:absolute;inset:0;width:100%;height:100%;object-fit:contain;pointer-events:none';this.overlay.before(this.mirrorRaster);
            if(this.mirrorRaster instanceof HTMLVideoElement){
                const video=this.mirrorRaster;video.muted=true;video.autoplay=true;video.playsInline=true;
                source.capture??=source.canvas.captureStream(0);video.srcObject=source.capture;void video.play();
                const presented=()=>{this.presentedMirrorFrames++;this.mirrorStarted=performance.now();this.mirrorCallback=video.requestVideoFrameCallback(presented);};
                this.mirrorCallback=video.requestVideoFrameCallback(presented);
            }
        }
        this.canvas.style.opacity='0';this.mirrorRaster.hidden=false;this.mirroring=true;
        const width=720,height=Math.max(180,Math.round(720*box.height/box.width)),key=`${source.layoutKey}:${width}:${height}:${box.width}`;
        const k=Math.min(width/source.overlay.width,height/source.overlay.height),x=(width-source.overlay.width*k)/2,y=(height-source.overlay.height*k)/2;
        if(key!==this.mirrorKey){
            this.overlay.width=width;this.overlay.height=height;this.mirrorDest=[x,y,source.overlay.width*k,source.overlay.height*k];
            this.scale=source.scale*k;this.offset=[source.offset[0]*k+x,source.offset[1]*k+y];this.panelOffsets=source.panelOffsets.map(v=>v.slice());this.landscape=source.landscape;
            this.drawLabels(width,height,14*width/box.width,false,this.panelBounds[1]);this.mirrorKey=key;
            const caption=this.canvas.parentElement!.parentElement!.querySelector('.anatomy-caption');if(caption)caption.textContent=this.landscape?'Brain: front view. Nerve cord: underside view. Placed side by side for display.':ANATOMY_CAPTION;
            this.mirrorTick=-1;
        }
        if(this.mirrorTick!==frame.tick||this.shownFrame!==frame){
            if(this.mirrorRaster instanceof HTMLCanvasElement){
                if(this.mirrorRaster.width!==source.canvas.width||this.mirrorRaster.height!==source.canvas.height){this.mirrorRaster.width=source.canvas.width;this.mirrorRaster.height=source.canvas.height;}
                this.mirrorRaster.getContext('2d')!.drawImage(source.canvas,0,0);this.presentedMirrorFrames++;
            }else (source.capture!.getVideoTracks()[0] as CanvasCaptureMediaStreamTrack).requestFrame();
            this.mirrorTick=frame.tick;
        }
        this.shownFrame=frame;this.shownFrames=frames;this.shownDim=false;
    }
    draw(frame: Frame, frames: Frame[], dim = false) {
        if(this.mirroring){this.mirroring=false;this.canvas.style.opacity='';this.mirrorRaster!.hidden=true;this.mirrorKey='';this.lastMode='';this.lastTick=-1;}
        if (!this.ready)
            return;
        const box=this.canvas.parentElement!.getBoundingClientRect();
        if(box.width<1||box.height<1)return;
        const key=`${this.mode}:720:${Math.max(180,Math.round(720*box.height/box.width))}:${Math.round(box.width)}`;
        if (this.shownFrame===frame && this.lastTick === frame.tick && this.lastMode === this.mode && this.layoutKey===key && this.shownDim===dim)
            return;
        this.shownFrame=frame;this.shownFrames=frames;this.shownDim=dim;
        if (this.lastMode !== this.mode || this.layoutKey!==key)
            this.prepare();
        this.lastTick = frame.tick;
        this.lastMode = this.mode;
        const last=this.recordedLast(frame,frames);
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
            gl.uniform2f(gl.getUniformLocation(this.lineProgram,'cordOffset'),...this.panelOffsets[1] as [number,number]);
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
                if(length){this.indexScratch.set(this.allIndices.subarray(first,first+length),count);count+=length;}
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
            c.drawImage(this.staticLayers.get(this.layoutKey)!, 0, 0);
            c.globalCompositeOperation = 'lighter';
            for (const [i, tick] of last) {
                const n = this.anatomy.neurons[i];
                if (!n?.soma || (this.mode === 'brain' && n.somaPanel !== 0))
                    continue;
                const a = spikeAlpha(frame.tick, tick, this.display.spike_decay_tau_ms);
                if (a < this.display.spike_alpha_threshold)
                    continue;
                const [x, y] = this.point(n.soma,n.somaPanel);
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
    private recordedLast(frame:Frame,frames:Frame[]){
        const ticks=new Float64Array(this.nodes.length);ticks.fill(-1);
        const cutoff=frame.tick+2*this.display.spike_decay_tau_ms*Math.log(this.display.spike_alpha_threshold);
        for(const f of frames)if(f.tick>=cutoff&&f.tick<=frame.tick)for(const e of f.spikes)if(e.tick<=frame.tick)for(const i of e.indices)if(e.tick>ticks[i])ticks[i]=e.tick;
        const last=new Map<number,number>();for(let i=0;i<ticks.length;i++)if(ticks[i]>=0)last.set(i,ticks[i]);
        return last;
    }
    activityAt(frame:Frame,frames:Frame[]){return [...this.recordedLast(frame,frames)].sort((a,b)=>a[0]-b[0]).map(([i,tick])=>[i,spikeAlpha(frame.tick,tick,this.display.spike_decay_tau_ms)]);}
    snapshotAt(frame: Frame, frames: Frame[], mode = 'brain') {
        const previous = { frame: this.shownFrame, frames: this.shownFrames, dim: this.shownDim, mode: this.mode };
        this.mode = mode; this.lastTick = -1; this.draw(frame, frames);
        const snapshot = this.snapshot();
        this.mode = previous.mode; this.lastTick = -1;
        if (previous.frame) this.draw(previous.frame, previous.frames, previous.dim);
        return snapshot;
    }
    snapshot() { const source=this.mirroring?this.mirrorRaster!:this.canvas;const c = document.createElement('canvas'); c.width = this.mirroring?this.overlay.width:this.canvas.width; c.height = this.mirroring?this.overlay.height:this.canvas.height; const g = c.getContext('2d')!; if(this.mirroring)g.drawImage(source,...this.mirrorDest as [number,number,number,number]);else g.drawImage(source, 0, 0); g.drawImage(this.overlay, 0, 0, c.width, c.height); return c; }
    get mirrorStatus(){const box=this.canvas.parentElement!.getBoundingClientRect();return {active:this.mirroring,visible:box.bottom>0&&box.top<innerHeight&&this.canvas.parentElement!.checkVisibility(),ready:this.mirrorRaster instanceof HTMLVideoElement?this.mirrorRaster.readyState:this.mirrorRaster?4:0,frames:this.presentedMirrorFrames};}
    dispose(){this.capture?.getTracks().forEach(t=>t.stop());if(this.mirrorRaster instanceof HTMLVideoElement){this.mirrorRaster.cancelVideoFrameCallback(this.mirrorCallback);this.mirrorRaster.pause();this.mirrorRaster.srcObject=null;}}
    get renderer() { return this.gl ? 'WebGL2' : 'Canvas soma fallback'; }
}
