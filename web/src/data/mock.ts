// Mock data copied from the target comp. Replace with API calls in phase 2.

export type SceneKind = "straight" | "cutin" | "cutout" | "lead" | "curve";
export type FactStatus = "ok" | "warn" | "bad";
export type Match = "Direct reuse" | "Modify and reuse" | "Not reusable";
export type Cost = "Low" | "Medium" | "High";

export interface Scene {
  id: number;
  title: string;
  req: string;
  desc: string;
  pages: string;
  p0: number;
  count: number;
  kind: SceneKind;
  query: string;
  sec: string;
  text: string;
  fig: string;
}

export interface Candidate {
  key: string;
  xosc: string;
  xodr: string;
  desc: string;
  sem: number;
  scen: number;
  road: number;
  cost: Cost;
  match: Match;
  conf: number;
  ver: string;
  dur: string;
  rationale: string;
  facts: [string, FactStatus][];
}

export const DOCUMENT = {
  name: "Euro NCAP 2025 – Lane Support Systems.pdf",
  version: "1.0",
  size: "3.2 MB",
  pages: 156,
};

export const SCENES: Scene[] = [
  { id: 1, title: "Straight lane keeping", req: "LSS-1.1.1", desc: "Vehicle maintains lane in straight on highway",
    pages: "8 – 10", p0: 8, count: 1, kind: "straight", query: "lane keeping straight highway",
    sec: "1.1.1 Straight lane keeping", fig: "Lane keeping scenario (example)",
    text: "The vehicle travels on a straight highway section. The system shall keep the vehicle within the lane boundaries without driver steering input for the full duration of the test." },
  { id: 2, title: "Cut-in from adjacent lane", req: "LSS-2.1.1", desc: "Vehicle cut-in from adjacent lane with gradual lateral movement",
    pages: "14 – 16", p0: 14, count: 2, kind: "cutin", query: "cut in lane support",
    sec: "2.1.1 Cut-in from adjacent lane", fig: "Cut-in scenario (example)",
    text: "A vehicle from the adjacent lane performs a cut-in manoeuvre into the ego lane. The system shall detect the cut-in and provide appropriate response to maintain safety and lane support functionality." },
  { id: 3, title: "Cut-out / lead vehicle leaves", req: "LSS-2.2.1", desc: "Lead vehicle cuts out, ego continues",
    pages: "17 – 19", p0: 17, count: 1, kind: "cutout", query: "cut out lead vehicle",
    sec: "2.2.1 Cut-out of lead vehicle", fig: "Cut-out scenario (example)",
    text: "The lead vehicle changes into the adjacent lane. The ego vehicle continues in its lane and the system shall maintain lane support without unnecessary intervention." },
  { id: 4, title: "Close lead vehicle", req: "LSS-3.1.1", desc: "Low speed lead vehicle",
    pages: "24 – 26", p0: 24, count: 1, kind: "lead", query: "close low speed lead vehicle",
    sec: "3.1.1 Close lead vehicle", fig: "Close lead vehicle scenario (example)",
    text: "A slower lead vehicle travels in the ego lane at short time gap. The system shall keep lane support active while the longitudinal controller adapts speed." },
  { id: 5, title: "Curved road", req: "LSS-4.1.1", desc: "Lane support on gentle curve",
    pages: "32 – 35", p0: 32, count: 1, kind: "curve", query: "lane support curve",
    sec: "4.1.1 Lane support on gentle curve", fig: "Curve scenario (example)",
    text: "The ego vehicle travels on a curve with constant radius. The system shall keep the vehicle centred within the lane through the curve." },
];

export const REQ_FACTS = [
  "Adjacent vehicle cut-in",
  "Highway motorway road",
  "Gradual lateral movement",
  "Constant speed",
  "Ego maintains lane",
];

export interface RoadInfo { length: string; lanes: string; type: string; lanesEach: number; rural: boolean }

export const ROADS: Record<string, RoadInfo> = {
  "e6mini.xodr": { length: "3.2 km", lanes: "3 (each direction)", type: "Highway (motorway)", lanesEach: 3, rural: false },
  "highway_straight.xodr": { length: "5.0 km", lanes: "3 (each direction)", type: "Highway (motorway)", lanesEach: 3, rural: false },
  "rural_2lane.xodr": { length: "2.4 km", lanes: "1 (each direction)", type: "Rural road", lanesEach: 1, rural: true },
};

const c = (o: Omit<Candidate, "key">): Candidate => ({ key: o.xosc, ...o });

export const CANDIDATES: Candidate[] = [
  c({ xosc: "cutin_left_01.xosc", xodr: "e6mini.xodr", desc: "Adjacent vehicle cuts in (left to right)",
    sem: .92, scen: .88, road: .85, cost: "Low", match: "Direct reuse", conf: .90, ver: "1.3", dur: "12 s",
    rationale: "High semantic and scenario similarity, same road topology (e6mini).",
    facts: [["Cut-in from left lane", "ok"], ["e6mini (3 lanes each direction)", "ok"], ["Lateral offset 3.5 m over 3 s", "ok"],
      ["Relative speed 0 ± 3 km/h", "ok"], ["Ego keeps lane, no lane change", "ok"]] }),
  c({ xosc: "cutin_left_02.xosc", xodr: "e6mini.xodr", desc: "Gradual cut-in with constant speed",
    sem: .87, scen: .82, road: .80, cost: "Low", match: "Direct reuse", conf: .86, ver: "1.1", dur: "15 s",
    rationale: "High semantic and scenario similarity, same road topology (e6mini).",
    facts: [["Cut-in from left lane", "ok"], ["e6mini (3 lanes each direction)", "ok"], ["Lateral offset 3.5 m over 4 s", "ok"],
      ["Relative speed 0 ± 2 km/h", "ok"], ["Ego keeps lane, no lane change", "ok"]] }),
  c({ xosc: "cutin_right_01.xosc", xodr: "e6mini.xodr", desc: "Adjacent vehicle cuts in (right to left)",
    sem: .83, scen: .78, road: .78, cost: "Medium", match: "Modify and reuse", conf: .74, ver: "1.0", dur: "14 s",
    rationale: "Cut-in direction is mirrored; flip the lateral offset sign to reuse.",
    facts: [["Cut-in from right lane", "warn"], ["e6mini (3 lanes each direction)", "ok"], ["Lateral offset 3.5 m over 4 s", "ok"],
      ["Relative speed 0 ± 2 km/h", "ok"], ["Ego keeps lane, no lane change", "ok"]] }),
  c({ xosc: "cutin_left_03.xosc", xodr: "highway_straight.xodr", desc: "Cut-in with braking ego reaction",
    sem: .80, scen: .76, road: .65, cost: "Medium", match: "Modify and reuse", conf: .71, ver: "2.0", dur: "18 s",
    rationale: "Remove the ego braking event; road topology is equivalent.",
    facts: [["Cut-in from left lane", "ok"], ["highway_straight (3 lanes each direction)", "ok"], ["Lateral offset 3.5 m over 3.5 s", "ok"],
      ["Ego brakes −4 m/s² after cut-in", "warn"], ["Ego keeps lane, no lane change", "ok"]] }),
  c({ xosc: "lane_merge_01.xosc", xodr: "e6mini.xodr", desc: "Merge from on-ramp",
    sem: .72, scen: .68, road: .70, cost: "High", match: "Not reusable", conf: .62, ver: "1.0", dur: "20 s",
    rationale: "On-ramp merge is a different manoeuvre family from adjacent-lane cut-in.",
    facts: [["Merge from on-ramp", "bad"], ["e6mini (3 lanes each direction)", "ok"], ["Lateral offset 3.5 m over 5 s", "ok"],
      ["Relative speed −15 km/h", "warn"], ["Ego keeps lane, no lane change", "ok"]] }),
  c({ xosc: "cutin_left_slow.xosc", xodr: "e6mini.xodr", desc: "Slow cut-in (low speed)",
    sem: .71, scen: .66, road: .80, cost: "Medium", match: "Modify and reuse", conf: .69, ver: "1.2", dur: "16 s",
    rationale: "Relative speed differs; adjust the target speed parameter.",
    facts: [["Cut-in from left lane", "ok"], ["e6mini (3 lanes each direction)", "ok"], ["Lateral offset 3.5 m over 6 s", "ok"],
      ["Relative speed −20 km/h", "warn"], ["Ego keeps lane, no lane change", "ok"]] }),
  c({ xosc: "cutin_right_02.xosc", xodr: "rural_2lane.xodr", desc: "Cut-in on rural road",
    sem: .68, scen: .62, road: .56, cost: "High", match: "Not reusable", conf: .58, ver: "1.0", dur: "14 s",
    rationale: "Rural two-lane road conflicts with the highway requirement.",
    facts: [["Cut-in from right lane", "warn"], ["rural_2lane (1 lane each direction)", "bad"], ["Lateral offset 3.0 m over 3 s", "ok"],
      ["Relative speed 0 ± 2 km/h", "ok"], ["Ego keeps lane, no lane change", "ok"]] }),
  c({ xosc: "lane_change_ego.xosc", xodr: "e6mini.xodr", desc: "Ego lane change with traffic",
    sem: .66, scen: .60, road: .75, cost: "High", match: "Not reusable", conf: .55, ver: "1.4", dur: "22 s",
    rationale: "The ego performs the lane change; the requirement needs the ego to keep its lane.",
    facts: [["No cut-in vehicle", "bad"], ["e6mini (3 lanes each direction)", "ok"], ["Ego lateral offset 3.5 m", "warn"],
      ["Relative speed 0 ± 5 km/h", "ok"], ["Ego changes lane", "bad"]] }),
];

export const DEFAULT_FILTERS: Record<string, string> = {
  "Scenario type": "Lane support",
  Maneuver: "Cut-in",
  "Road type": "Highway",
  Standard: "Euro NCAP",
};

export const FILTER_OPTIONS: Record<string, string[]> = {
  "Scenario type": ["Lane support", "AEB", "ACC"],
  Maneuver: ["Cut-in", "Cut-out", "Lane change", "Merge"],
  "Road type": ["Highway", "Rural", "Urban"],
  Standard: ["Euro NCAP", "GB/T", "UN R157"],
};
