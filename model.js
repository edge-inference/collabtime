'use strict';
const SVG = 'http://www.w3.org/2000/svg';
const $ = id => document.getElementById(id);
function el(name, attrs, text) {
  const node = document.createElementNS(SVG, name);
  for (const [key, value] of Object.entries(attrs || {})) node.setAttribute(key, value);
  if (text !== undefined) node.textContent = text;
  return node;
}
function press(group, chosen) {
  for (const button of group.querySelectorAll('button')) button.setAttribute('aria-pressed', String(button === chosen));
}
const results = fetch('results.json').then(response => {
  if (!response.ok) throw new Error('Could not load the comparison data.');
  return response.json();
});

/* A replay: Restart, Back, Play or Pause, Step. It plays by itself, once each time its panel reaches the middle of the
   window, and pauses when the panel leaves it or the tab is hidden. The first use of a control hands it to the reader
   for good. With reduced motion nothing plays until the reader asks. While it plays by itself the step note is not
   announced. */
const calm = matchMedia('(prefers-reduced-motion: reduce)');
function replay(root, {count, render, interval = 1500}) {
  const play = root.querySelector('[data-act="play"]'), position = root.querySelector('.replay-pos');
  const note = root.previousElementSibling, notes = note && note.hasAttribute('aria-live') ? [note] : [];
  let index = 0, total = count, timer = null, auto = !calm.matches && 'IntersectionObserver' in window, inView = false;
  const announce = on => { for (const note of notes) note.setAttribute('aria-live', on ? 'polite' : 'off'); };
  const stop = () => { clearInterval(timer); timer = null; play.textContent = 'Play'; };
  const show = () => { render(index); position.textContent = `Step ${index + 1} of ${total}`; };
  const go = to => { index = Math.max(0, Math.min(total - 1, to)); show(); };
  const start = () => {
    if (timer) return;
    if (index === total - 1) go(0);
    play.textContent = 'Pause';
    timer = setInterval(() => { go(index + 1); if (index >= total - 1) stop(); }, interval);
  };
  const autoplay = () => { if (auto && inView && !document.hidden) start(); };
  root.addEventListener('click', event => {
    const button = event.target.closest('button'); if (!button) return;
    if (auto) { auto = false; announce(true); }
    const act = button.dataset.act;
    if (act !== 'play') { stop(); go(act === 'next' ? index + 1 : act === 'back' ? index - 1 : 0); return; }
    if (timer) stop(); else start();
  });
  if (auto) {
    announce(false);
    new IntersectionObserver(([entry]) => {
      inView = entry.isIntersecting;
      if (!auto) return;
      if (inView) autoplay(); else stop();
    }, {rootMargin: '-35% 0px -35% 0px'}).observe(root.closest('.panel') || root);
    document.addEventListener('visibilitychange', () => { if (!auto) return; if (document.hidden) stop(); else autoplay(); });
  }
  show();
  return {reset(newCount, to = 0) { stop(); if (newCount) total = newCount; go(to); }, autoplay};
}

/* 01. One action request under three serving rules; latencies come from results.json. */
async function initRules() {
  const {configurations, scope} = await results;
  const byId = Object.fromEntries(configurations.map(c => [c.id, c]));
  const base = byId.timeslicing.latency_ms;
  const x = ms => 130 + ms * 1.6;
  for (const ms of [0, 100, 200, 300]) {
    $('rule-axis').append(el('line', {class: 'd-axis', x1: x(ms), y1: 127, x2: x(ms), y2: 137}),
      el('text', {class: 'd-lab', x: x(ms), y: 152, 'text-anchor': 'middle'}, ms === 300 ? '300 ms' : String(ms)));
  }
  const words = {solo: 'action latency with System 1 alone', timeslicing: 'action latency under GPU time slicing', priority: 'action latency under action priority'};
  function render(rule) {
    const latency = byId[rule].latency_ms, end = x(latency), marks = $('rule-marks');
    marks.replaceChildren();
    if (rule === 'solo') {
      marks.append(el('text', {class: 'd-lab', x: 130, y: 48}, 'not running'),
        el('rect', {class: 'f-s1', x: 130, y: 78, width: end - 130, height: 28, rx: 2}),
        el('text', {class: 'd-in', x: (130 + end) / 2, y: 96, 'text-anchor': 'middle'}, 'runs alone'));
    } else if (rule === 'timeslicing') {
      const slices = 7, width = (end - 130) / slices;  /* odd count: the action's last slice ends at the finish */
      for (let i = 0; i < slices; i++) {
        marks.append(el('rect', {class: i % 2 ? 'f-s2' : 'f-s1', x: 130 + i * width + 1, y: i % 2 ? 30 : 78, width: width - 2, height: 28, rx: 2}));
      }
      marks.append(el('rect', {class: 'f-s2', x: end + 1, y: 30, width: x(300) - end - 1, height: 28, rx: 2}));
    } else {
      marks.append(el('rect', {class: 'f-held', x: 131, y: 31, width: end - 132, height: 26, rx: 2}),
        el('text', {class: 'd-lab', x: (130 + end) / 2, y: 48, 'text-anchor': 'middle'}, 'held'),
        el('rect', {class: 'f-s2', x: end + 1, y: 30, width: x(300) - end - 1, height: 28, rx: 2}),
        el('text', {class: 'd-in', x: (end + x(300)) / 2, y: 48, 'text-anchor': 'middle'}, 'resumes'),
        el('rect', {class: 'f-s1', x: 130, y: 78, width: end - 130, height: 28, rx: 2}),
        el('text', {class: 'd-in', x: (130 + end) / 2, y: 96, 'text-anchor': 'middle'}, 'runs first'));
    }
    marks.append(el('line', {class: 'd-guide', x1: 130, y1: 18, x2: 130, y2: 132}), el('line', {class: 'd-guide', x1: end, y1: 18, x2: end, y2: 132}),
      el('text', {class: 'd-strong', x: 130, y: 170, 'text-anchor': 'middle'}, 'ready'), el('text', {class: 'd-strong', x: end, y: 170, 'text-anchor': 'middle'}, 'finish'));
    $('rule-ms').textContent = `${latency} ms`;
    const change = Math.round((1 - latency / base) * 100);
    $('rule-text').textContent = words[rule] + (rule === 'priority' ? `, ${change}% lower than time slicing` : rule === 'solo' ? '; System 2 is not running, so this is a reference, not a matched comparison' : '');
    $('rule-title').textContent = `One action request, ${words[rule]}: ${latency} milliseconds from ready to finish.`;
  }
  const group = document.querySelector('[aria-label="Serving rule"]');
  group.addEventListener('click', event => {
    const button = event.target.closest('button'); if (!button) return;
    press(group, button); render(button.dataset.rule);
  });
  if (scope) $('rule-scope').textContent = `Measured action latency. ${scope} The slices are drawn schematically.`;
  render('timeslicing');
}

/* 02. One GPU iteration grows with its batch (schematic). */
function initBatch() {
  const slider = $('robots');
  function render() {
    const n = Number(slider.value), width = 60 + 22 * n, end = 250 + width, chips = $('chips');
    $('robots-out').textContent = String(n);
    $('it-k').setAttribute('width', width); $('it-k-t').setAttribute('x', 250 + width / 2);
    $('it-k-t').textContent = width < 100 ? 'k' : 'iteration k';
    $('it-n').setAttribute('x', end); $('it-n-t').setAttribute('x', end + 45);
    $('it-end').setAttribute('x1', end); $('it-end').setAttribute('x2', end); $('it-end-t').setAttribute('x', end);
    chips.replaceChildren();
    for (let i = 0; i < n; i++) {
      const reading = i === n - 1 && n > 1;
      chips.append(el('rect', {x: 130 + i * 62, y: 184, width: 54, height: 24, rx: 2, fill: reading ? 'var(--orange)' : 'var(--blue)'}),
        el('text', {class: 'd-in', x: 157 + i * 62, y: 200, 'text-anchor': 'middle'}, `R${i + 1}`));
    }
    $('batch-title').textContent = `Three GPU iterations in a row. Iteration k carries ${n} robot${n === 1 ? '' : 's'} and is ${n > 3 ? 'longer' : 'shorter'} than its neighbours.`;
  }
  slider.addEventListener('input', render); render();
}

/* 03. The loop of Figure 4, replayed for two robots (illustrative numbers, the same as in section 04). */
const STEPS = [
  {l: [4], t: '0 ms', a: 'Skill ended, needs a decision', b: 'Carrying a cup', p: 'Empty', r: 'Idle',
    n: 'Each robot runs its own skill for this tick. Robot A’s skill has just ended, so A joins N, the robots that need a decision.'},
  {l: [5], t: '0 ms', a: 'Waiting', b: 'Carrying a cup', p: 'Empty', r: 'Idle',
    n: 'Inference runs on the simulation host using A’s image and prompt. It produces the System 2 decision Y, “go to the kitchen”, and resource demand D: 800 prompt tokens and 40 output tokens. Simulated time does not advance during host inference.'},
  {l: [6, 7], t: '0 ms', a: 'Waiting', b: 'Carrying a cup', p: 'A: go to the kitchen, release unknown', r: 'A in service',
    n: 'The System 2 decision is stored in the pending set. Its release time is initially infinity, so the robot cannot use it yet. The resource model receives the request’s demand to simulate execution on the target hardware.'},
  {l: [8, 9], t: '100 ms', a: 'Waiting', b: 'Carrying a cup', p: 'A: release unknown', r: 'A in service, would finish at 180 ms',
    n: 'The world moves one tick. The resource model is moved to the same time and asked what has finished. Nothing yet.'},
  {l: [4, 5, 6, 7], t: '100 ms', a: 'Waiting', b: 'Skill ended, needs a decision', p: 'A and B: release unknown', r: 'A and B share the GPU; A now finishes at 240 ms',
    n: 'B asks for a decision too. Its request joins A’s on the GPU and slows it: 180 ms becomes 240 ms. This is why no finish time was fixed when A arrived.'},
  {l: [8, 9], t: '300 ms', a: 'Waiting', b: 'Waiting', p: 'A: release at 300 ms. B: release unknown', r: 'A finished at 240 ms; B in service',
    n: 'Two more ticks. A finished at 240 ms. The next-tick rule rounds that up, so A’s release time is 300 ms.'},
  {l: [2, 3], t: '300 ms', a: 'New skill: go to the kitchen', b: 'Waiting', p: 'B: release unknown', r: 'B in service',
    n: 'A’s System 2 decision is released from the pending set and selects A’s next skill. A waited 300 ms of simulated time.'},
  {l: [8, 9, 2, 3], t: '400 ms', a: 'Going to the kitchen', b: 'New skill: place the cup', p: 'Empty', r: 'Idle',
    n: 'B finishes at 350 ms and is released at 400 ms in the same way.'},
  {l: [10, 11, 12], t: 'End', a: 'Task done, world removed', b: 'Task done, world removed', p: 'Dropped for finished worlds', r: 'Drained',
    n: 'A world that completes its task or runs out of budget leaves the loop, and its pending System 2 decisions are discarded. After the loop, leftover GPU work runs to completion so time and energy are counted in full.'}
];
function initLoop() {
  const lines = [...document.querySelectorAll('#code li')];
  replay($('loop-replay'), {count: STEPS.length, interval: 2600, render(index) {
    const step = STEPS[index];
    lines.forEach((line, i) => line.classList.toggle('on', step.l.includes(i + 1)));
    document.querySelector('#s-t strong').textContent = step.t;
    $('s-a').textContent = step.a; $('s-b').textContent = step.b; $('s-p').textContent = step.p; $('s-r').textContent = step.r;
    $('step-note').textContent = step.n;
  }});
}

/* 04. Two clocks: the world and the hardware model, in step or with the model running ahead. */
const A180 = {proj: 180, label: 'alone: 180 ms'}, A240 = {proj: 240, label: 'shared: 240 ms'}, B350 = {proj: 350, label: '350 ms'}, B280 = {proj: 280, label: 'alone: 280 ms'};
const SYNC = {
  step: [
    {w: 0, m: 0, a: A180, n: 'Robot A asks at 0 ms. Alone, its request would take 180 ms.'},
    {w: 100, m: 0, a: A180, n: 'The world steps one tick, to 100 ms.'},
    {w: 100, m: 100, a: A180, n: 'The hardware model catches up to 100 ms and stops there. A is not finished.'},
    {w: 100, m: 100, a: A240, b: B350, n: 'Robot B asks at 100 ms. The two requests share the GPU, so A now needs until 240 ms.'},
    {w: 200, m: 100, a: A240, b: B350, n: 'The world steps to 200 ms.'},
    {w: 200, m: 200, a: A240, b: B350, n: 'The model catches up. Nothing has finished, so nothing is released.'},
    {w: 300, m: 200, a: A240, b: B350, n: 'The world steps to 300 ms.'},
    {w: 300, m: 300, a: A240, b: B350, relA: 300, n: 'The model catches up. A finished at 240 ms and is released at this tick, 300 ms.'},
    {w: 400, m: 400, a: A240, b: B350, relA: 300, relB: 400, n: 'One more tick. B finished at 350 ms and is released at 400 ms.'}
  ],
  ahead: [
    {w: 0, m: 0, a: A180, n: 'Robot A asks at 0 ms. Alone, its request would take 180 ms.'},
    {w: 0, m: 180, a: A180, n: 'The hardware model runs A straight to its end, 180 ms, without waiting for the world.'},
    {w: 100, m: 180, a: A180, b: B280, bDone: 0, n: 'Robot B asks at 100 ms. A’s finish is already fixed, so B cannot slow it.'},
    {w: 200, m: 200, a: A180, b: B280, relA: 200, n: 'A is released at 200 ms. In step with the world it is 300 ms: the model output is released one tick too early.'}
  ]
};
function initSync() {
  const x = ms => 120 + ms * 0.98, group = document.querySelector('[aria-label="How the hardware model is driven"]');
  for (let ms = 0; ms <= 500; ms += 100) {
    $('sync-axis').append(el('line', {class: 'd-axis', x1: x(ms), y1: 161, x2: x(ms), y2: 171}),
      el('text', {class: 'd-lab', x: x(ms), y: 188, 'text-anchor': 'middle'}, ms === 500 ? '500 ms' : String(ms)));
  }
  let mode = 'step';
  const player = replay($('sync-replay'), {count: SYNC.step.length, interval: 1700, render(index) {
    const frame = SYNC[mode][index];
    $('a-proj').setAttribute('width', frame.a.proj * 0.98);
    $('a-done').style.transform = `scaleX(${Math.min(frame.m, frame.a.proj) / 500})`;
    $('a-end').setAttribute('x', x(frame.a.proj) + 8); $('a-end').textContent = frame.a.label;
    for (const id of ['b-proj', 'b-done', 'b-end']) $(id).setAttribute('visibility', frame.b ? 'visible' : 'hidden');
    if (frame.b) {
      const done = frame.bDone !== undefined ? frame.bDone : Math.max(0, Math.min(frame.m, frame.b.proj) - 100);
      $('b-proj').setAttribute('width', (frame.b.proj - 100) * 0.98);
      $('b-done').style.transform = `scaleX(${done / 400})`;
      $('b-end').setAttribute('x', x(frame.b.proj) + 8); $('b-end').textContent = frame.b.label;
    } else $('b-done').style.transform = 'scaleX(0)';
    $('clock-world').style.transform = `translateX(${x(frame.w)}px)`;
    $('clock-model').style.transform = `translateX(${x(frame.m)}px)`;
    const released = $('sync-released'); released.replaceChildren();
    for (const [name, at] of [['A', frame.relA], ['B', frame.relB]]) {
      if (at === undefined) continue;
      released.append(el('circle', {cx: x(at), cy: 166, r: 5, fill: 'var(--teal)'}), el('text', {class: 'd-strong', x: x(at), y: 232, 'text-anchor': 'middle'}, `${name} released`));
    }
    $('sync-note').textContent = frame.n;
    $('sync-title').textContent = `${mode === 'step' ? 'In step with the world' : 'Running ahead'}. World clock at ${frame.w} milliseconds, hardware model clock at ${frame.m} milliseconds. ${frame.n}`;
  }});
  group.addEventListener('click', event => {
    const button = event.target.closest('button'); if (!button) return;
    press(group, button); mode = button.dataset.mode; player.reset(SYNC[mode].length); player.autoplay();
  });
}

/* 05. A finish time is applied at the next control tick. */
function initTick() {
  const slider = $('finish'), group = document.querySelector('[aria-label="Control rate"]');
  let hz = 20;
  const x = ms => 40 + ms * 1.4;
  function render() {
    const finish = Number(slider.value), ticks = Math.ceil(finish * hz / 1000 - 1e-9), applied = ticks * 1000 / hz, marks = $('tick-marks');
    $('finish-out').textContent = `${finish} ms`;
    marks.replaceChildren();
    for (let k = 0; k * 1000 / hz <= 400 + 1e-9; k++) marks.append(el('line', {class: 'd-axis', x1: x(k * 1000 / hz), y1: 54, x2: x(k * 1000 / hz), y2: 70}));
    marks.append(el('line', {x1: x(finish), y1: 62, x2: x(applied), y2: 62, stroke: 'var(--teal)', 'stroke-width': 3}),
      el('circle', {cx: x(finish), cy: 62, r: 6, fill: 'var(--orange)'}), el('circle', {cx: x(applied), cy: 62, r: 6, fill: 'var(--teal)'}),
      el('text', {class: 'd-lab', x: Math.min(Math.max(x(finish), 70), 570), y: 38, 'text-anchor': 'middle'}, 'inference complete'),
      el('text', {class: 'd-strong', x: Math.min(Math.max(x(applied), 70), 570), y: 92, 'text-anchor': 'middle'}, 'applied'));
    const wait = Math.round(applied - finish);
    $('tick-ms').textContent = `${Math.round(applied)} ms`;
    $('tick-text').textContent = wait === 0 ? 'applied immediately: modeled completion coincides with a control tick' : `applied, ${wait} ms after modeled completion`;
    $('tick-title').textContent = `Control ticks every ${Math.round(1000 / hz)} milliseconds. Modeled inference completes at ${finish} milliseconds and the output is applied at ${Math.round(applied)} milliseconds.`;
  }
  group.addEventListener('click', event => {
    const button = event.target.closest('button'); if (!button) return;
    press(group, button); hz = Number(button.dataset.hz); render();
  });
  slider.addEventListener('input', render); render();
}

/* 06. The scheduler's hold rule (Equation 5) replayed for one action inference. */
async function initScheduler() {
  const {configurations} = await results;
  const byId = Object.fromEntries(configurations.map(c => [c.id, c]));
  const free = byId.timeslicing.latency_ms, held = byId.priority.latency_ms, margin = 0.8;
  const x = ms => 130 + ms * 1.6, slider = $('budget'), group = document.querySelector('[aria-label="Budget"]');
  for (const ms of [0, 100, 200, 300]) {
    $('sched-axis').append(el('line', {class: 'd-axis', x1: x(ms), y1: 127, x2: x(ms), y2: 137}),
      el('text', {class: 'd-lab', x: x(ms), y: 152, 'text-anchor': 'middle'}, ms === 300 ? '300 ms' : String(ms)));
  }
  const measured = [['timeslicing', 'GPU time slicing'], ['priority', 'Always prioritize'], ['uniform', 'Uniform 250 ms budget'], ['phase', 'Phase budgets, 300 and 450 ms']];
  for (const [id, label] of measured) {
    const item = document.createElement('div'), term = document.createElement('dt'), value = document.createElement('dd');
    item.dataset.id = id; term.textContent = `Measured: ${label}`; value.textContent = `${byId[id].latency_ms} ms`;
    item.append(term, value); $('sched-measured').append(item);
  }
  let always = false;
  function plan() {
    const budget = Number(slider.value), target = margin * budget;
    if (always) return {kind: 'full', share: 1, hold: held, finish: held, target: null, budget};
    if (free <= target) return {kind: 'free', share: 0, hold: 0, finish: free, target, budget};
    const share = Math.min(1, Math.max(0, (free - target) / (free - held)));
    return share >= 1 ? {kind: 'full', share: 1, hold: held, finish: held, target, budget} : {kind: 'partial', share, hold: share * held, finish: target, target, budget};
  }
  function slices(marks, from, to, firstIsAction) {
    let count = Math.max(firstIsAction ? 1 : 2, Math.round((to - from) / 37));
    if ((count % 2 === 1) !== firstIsAction) count += 1;  /* the last slice is always the action's */
    const width = (x(to) - x(from)) / count;
    for (let i = 0; i < count; i++) {
      const action = firstIsAction ? i % 2 === 0 : i % 2 === 1;
      marks.append(el('rect', {class: action ? 'f-s1' : 'f-s2', x: x(from) + i * width + 1, y: action ? 78 : 30, width: Math.max(1, width - 2), height: 28, rx: 2}));
    }
  }
  const player = replay($('sched-replay'), {count: 4, interval: 2000, render(index) {
    const p = plan(), marks = $('sched-marks'), holdEnd = x(p.hold), end = x(p.finish);
    marks.replaceChildren();
    marks.append(el('line', {class: 'd-guide', x1: 130, y1: 18, x2: 130, y2: 132}), el('text', {class: 'd-strong', x: 130, y: 170, 'text-anchor': 'middle'}, 'arrives'));
    const targetOnChart = p.target !== null && p.target <= 300;
    if (index >= 1 && targetOnChart && !(index === 3 && p.kind === 'partial')) {
      marks.append(el('line', {x1: x(p.target), y1: 18, x2: x(p.target), y2: 132, stroke: 'var(--orange)', 'stroke-width': 1.5, 'stroke-dasharray': '4 4'}),
        el('text', {class: 'd-lab', x: x(p.target), y: 170, 'text-anchor': 'middle'}, 'target'));
    }
    if (index < 2) {
      marks.append(el('text', {class: 'd-lab', x: 142, y: 48}, 'running'), el('circle', {cx: 130, cy: 92, r: 5, fill: 'var(--teal)'}), el('text', {class: 'd-lab', x: 142, y: 96}, 'action request'));
    } else if (p.kind === 'free') {
      slices(marks, 0, free, true);
      if (index === 3) marks.append(el('rect', {class: 'f-s2', x: end + 1, y: 30, width: x(300) - end - 1, height: 28, rx: 2}), el('text', {class: 'd-strong', x: end, y: 170, 'text-anchor': 'middle'}, 'finish'));
    } else {
      marks.append(el('rect', {class: 'f-held', x: 131, y: 31, width: Math.max(2, holdEnd - 132), height: 26, rx: 2}),
        el('rect', {class: 'f-s1', x: 130, y: 78, width: holdEnd - 130, height: 28, rx: 2}));
      if (holdEnd - 130 > 44) marks.append(el('text', {class: 'd-lab', x: (130 + holdEnd) / 2, y: 48, 'text-anchor': 'middle'}, 'held'));
      if (index === 3) {
        if (p.kind === 'partial') slices(marks, p.hold, p.finish, false);
        marks.append(el('rect', {class: 'f-s2', x: end + 1, y: 30, width: x(300) - end - 1, height: 28, rx: 2}),
          el('text', {class: 'd-strong', x: end, y: 170, 'text-anchor': 'middle'}, p.kind === 'partial' ? 'finish, on target' : 'finish'));
      }
    }
    const head = index < 2 ? 0 : index === 2 ? (p.kind === 'free' ? free / 2 : p.hold) : p.finish;
    $('sched-head').style.transform = `translateX(${x(head)}px)`;
    const target = p.target === null ? null : Math.round(p.target);
    const notes = {
      free: [`An action request arrives. The scheduler’s estimates: ${free} ms with System 2 free, ${held} ms with System 2 held.`,
        `The target is 0.8 × ${p.budget} = ${target} ms. The free estimate, ${free} ms, is within it, so System 2 keeps running.`,
        'Both models share the GPU from the start.', `The action completes near ${free} ms, the free estimate.`],
      partial: [`An action request arrives. The scheduler’s estimates: ${free} ms with System 2 free, ${held} ms with System 2 held.`,
        `The target is 0.8 × ${p.budget} = ${target} ms. The free estimate, ${free} ms, is above it. Hold share: ${Math.round(p.share * 100)}%.`,
        `System 2 is suspended for ${Math.round(p.hold)} ms. Its model stays in memory.`,
        `System 2 resumes and the two share the GPU. The rule aims the action at ${target} ms.`],
      full: [`An action request arrives. The scheduler’s estimates: ${free} ms with System 2 free, ${held} ms with System 2 held.`,
        always ? 'Always prioritize: every action inference gets a full hold, whatever the budget.' : `The target is 0.8 × ${p.budget} = ${target} ms, below what a hold can reach. The hold is full.`,
        'System 2 is suspended until the action completes. Its model stays in memory.', `The action completes near ${held} ms. System 2 resumes.`]
    };
    $('sched-note').textContent = notes[p.kind][index];
    $('sched-title').textContent = `One action inference under the scheduler. ${notes[p.kind][index]}`;
  }});
  function update() {
    const p = plan();
    $('budget-out').textContent = always ? 'any' : `${p.budget} ms`;
    $('sched-f').textContent = p.kind === 'free' ? 'No hold' : p.kind === 'full' ? 'Full hold' : `${Math.round(p.share * 100)}% hold`;
    $('sched-text').textContent = p.kind === 'free' ? `the free estimate is within the target of ${Math.round(p.target)} ms`
      : p.kind === 'full' ? (always ? 'on every action inference, whatever the budget' : `the target of ${Math.round(p.target)} ms is below what a hold can reach, ${held} ms`)
      : `${Math.round(p.hold)} ms of each action inference; the rule aims at ${Math.round(p.target)} ms`;
    const match = always ? 'priority' : p.budget === 250 ? 'uniform' : p.budget === 300 || p.budget === 450 ? 'phase' : null;
    for (const item of $('sched-measured').children) item.classList.toggle('on', item.dataset.id === match);
    player.reset(4, 3);
  }
  group.addEventListener('click', event => {
    const button = event.target.closest('button'); if (!button) return;
    press(group, button); always = button.dataset.budget === 'always';
    if (!always) slider.value = button.dataset.budget;
    update();
  });
  slider.addEventListener('input', () => {
    always = false;
    press(group, group.querySelector(`[data-budget="${slider.value}"]`));
    update();
  });
  $('sched-scope').textContent = `The two estimates are set to the measured medians of the LIBERO comparison: ${free} ms with System 2 free and ${held} ms with it held. The correction term is zero. The target is what the rule aims for, not a measurement.`;
  update();
}

initBatch(); initLoop(); initSync(); initTick();
initRules().catch(error => { $('rule-text').textContent = error.message; });
initScheduler().catch(error => { $('sched-text').textContent = error.message; });
