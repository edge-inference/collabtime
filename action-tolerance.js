'use strict';
(async () => {
  const root = document.getElementById('tolerance-interactive');
  if (!root) return;
  const fallback = document.querySelector('.tolerance-static');
  const response = await fetch('action-tolerance.json');
  if (!response.ok) return;
  const {workloads} = await response.json();
  const ns = 'http://www.w3.org/2000/svg';
  const values = new Intl.NumberFormat('en-US', {maximumFractionDigits: 2});
  const delays = new Intl.NumberFormat('en-US', {maximumFractionDigits: 1});
  const panels = [];
  const grid = document.createElement('div');
  grid.className = 'ct-grid';
  const status = document.createElement('p');
  status.className = 'ct-a11y';
  status.setAttribute('aria-live', 'polite');
  const palette = {
    nav: 'var(--ct-blue)', navigate: 'var(--ct-blue)', go: 'var(--ct-blue)',
    pick: 'var(--ct-orange)', reach: 'var(--ct-orange)',
    bring: 'var(--ct-teal)', grasp: 'var(--ct-teal)',
    put: 'var(--ct-purple)', place: 'var(--ct-purple)', transport: 'var(--ct-purple)'
  };
  function node(tag, attrs = {}, text) {
    const el = document.createElementNS(ns, tag);
    for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, String(value));
    if (text !== undefined) el.textContent = text;
    return el;
  }
  function marker(shape, x, y, color, size = 3.6) {
    let el;
    if (shape === 'square') el = node('rect', {x:x-size, y:y-size, width:size*2, height:size*2});
    else if (shape === 'triangle') el = node('polygon', {points:`${x},${y-size-1} ${x-size-1},${y+size} ${x+size+1},${y+size}`});
    else if (shape === 'diamond' || shape === 'open') el = node('polygon', {points:`${x},${y-size-1} ${x-size-1},${y} ${x},${y+size+1} ${x+size+1},${y}`});
    else el = node('circle', {cx:x, cy:y, r:size});
    el.setAttribute('fill', shape === 'open' ? 'var(--ct-panel)' : color);
    if (shape === 'open') {
      el.setAttribute('stroke', color);
      el.setAttribute('stroke-width', '1.7');
    }
    return el;
  }
  function styleFor(workload, series, index) {
    const every = /^Every/.test(series.label);
    let color = palette[series.key] || 'var(--ct-ink)';
    if (every) color = 'var(--ct-ink)';
    if (workload.key === 'libero' && series.key === 'reach') color = 'var(--ct-blue)';
    if (workload.key === 'behavior' && series.key === 'place') color = 'var(--ct-grey)';
    return {color, shape: every ? 'open' : ['circle','square','triangle','diamond'][index % 4], dash:every};
  }
  function hideTooltip(panel) {
    panel.tooltip.hidden = true;
    panel.pinned = false;
  }
  function measuredAt(panel, x) {
    return panel.w.series.filter(s => !panel.hidden.has(s.key)).flatMap(series => {
      // The source rounds the LeKiwi Every series to tenths of a millisecond.
      const point = series.points.find(p => Math.abs(p.x - x) < 0.1);
      return point ? [{series, point}] : [];
    });
  }
  function showTooltip(panel, x, anchor) {
    const rows = measuredAt(panel, x);
    if (!rows.length) return hideTooltip(panel);
    panel.tooltip.replaceChildren();
    const heading = document.createElement('strong');
    heading.textContent = `${delays.format(x)} ms action chunk delay`;
    panel.tooltip.append(heading);
    for (const {series, point} of rows) {
      const row = document.createElement('div'); row.className = 'ct-tooltip-row';
      const label = document.createElement('span'); label.textContent = series.label;
      const value = document.createElement('span');
      value.textContent = values.format(point.y) + (panel.w.yLabel.includes('%') ? '%' : '');
      row.append(label, value); panel.tooltip.append(row);
    }
    panel.tooltip.hidden = false;
    const bounds = panel.section.getBoundingClientRect();
    const size = panel.tooltip.getBoundingClientRect();
    const left = Math.max(8, Math.min(anchor.x - bounds.left + 12, bounds.width - size.width - 8));
    const top = Math.max(8, Math.min(anchor.y - bounds.top + 14, bounds.height - size.height - 8));
    panel.tooltip.style.left = `${left}px`;
    panel.tooltip.style.top = `${top}px`;
  }
  function draw(panel) {
    const {w, svg, buttons, hidden} = panel;
    const width = svg.getBoundingClientRect().width;
    if (!width) return;
    hideTooltip(panel);
    const height = 236, left = 35, right = 14, top = 16, bottom = 51;
    const xMax = Math.ceil(w.xMax), yMax = w.yDomain[1];
    const px = x => left + x / xMax * (width - left - right);
    const py = y => height - bottom - y / yMax * (height - top - bottom);
    svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
    svg.replaceChildren(node('title', {}, `${w.title}: ${w.yLabel} by action chunk delay`));
    svg.append(node('line', {x1:left, y1:top, x2:left, y2:height-bottom, class:'ct-axis'}),
      node('line', {x1:left, y1:height-bottom, x2:width-right, y2:height-bottom, class:'ct-axis'}));
    const ticks = w.key === 'lekiwi' ? [0,133,267] : w.key === 'libero' ? [0,150,300,450] : [0,100,200,300,400];
    for (const x of ticks) {
      svg.append(node('line', {x1:px(x), x2:px(x), y1:height-bottom, y2:height-bottom+4, class:'ct-axis'}),
        node('text', {x:px(x), y:height-bottom+20, 'text-anchor':'middle'}, x));
    }
    for (const y of yMax > 10 ? [0,50,100] : [0,1,2,3]) {
      svg.append(node('line', {x1:left-4, x2:left, y1:py(y), y2:py(y), class:'ct-axis'}),
        node('text', {x:left-9, y:py(y)+4, 'text-anchor':'end'}, y));
    }
    svg.append(node('text', {x:(left+width-right)/2, y:height-4, 'text-anchor':'middle'}, 'Action chunk delay (ms)'));
    const visiblePoints = [];
    w.series.forEach((series, index) => {
      buttons[index].setAttribute('aria-pressed', String(!hidden.has(series.key)));
      if (hidden.has(series.key)) return;
      const style = styleFor(w, series, index);
      const group = node('g', {'data-series':series.key, 'aria-hidden':'true'});
      const line = node('polyline', {points:series.points.map(p => `${px(p.x)},${py(p.y)}`).join(' '), class:'ct-series-line', stroke:style.color});
      if (style.dash) line.setAttribute('stroke-dasharray', '5 4');
      group.append(line);
      series.points.forEach(point => {
        const mark = marker(style.shape, px(point.x), py(point.y), style.color);
        mark.setAttribute('data-point', `${point.x},${point.y}`);
        group.append(mark); visiblePoints.push(point.x);
      });
      svg.append(group);
    });
    // One target per measured delay exposes overlapping observations together.
    const stops = [...new Set(visiblePoints)].sort((a,b) => a-b).filter((x,i,a) => !i || x-a[i-1] >= 0.1);
    for (let i = 0; i < stops.length; i++) {
      const x = stops[i];
      const start = i ? (px(stops[i-1])+px(x))/2 : left-6;
      const end = i < stops.length-1 ? (px(x)+px(stops[i+1]))/2 : width-right+6;
      const descriptions = measuredAt(panel, x).map(({series,point}) => `${series.label}: ${values.format(point.y)} ${w.yLabel.toLowerCase()}`);
      const hit = node('rect', {x:start, y:top-6, width:end-start, height:height-bottom-top+12, class:'ct-hit', tabindex:0, role:'button', 'data-delay':x,
        'aria-label':`${delays.format(x)} ms. ${descriptions.join('; ')}`, 'aria-describedby':panel.tooltip.id});
      const anchor = event => {
        if (event && Number.isFinite(event.clientX)) return {x:event.clientX, y:event.clientY};
        const rect = svg.getBoundingClientRect();
        return {x:rect.left+px(x), y:rect.top+top+18};
      };
      hit.addEventListener('pointermove', event => { if (!panel.pinned) showTooltip(panel, x, anchor(event)); });
      hit.addEventListener('pointerleave', () => { if (!panel.pinned && document.activeElement !== hit) hideTooltip(panel); });
      hit.addEventListener('focus', () => showTooltip(panel, x, anchor()));
      hit.addEventListener('blur', () => hideTooltip(panel));
      hit.addEventListener('click', event => {
        const wasPinned = panel.pinned;
        panels.forEach(hideTooltip);
        if (!wasPinned) { showTooltip(panel, x, anchor(event)); panel.pinned = true; }
      });
      hit.addEventListener('keydown', event => {
        if (event.key === 'Escape') hideTooltip(panel);
        if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); showTooltip(panel, x, anchor()); }
      });
      svg.append(hit);
    }
  }
  workloads.forEach(w => {
    const section = document.createElement('section'); section.className = 'ct-panel';
    const h = document.createElement('h3'); h.textContent = w.title.split(' · ')[0] + ' ';
    h.id = `tolerance-${w.key}-title`; section.setAttribute('aria-labelledby', h.id);
    const policy = document.createElement('span'); policy.textContent = '· ';
    if (w.key === 'fetch') policy.append('SmolVLA');
    else {
      const pi = document.createElement('span'); pi.className = 'ct-pi'; pi.append('π');
      const sub = document.createElement('sub'); sub.textContent = '0.5'; pi.append(sub); policy.append(pi);
    }
    h.append(policy);
    const unit = document.createElement('p'); unit.className = 'ct-unit'; unit.textContent = w.yLabel;
    const svg = node('svg', {class:'ct-plot', role:'group', 'aria-label':`${w.title}, ${w.yLabel} versus action chunk delay`});
    const legend = document.createElement('div'); legend.className = 'ct-legend';
    legend.setAttribute('role', 'group'); legend.setAttribute('aria-label', `${w.title} series`);
    const tooltip = document.createElement('div'); tooltip.className = 'ct-tooltip'; tooltip.hidden = true;
    tooltip.id = `tolerance-${w.key}-tooltip`; tooltip.setAttribute('role', 'tooltip');
    const panel = {w, section, svg, tooltip, buttons:[], hidden:new Set(), pinned:false};
    panels.push(panel);
    w.series.forEach((series,index) => {
      const style = styleFor(w, series, index);
      const button = document.createElement('button'); button.type = 'button'; button.className = 'ct-key';
      button.setAttribute('aria-pressed','true'); button.setAttribute('aria-label', `${series.label}, ${w.title.split(' · ')[0]}`);
      const swatch = node('svg', {viewBox:'0 0 23 14', 'aria-hidden':'true'});
      const line = node('line', {x1:1, x2:22, y1:7, y2:7, stroke:style.color, 'stroke-width':2});
      if (style.dash) line.setAttribute('stroke-dasharray','5 4');
      swatch.append(line, marker(style.shape,11,7,style.color,3)); button.append(swatch, document.createTextNode(series.label));
      button.addEventListener('click', () => {
        panel.hidden.has(series.key) ? panel.hidden.delete(series.key) : panel.hidden.add(series.key);
        draw(panel);
        status.textContent = `${w.title.split(' · ')[0]}: ${series.label} ${panel.hidden.has(series.key) ? 'hidden' : 'shown'}.`;
      });
      panel.buttons.push(button); legend.append(button);
    });
    section.append(h,unit,svg,legend,tooltip); grid.append(section);
  });
  root.append(grid,status); root.hidden = false; fallback.hidden = true;
  const render = () => panels.forEach(draw);
  let previousWidth;
  new ResizeObserver(entries => {
    const width = entries[0].contentRect.width;
    if (width !== previousWidth) { previousWidth = width; render(); }
  }).observe(root);
  document.addEventListener('pointerdown', event => {
    panels.forEach(panel => { if (!panel.svg.contains(event.target)) hideTooltip(panel); });
  });
  render();
})().catch(error => {
  console.error('Action-delay chart could not load:', error);
  const root = document.getElementById('tolerance-interactive');
  if (root) root.hidden = true;
  const fallback = document.querySelector('.tolerance-static');
  if (fallback) fallback.hidden = false;
});
