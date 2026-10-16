import { Game } from './game.ts';
let game: Game | null = null, paused = true, timer: any = null, manual = false;
let wall = 0, steps = 0;
function snapshot(frame: any) { return { kind: 'frame', frame, looming: game!.looming, tick: game!.tick, catches: game!.catches, strikes: game!.strikes, done: game!.done, simulation_wall_s_per_sim_s: wall / (steps * .01) }; }
function step() {
    if (!game || paused || game.done)
        return;
    const prior = game.strike;
    const start = performance.now();
    const frame = game.step();
    wall += (performance.now() - start) / 1000;
    steps++;
    self.postMessage(snapshot(frame));
    if (prior && !game.strike) {
        paused = true;
        self.postMessage({ kind: 'replay', frames: game.replayFrames(), impact: game.lastImpact, done: game.done });
    }
    if (game.done)
        paused = true;
}
self.onmessage = async (event) => {
    const message = event.data;
    try {
        if (message.kind === 'init') {
            clearInterval(timer);
            game = new Game(message.buffer, message.runtime, message.profile, message.neuralSeed, message.environmentSeed);
            manual = !!message.manual;
            paused = true;
            wall = 0;
            steps = 0;
            if (!manual)
                timer = setInterval(step, 10);
            self.postMessage({ kind: 'ready', tick: 0, body: game.runner.body });
        }
        else if (message.kind === 'pause') { paused = true; }
        else if (message.kind === 'start' || message.kind === 'resume') {
            paused = false;
        }
        else if (message.kind === 'strike' && game && !paused) {
            game.apply({ tick: game.tick, x: message.x, y: message.y, hold_ms: message.hold_ms });
        }
        else if (message.kind === 'advance' && manual) {
            for (let i = 0; i < message.intervals; i++)
                step();
            self.postMessage({ kind: 'advanced', id: message.id });
        }
        else if (message.kind === 'log' && game) {
            self.postMessage({ kind: 'log', id: message.id, log: await game.log() });
        }
    }
    catch (error) {
        self.postMessage({ kind: 'error', error: String(error) });
    }
};
