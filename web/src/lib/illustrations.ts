// Hand-drawn SVG placeholders. Real thumbnails will come from esmini frames / PDF figure crops.
import type { SceneKind } from "../data/mock";

const uri = (svg: string) => `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
const wrap = (w: number, h: number, body: string, defs = "") =>
  uri(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}"><defs>${CAR_DEFS}${defs}</defs>${body}</svg>`);

const CAR_DEFS =
  '<filter id="sh" x="-30%" y="-30%" width="160%" height="160%"><feDropShadow dx="0" dy=".8" stdDeviation=".7" flood-opacity=".45"/></filter>' +
  '<linearGradient id="asph" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#868c92"/><stop offset="1" stop-color="#737980"/></linearGradient>';

function car(x: number, y: number, ang: number, color: string, s = 1) {
  return `<g transform="translate(${x} ${y}) rotate(${ang}) scale(${s})" filter="url(#sh)">
    <rect x="-8.5" y="-4.3" width="17" height="8.6" rx="2.6" fill="${color}" stroke="#00000033" stroke-width=".5"/>
    <rect x="1.4" y="-3.5" width="3.4" height="7" rx="1.1" fill="#1b2633" opacity=".82"/>
    <rect x="-6.6" y="-3.2" width="2.2" height="6.4" rx=".9" fill="#1b2633" opacity=".55"/>
    <rect x="-3.6" y="-3.3" width="4.4" height="6.6" rx="1" fill="#ffffff" opacity=".12"/>
  </g>`;
}

function arrow(d: string, x: number, y: number, ang: number, color = "#ffffff") {
  return `<path d="${d}" fill="none" stroke="${color}" stroke-width="1.3" stroke-dasharray="3 2.2"/>
    <polygon points="0,-2.7 5.2,0 0,2.7" fill="${color}" transform="translate(${x} ${y}) rotate(${ang})"/>`;
}

function straightRoad(w: number, h: number, top: number, bot: number) {
  const m1 = top + (bot - top) / 3, m2 = top + (2 * (bot - top)) / 3;
  return `<rect width="${w}" height="${h}" fill="#8e9a84"/>
    <rect y="${top - 1}" width="${w}" height="${bot - top + 2}" fill="url(#asph)"/>
    <line x1="0" y1="${top}" x2="${w}" y2="${top}" stroke="#eef1f3" stroke-width="1.3"/>
    <line x1="0" y1="${bot}" x2="${w}" y2="${bot}" stroke="#eef1f3" stroke-width="1.3"/>
    <line x1="0" y1="${m1}" x2="${w}" y2="${m1}" stroke="#eef1f3" stroke-width="1.1" stroke-dasharray="8 6"/>
    <line x1="0" y1="${m2}" x2="${w}" y2="${m2}" stroke="#eef1f3" stroke-width="1.1" stroke-dasharray="8 6"/>`;
}

const WHITE = "#f3f5f7", BLUE = "#2f6fd6", GREY = "#c5cad0";

export function sceneThumb(kind: SceneKind) {
  const w = 112, h = 72;
  let b = straightRoad(w, h, 7, 65);
  switch (kind) {
    case "straight":
      b += car(40, 55, 0, WHITE) + car(92, 36, 0, GREY, 0.92);
      break;
    case "cutin":
      b += car(30, 55, 0, WHITE) + car(60, 38, 16, BLUE) + arrow("M69 41 C78 44 84 52 95 54", 95, 54, 12);
      break;
    case "cutout":
      b += car(30, 55, 0, WHITE) + car(70, 50, -18, GREY) + arrow("M79 46 C86 42 92 38 101 36", 101, 36, -12);
      break;
    case "lead":
      b += car(30, 55, 0, WHITE) + car(66, 55, 0, GREY) +
        '<line x1="40" y1="55" x2="56" y2="55" stroke="#ffd34d" stroke-width="1.2" stroke-dasharray="2 2"/>';
      break;
    case "curve":
      b = `<rect width="${w}" height="${h}" fill="#8e9a84"/>
        <path d="M-10 88 Q 40 62 124 0" fill="none" stroke="#eef1f3" stroke-width="50"/>
        <path d="M-10 88 Q 40 62 124 0" fill="none" stroke="#7d8389" stroke-width="47"/>
        <path d="M-10 88 Q 40 62 124 0" fill="none" stroke="#eef1f3" stroke-width="1.1" stroke-dasharray="7 6"/>` +
        car(46, 50, -28, WHITE) + car(80, 33, -36, GREY, 0.9);
      break;
  }
  return wrap(w, h, b);
}

export function simPreview() {
  const w = 220, h = 150;
  const parts = [
    `<rect width="${w}" height="${h}" fill="#7f8f70"/>`,
    `<rect width="${w}" height="${h}" fill="url(#fog)"/>`,
    '<polygon points="16,150 204,150 125,0 95,0" fill="url(#asph)"/>',
  ];
  for (const k of [0, 1]) parts.push(`<line x1="${16 + 188 * k}" y1="150" x2="${95 + 30 * k}" y2="0" stroke="#f2f4f6" stroke-width="1.7"/>`);
  for (const k of [1 / 3, 2 / 3])
    parts.push(`<line x1="${16 + 188 * k}" y1="150" x2="${95 + 30 * k}" y2="0" stroke="#f2f4f6" stroke-width="1.3" stroke-dasharray="12 10"/>`);
  parts.push(car(112, 124, -90, BLUE, 1.9), car(131, 50, -92, "#eceff2", 1.25), arrow("M129 62 C127 80 119 92 114 104", 114, 104, 110));
  const fog = '<linearGradient id="fog" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".4"/><stop offset=".55" stop-color="#fff" stop-opacity="0"/></linearGradient>';
  return wrap(w, h, parts.join(""), fog);
}

function rng(seed: number) {
  let s = seed;
  return () => ((s = (s * 16807) % 2147483647) - 1) / 2147483646;
}

export function roadPreview(lanesEach = 3, rural = false) {
  const w = 200, h = 96, r = rng(7 + lanesEach);
  const p: string[] = [`<rect width="${w}" height="${h}" fill="#6d8a52"/>`];
  const greens = ["#5d7a45", "#7d9a5f", "#4f6b3b", "#8aa56b"];
  for (let i = 0; i < 80; i++)
    p.push(`<circle cx="${(r() * w).toFixed(1)}" cy="${(r() * h).toFixed(1)}" r="${(1.5 + r() * 3).toFixed(1)}" fill="${greens[Math.floor(r() * 4)]}"/>`);
  const lw = 5.2;
  if (rural) {
    const top = 40, rw = lw * 3;
    p.push(`<rect x="0" y="${top}" width="${w}" height="${rw}" fill="#8a8f93"/>`,
      `<line x1="0" y1="${top + rw / 2}" x2="${w}" y2="${top + rw / 2}" stroke="#f1f1f1" stroke-width=".8" stroke-dasharray="6 5"/>`);
  } else {
    const cw = lanesEach * lw, top = (h - (2 * cw + 4)) / 2;
    for (const c of [0, 1]) {
      const y0 = top + c * (cw + 4);
      p.push(`<rect x="0" y="${y0}" width="${w}" height="${cw}" fill="#868b90"/>`,
        `<line x1="0" y1="${y0}" x2="${w}" y2="${y0}" stroke="#f1f1f1" stroke-width=".7"/>`,
        `<line x1="0" y1="${y0 + cw}" x2="${w}" y2="${y0 + cw}" stroke="#f1f1f1" stroke-width=".7"/>`);
      for (let k = 1; k < lanesEach; k++)
        p.push(`<line x1="0" y1="${y0 + k * lw}" x2="${w}" y2="${y0 + k * lw}" stroke="#f1f1f1" stroke-width=".55" stroke-dasharray="5 5"/>`);
    }
    p.push(`<rect x="0" y="${top + cw}" width="${w}" height="4" fill="#5d7a45"/>`);
  }
  return wrap(w, h, p.join(""));
}

function textLines(x: number, y: number, width: number, n: number, seed: number, gap = 4.2, lw = 1.6) {
  const r = rng(seed + 11);
  let out = "";
  for (let i = 0; i < n; i++) {
    const ww = width * (i < n - 1 ? 0.72 + r() * 0.28 : 0.35 + r() * 0.25);
    out += `<rect x="${x}" y="${(y + i * gap).toFixed(1)}" width="${ww.toFixed(1)}" height="${lw}" fill="#c3c8ce"/>`;
  }
  return out;
}

export function pdfPage(pageNo: number, seed = 1) {
  const w = 120, h = 160;
  return wrap(w, h, `<rect width="${w}" height="${h}" fill="#fff"/>
    <text x="8" y="12" font-size="7" font-family="Arial" font-weight="700" fill="#222">${pageNo}</text>
    <text x="112" y="12" font-size="5" font-family="Arial" text-anchor="end" fill="#555">Euro NCAP</text>
    <line x1="8" y1="16" x2="112" y2="16" stroke="#d6d9dd" stroke-width=".6"/>
    ${textLines(8, 22, 104, 9, seed)}${textLines(8, 64, 104, 6, seed + 3)}
    <rect x="10" y="94" width="100" height="34" fill="#eef0f2"/>
    <line x1="10" y1="111" x2="110" y2="111" stroke="#9aa1a8" stroke-width=".6" stroke-dasharray="3 2"/>
    ${car(40, 118, 0, WHITE, 0.9)}${car(70, 104, 0, BLUE, 0.9)}
    ${textLines(8, 136, 104, 4, seed + 7)}`);
}

export function evidenceFigure() {
  const w = 240, h = 48;
  return wrap(w, h, `<rect width="${w}" height="${h}" fill="url(#asph)"/>
    <line x1="0" y1="4" x2="${w}" y2="4" stroke="#eef1f3" stroke-width="1.2"/>
    <line x1="0" y1="44" x2="${w}" y2="44" stroke="#eef1f3" stroke-width="1.2"/>
    <line x1="0" y1="24" x2="${w}" y2="24" stroke="#eef1f3" stroke-width="1" stroke-dasharray="9 7"/>
    ${car(90, 14, 0, BLUE, 1.15)}${car(150, 34, 0, WHITE, 1.15)}${arrow("M103 14 L129 14", 129, 14, 0)}`);
}

export function docPage(title: string, seed = 4) {
  const w = 300, h = 400;
  return wrap(w, h, `<rect width="${w}" height="${h}" fill="#fff"/>
    <text x="22" y="34" font-size="12" font-family="Arial" font-weight="700" fill="#1d2733">${title}</text>
    ${textLines(22, 50, 256, 12, seed, 8, 2.4)}
    <rect x="22" y="160" width="256" height="90" fill="#eef0f2"/>
    ${car(110, 222, 0, WHITE, 1.8)}${car(170, 188, 12, BLUE, 1.8)}
    ${textLines(22, 268, 256, 14, seed + 2, 8, 2.4)}`);
}
