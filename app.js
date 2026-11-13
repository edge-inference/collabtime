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
  const baseline = configurations.find(c => c.id === 'timeslicing');
  const descriptions = {
    priority: 'Brief action priority lowers latency and energy. Phase labels are not required for this configuration.',
    uniform: 'A uniform 250 ms budget performs similarly to action priority in this comparison.',
    phase: 'The tested phase budgets allow more overlap, but do not improve task success or energy over action priority.',
    mps: 'The 50% MPS limit permits higher System 2 throughput than action priority, at higher System 1 latency. It is not an equal-throughput comparison.',
    solo: 'System 1 alone is a task-success reference. It does not execute System 2, so its energy is not a matched co-execution comparison.'
  };
  function render(selectedId) {
    const selected = configurations.find(c => c.id === selectedId);
    const metrics = [
      ['Action inference latency', 'latency_ms', 300, 'ms', 0],
      ['Task success', 'success_pct', 100, '%', 1],
      ['Module energy per episode', 'energy_j', 900, 'J', 0]
    ];
    const chart = document.querySelector('#comparison-chart');
    chart.replaceChildren();
    for (const [label, key, max, unit, places] of metrics) {
      const node = document.createElement('div'); node.className = 'metric';
      const heading = document.createElement('div'); heading.className = 'metric-label';
      const name = document.createElement('span'); name.textContent = label; heading.append(name);
      if (key !== 'success_pct' && selected.id !== 'solo') {
        const change = document.createElement('strong');
        const reduction = (1-selected[key]/baseline[key])*100;
        change.textContent = `${Math.abs(reduction).toFixed(0)}% ${reduction >= 0 ? 'lower' : 'higher'}`;
        heading.append(change);
      }
      node.append(heading);
      for (const [record, css] of [[baseline, ''], [selected, 'selected']]) {
        const row = document.createElement('div'); row.className = `metric-bar ${css}`;
        row.setAttribute('aria-label', `${record.label}: ${record[key].toFixed(places)} ${unit}`);
        const bar = document.createElement('span'); bar.className='bar'; bar.style.width=`${record[key]/max*78}%`;
        const value = document.createElement('span'); value.className='value'; value.textContent=`${record[key].toFixed(places)} ${unit}`;
        row.append(bar, value); node.append(row);
      }
      chart.append(node);
    }
    document.querySelector('#comparison-note').textContent = descriptions[selected.id];
  }
  for (const c of configurations) {
    const tr = document.createElement('tr'); if (c.id === 'priority') tr.className='highlight';
    for (const v of [c.label, c.latency_ms, c.success_pct.toFixed(1), c.energy_j]) {
      const td=document.createElement('td'); td.textContent=v; tr.append(td);
    }
    document.querySelector('#result-table').append(tr);
  }
  bindChoices('#configuration', render);
}
init().catch(error => { document.querySelector('#comparison-chart').textContent = error.message; });
