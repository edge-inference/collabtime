'use strict';
function bindChoices(selector, onSelect) {
  const buttons = [...document.querySelectorAll(`${selector} button[data-value]`)];
  function select(button) {
    for (const option of buttons) {
      option.setAttribute('aria-pressed', String(option === button));
    }
    onSelect(button.dataset.value);
  }
  for (const button of buttons) button.addEventListener('click', () => select(button));
  select(buttons.find(button => button.getAttribute('aria-pressed') === 'true') || buttons[0]);
}
const partnrVideo = document.querySelector('#partnr-video');
let partnrPlaybackRate = 1;
function setPartnrSpeed() {
  partnrVideo.defaultPlaybackRate = partnrPlaybackRate;
  partnrVideo.playbackRate = partnrPlaybackRate;
}
bindChoices('#partnr-speed', value => {
  partnrPlaybackRate = Number(value);
  setPartnrSpeed();
});
partnrVideo.addEventListener('loadedmetadata', setPartnrSpeed);
async function init() {
  const response = await fetch('results.json');
  if (!response.ok) throw new Error('Could not load the comparison data.');
  const {configurations} = await response.json();
  // Every configuration is drawn at once, as in the paper's figure: one panel per metric,
  // one vertical bar per configuration, in the order of results.json.
  const short = {
    solo: ['System 1', 'alone'], timeslicing: ['GPU time', 'slicing'], mps: ['System 2', 'MPS 50%'],
    priority: ['Action', 'priority'], uniform: ['Uniform', '250 ms'], phase: ['Phase', 'budgets']
  };
  const roles = {timeslicing: 'is-base', priority: 'is-priority', uniform: 'is-uniform'};
  const baseline = configurations.find(c => c.id === 'timeslicing');
  const plotHeight = 150;
  const metrics = [
    ['Action inference latency (ms)', 'latency_ms', 300, 'ms', 0, '\u224846% lower vs. time slicing', 'gain'],
    ['Task success (%)', 'success_pct', 100, '%', 1, 'System 1 alone success retained', ''],
    ['Module energy (J per episode)', 'energy_j', 900, 'J', 0, '\u224813% lower vs. time slicing', 'gain']
  ];
  const chart = document.querySelector('#comparison-chart');
  chart.replaceChildren();
  for (const [label, key, max, unit, places, hint, hintClass] of metrics) {
    const node = document.createElement('section'); node.className = 'vb-panel';
    const head = document.createElement('div'); head.className = 'vb-head';
    const heading = document.createElement('h4'); heading.className = 'vb-title'; heading.textContent = label;
    const keyLine = document.createElement('span'); keyLine.className = 'vb-key';
    keyLine.append(document.createElement('i'), 'GPU time slicing');
    head.append(heading, keyLine);
    const sub = document.createElement('p'); sub.className = `vb-hint ${hintClass}`.trim(); sub.textContent = hint;
    const list = document.createElement('ul'); list.className = 'vb-bars';
    const line = document.createElement('li'); line.className = 'vb-baseline'; line.setAttribute('aria-hidden', 'true');
    line.style.top = `${18 + plotHeight - baseline[key]/max*plotHeight}px`;
    list.append(line);
    for (const record of configurations) {
      const col = document.createElement('li'); col.className = `vb-col ${roles[record.id] || ''}`.trim();
      col.setAttribute('aria-label', `${record.label}: ${record[key].toFixed(places)} ${unit}`);
      const stack = document.createElement('span'); stack.className = 'vb-stack'; stack.setAttribute('aria-hidden', 'true');
      const value = document.createElement('span'); value.className = 'vb-val'; value.textContent = record[key].toFixed(places);
      const bar = document.createElement('span'); bar.className = 'vb-bar';
      bar.style.height = `${record[key]/max*plotHeight}px`;
      stack.append(value, bar);
      const name = document.createElement('span'); name.className = 'vb-name'; name.setAttribute('aria-hidden', 'true');
      name.append(short[record.id][0], document.createElement('br'), short[record.id][1]);
      col.append(stack, name); list.append(col);
    }
    node.append(head, sub, list); chart.append(node);
  }
  for (const c of configurations) {
    const tr = document.createElement('tr'); if (c.id === 'priority' || c.id === 'uniform') tr.className='highlight';
    for (const v of [c.label, c.latency_ms, c.success_pct.toFixed(1), c.energy_j]) {
      const td=document.createElement('td'); td.textContent=v; tr.append(td);
    }
    document.querySelector('#result-table').append(tr);
  }
}
init().catch(error => { document.querySelector('#comparison-chart').textContent = error.message; });
