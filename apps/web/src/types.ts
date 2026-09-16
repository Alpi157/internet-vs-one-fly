export type Point = { x: number; y: number };

export type StrikeState = {
  attack_id: string;
  locked_target: Point;
  commit_tick: number;
  stimulus_tick: number;
  impact_tick: number;
  phase: "wind-up" | "approach";
  progress: number;
};

export type ImpactState = {
  attack_id: string;
  control_tick: number;
  locked_target: Point;
  authoritative_fly_position: Point;
  distance: number;
  strike_radius: number;
  outcome: "caught" | "missed";
};

export type GameState = {
  type: "state";
  server_tick: number;
  logical_time_ms: number;
  round_remaining_ms: number;
  phase: "ready" | "wind-up" | "approach" | "cooldown" | "complete";
  aim: Point | null;
  strike: StrikeState | null;
  cooldown_remaining_ms: number;
  attacks_used: number;
  attempts_remaining: number;
  fly: {
    x: number;
    y: number;
    heading_rad: number;
    takeoff_started: boolean;
    takeoff_active: boolean;
  };
  last_impact: ImpactState | null;
  result: "caught" | "fly-survived" | null;
  result_reason: string | null;
  backend: "kernel";
  model: { N: number; E: number; represented_contacts: number };
};

export type ServerMessage =
  | GameState
  | {
      type: "ack";
      kind: "aim" | "attack";
      sequence: number;
      server_tick: number;
      attack_id?: string;
      locked_target?: Point;
      impact_tick?: number;
    }
  | { type: "error"; code: string; message: string; server_tick?: number };
