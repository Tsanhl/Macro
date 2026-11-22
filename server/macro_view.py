"""Regroups the macro board's page (macro/index.html, served on 8766) as it is served. macro/ is never edited.

Three pages:
  宏觀  one scrolling page (reorganised 2026-11-22, user): 現在要看 (data dates, the transmission chain, four
        conclusions, the market state and 之後要看) and AI 拋售：半導體與避險資產 in section rbmacro; then the dashboard's
        breadth section (advance-decline line with SPY and the McClellan oscillator; the 50-day share chart is hidden);
        then section rbmacro2 with 信用總表, 美債, 股債波動 and 資金 (TGA and net liquidity); and, at the bottom, the
        dashboard's relative rotation graph. The macro_summary cards are drawn by RB_JS below; the two dashboard sections
        are styled as single cards like the others, each with its heading and one data line from macro_summary.
  美國經濟  growth, labour, inflation, consumers, housing, fiscal and financial conditions from FRED
        (server/us_economy_view.py, data from macro/us_economy.py): a table and small charts per section, data only.
  油價  the 油市總結 (macro_summary.oil_summary), then the dashboard's oil page with these changes: its curve card is
        replaced by the Brent curve card (latest, week-earlier and month-earlier curves by contract month, and the four
        spreads with their sentences), the OVX card gets its implication lines, the five-contract managed-money card
        follows the inventory card, and the 戰事最新進展 card sits to the right of the 事件機率 card (below it on narrow
        screens). The Brent price chart and the dashboard's 基金持倉及資金流 card (#oil-funds-card: ICE Brent and CFTC
        WTI lots, which the 油市總結 states, and hand-kept ETF flows) are not shown.
The dashboard page's own header (its 板塊輪動, 市寬 and 油價 tabs) is replaced, and the 更新數據 button and source dates stay.
The 新聞與連接 and AI 追蹤 pages are separate (pages.py). The page takes the institutional board's look (STYLE below).
"""
import json
import re

import us_economy_view

GROUPS = {"overview": ["rbmacro", "breadth", "rbmacro2", "rotation"], "useco": ["useco"], "oil": ["oil"]}
DRAW = GROUPS
HIDE = ["#update-status", "#oil-curve-card", "#oil-funds-card", "#oil-ovx-reading", "#card-pctabove"]
# #oil-ovx-reading says what the OVX lines already say
HIDE_HAS = "#rotation .rb-seg:has(.rb-grp)"  # the universe switch: sectors only (own rule, so an old browser skips just this)

NAV = """<nav class="rb-tabs" role="tablist" aria-label="頁面" data-en-aria="Pages">
      <button type="button" role="tab" id="tab-overview" data-page="overview" aria-selected="true" data-en="Macro">宏觀</button>
      <button type="button" role="tab" id="tab-oil" data-page="oil" aria-selected="false" data-en="Oil">油價</button>
      <button type="button" role="tab" id="tab-useco" data-page="useco" aria-selected="false" data-en="US economy">美國經濟</button>
    </nav>"""

# Draws the new charts with the dashboard's own lineChart (inside its script, so the same tooltips and colours).
RB_JS = """  function drawRbMacro() {
    const c = colors(), el = (id) => document.getElementById(id);
    const since = (rows, days) => { if (!rows.length) return rows; const cut = +day(rows.at(-1).date) - days * 864e5; return rows.filter((r) => +day(r.date) >= cut); };
    const draw = (id, series, opts) => {
      const e = el(id); if (!e) return;
      if (!series[0].values.length) { e.replaceChildren(); return; }
      lineChart(e, { series, height: 200, ...opts });
    };
    const yi = (v) => d3.format(',.0f')(v) + ' 億美元';
    const mw = status(['macro_watch']) === 'ok' ? dash.data('macro_watch').data[0] : null;
    if (mw && mw.tga && mw.tga.rows) draw('ch-rb-tga', [{ name: 'TGA', color: c[0], values: since(mw.tga.rows, 183).map((r) => ({ d: day(r.date), v: r.bn * 10 })) }], { yFmt: d3.format(','), tipFmt: yi });
    if (mw && mw.move && mw.move.rows) draw('ch-rb-move', [{ name: 'MOVE', color: c[0], values: since(mw.move.rows, 183).map((r) => ({ d: day(r.date), v: r.v })) }], { yFmt: d3.format('d'), tipFmt: (v) => v.toFixed(1) });
    if (status(['liquidity']) === 'ok') {
      const rows = since(dash.data('liquidity').data.filter((r) => r.net_liq != null), 183);
      draw('ch-rb-liq', [{ name: '淨流動性', color: c[0], values: rows.map((r) => ({ d: day(r.date), v: r.net_liq * 10 })) }], { yFmt: d3.format(','), tipFmt: yi });
    }
    if (status(['ratios']) === 'ok') {
      const rows = since(dash.data('ratios').data.filter((r) => r.pair === 'SMH_SPY'), 183);
      draw('ch-rb-smh', [{ name: 'SMH ÷ SPY', color: c[0], values: rows.map((r) => ({ d: day(r.date), v: r.value })) },
        { name: '50 日均線', color: 'var(--cds-chart-muted)', dash: true, values: rows.map((r) => ({ d: day(r.date), v: r.sma50 })) }], { yFmt: d3.format('d'), tipFmt: fmt1 });
    }
    if (status(['rates']) === 'ok') {
      const rows = since(dash.data('rates').data.filter((r) => r.nominal10 != null && r.nominal2 != null), 183);
      const pc = (v) => v.toFixed(2) + '%';
      draw('ch-rb-yields', [{ name: '10 年期', color: c[0], values: rows.map((r) => ({ d: day(r.date), v: r.nominal10 })) },
        { name: '2 年期', color: c[1], values: rows.map((r) => ({ d: day(r.date), v: r.nominal2 })) }], { yFmt: d3.format('.1f'), tipFmt: pc });
      draw('ch-rb-curve', [{ name: '10 年減 2 年', color: c[0], values: rows.map((r) => ({ d: day(r.date), v: Math.round((r.nominal10 - r.nominal2) * 100) })) }],
        { yFmt: d3.format('d'), tipFmt: (v) => v.toFixed(0) + ' 基點', ref: 0 });
    }
    // 避險資產對 AI 拋售: 63-session correlation with QQQ over the last year, two panels of three (macro_summary.HAVEN_CHARTS)
    const ca = status(['cross_asset']) === 'ok' ? dash.data('cross_asset').data[0] : null;
    const hr = ca && ca.havens && ca.havens.roll;
    if (ca && ca.havens && ca.havens.rows) {
      const e = el('ch-rb-havenbar');
      if (e) rbCorrBars(e, ca.havens.rows.filter((r) => r.corr != null), +(2 / Math.sqrt(ca.havens.window || 63)).toFixed(2));
    }
    if (hr && hr.dates) {
      const nm = Object.fromEntries((ca.havens.rows || []).map((r) => [r.t, r.name]));
      const sgn = (v) => (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(2);
      for (const [id, ts] of [['ch-rb-haven1', ['GLD', 'UUP', 'FXY']], ['ch-rb-haven2', ['SHY', 'IEF', 'XLP']]]) {
        const series = ts.map((t, i) => ({ name: nm[t] || t, color: c[i], values: (hr[t] || []).map((v, k) => ({ d: day(hr.dates[k]), v })) }))
          .filter((s) => s.values.length);
        if (series.length) draw(id, series, { yFmt: (v) => (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(1), tipFmt: sgn, ref: 0, yDomain: [-1, 1] });
      }
    }
  }

  // 油價: the Brent curve by contract month (latest, a week and a month earlier) and managed money in five oil contracts
  function rbCurveChart(el, lines, height = 230) {
    el.replaceChildren();
    const months = [...new Set(lines.flatMap((l) => l.pts.map((p) => p.m)))].sort();
    if (months.length < 2) return;
    const W = Math.max(el.clientWidth, 280), H = height, mt = 8, mb = 22;
    const svg = d3.select(el).append('svg').attr('class', 'rb-svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`);
    const y = d3.scaleLinear(d3.extent(lines.flatMap((l) => l.pts.map((p) => p.v))), [H - mb, mt]).nice(4);
    const ticks = y.ticks(4), yFmt = (v) => '$' + v.toFixed(0);
    const ml = measure(svg, ticks.map(yFmt)) + 8;
    const md = (m) => new Date(Date.UTC(+m.slice(0, 4), +m.slice(5, 7) - 1, 1));  // delivery month on a time axis, so gaps keep their length
    const x0 = d3.scaleUtc([md(months[0]), md(months.at(-1))], [ml + 10, W - 24]), x = (m) => x0(md(m));
    svg.append('g').selectAll('line').data(ticks).join('line').attr('class', 'rb-gridline').attr('x1', ml).attr('x2', W - 6).attr('y1', (t) => y(t)).attr('y2', (t) => y(t));
    svg.append('g').selectAll('text').data(ticks).join('text').attr('x', ml - 6).attr('y', (t) => y(t)).attr('dy', '0.32em').attr('text-anchor', 'end').text(yFmt);
    let lastX = -1e9;
    const shown = months.filter((m, i) => { const ok = x(m) - lastX >= 58 || i === months.length - 1 && x(m) - lastX >= 40; if (ok) lastX = x(m); return ok; });
    svg.append('g').selectAll('text').data(shown).join('text').attr('x', (m) => x(m)).attr('y', H - 4).attr('text-anchor', 'middle').text((m) => m);
    for (const l of lines) {
      svg.append('path').attr('d', d3.line().x((p) => x(p.m)).y((p) => y(p.v))(l.pts)).attr('fill', 'none').attr('stroke', l.color)
        .attr('stroke-width', l.dash ? 1.5 : 2).attr('stroke-dasharray', l.dash ? '4 3' : null).attr('stroke-linejoin', 'round');
      svg.append('g').selectAll('circle').data(l.pts).join('circle').attr('cx', (p) => x(p.m)).attr('cy', (p) => y(p.v)).attr('r', l.dash ? 2 : 2.5).attr('fill', l.color);
    }
    const rule = svg.append('line').attr('class', 'rb-axis').attr('y1', mt).attr('y2', H - mb).attr('opacity', 0);
    svg.append('rect').attr('x', ml).attr('y', mt).attr('width', W - 6 - ml).attr('height', H - mb - mt).attr('fill', 'transparent')
      .on('pointermove', (event) => {
        const [mx] = d3.pointer(event);
        const m = months.reduce((a, b) => (Math.abs(x(b) - mx) < Math.abs(x(a) - mx) ? b : a));
        rule.attr('x1', x(m)).attr('x2', x(m)).attr('opacity', 1);
        showTip(event, m + ' 合約', lines.map((l) => { const q = l.pts.find((r) => r.m === m); return { color: l.color, text: `${l.name}  ${q ? '$' + q.v.toFixed(2) : '—'}` }; }));
      })
      .on('pointerleave', () => { rule.attr('opacity', 0); hideTip(); });
  }

  function rbPosChart(el, rows, height = 250) {
    el.replaceChildren();
    const c = colors(), mb1 = (v) => d3.format(',.1f')(v) + ' 百萬桶';
    const pts = rows.map((r) => ({ d: day(r.date), L: r.long, S: -r.short, N: r.net }));
    if (pts.length < 2) return;
    const W = Math.max(el.clientWidth, 280), H = height, mt = 8, mb = 22;
    const svg = d3.select(el).append('svg').attr('class', 'rb-svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`);
    const y = d3.scaleLinear([d3.min(pts, (p) => Math.min(p.S, p.N)), d3.max(pts, (p) => Math.max(p.L, p.N))], [H - mb, mt]).nice(8);
    const ticks = y.ticks(5), yFmt = d3.format(',');
    const ml = measure(svg, ticks.map(yFmt)) + 8;
    const x = d3.scaleUtc(d3.extent(pts, (p) => p.d), [ml, W - 6]);
    svg.append('g').selectAll('line').data(ticks).join('line').attr('class', 'rb-gridline').attr('x1', ml).attr('x2', W - 6).attr('y1', (t) => y(t)).attr('y2', (t) => y(t));
    svg.append('g').selectAll('text').data(ticks).join('text').attr('x', ml - 6).attr('y', (t) => y(t)).attr('dy', '0.32em').attr('text-anchor', 'end').text(yFmt);
    svg.append('g').selectAll('text').data(x.ticks(W < 520 ? 4 : 8)).join('text').attr('x', (t) => x(t)).attr('y', H - 4).attr('text-anchor', 'middle').text(d3.utcFormat('%Y'));
    svg.append('path').attr('d', d3.area().x((p) => x(p.d)).y0(y(0)).y1((p) => y(p.L))(pts)).attr('fill', c[0]).attr('fill-opacity', 0.3);
    svg.append('path').attr('d', d3.area().x((p) => x(p.d)).y0(y(0)).y1((p) => y(p.S))(pts)).attr('fill', c[1]).attr('fill-opacity', 0.3);
    svg.append('line').attr('class', 'rb-axis').attr('x1', ml).attr('x2', W - 6).attr('y1', y(0)).attr('y2', y(0));
    svg.append('path').attr('d', d3.line().x((p) => x(p.d)).y((p) => y(p.N))(pts)).attr('fill', 'none').attr('stroke', 'var(--color-fg)').attr('stroke-width', 1.5).attr('stroke-linejoin', 'round');
    const last = pts.at(-1);
    svg.append('circle').attr('cx', x(last.d)).attr('cy', y(last.N)).attr('r', 3).attr('fill', 'var(--color-fg)');
    const rule = svg.append('line').attr('class', 'rb-axis').attr('y1', mt).attr('y2', H - mb).attr('opacity', 0);
    const dot = svg.append('circle').attr('r', 3.5).attr('fill', 'var(--color-fg)').attr('opacity', 0);
    const bis = d3.bisector((p) => p.d).center;
    svg.append('rect').attr('x', ml).attr('y', mt).attr('width', W - 6 - ml).attr('height', H - mb - mt).attr('fill', 'transparent')
      .on('pointermove', (event) => {
        const p = pts[bis(pts, x.invert(d3.pointer(event)[0]))];
        rule.attr('x1', x(p.d)).attr('x2', x(p.d)).attr('opacity', 1);
        dot.attr('cx', x(p.d)).attr('cy', y(p.N)).attr('opacity', 1);
        showTip(event, d3.utcFormat('%Y-%m-%d')(p.d) + ' 持倉', [{ color: c[0], text: 'long  ' + mb1(p.L) }, { color: c[1], text: 'short  ' + mb1(-p.S) },
          { color: 'var(--color-fg)', text: '淨額  ' + mb1(p.N) }]);
      })
      .on('pointerleave', () => { rule.attr('opacity', 0); dot.attr('opacity', 0); hideTip(); });
  }

  // 避險資產對 AI 拋售: each asset's current 63-session correlation with QQQ as a bar from zero (orange = with the Nasdaq,
  // blue = against it), the ±band within which a reading cannot be told apart from zero shaded grey, the five-year
  // median as a short vertical line, values in a right-hand column, and a tooltip per row.
  function rbCorrBars(el, rows, band) {
    el.replaceChildren();
    if (!rows.length) return;
    const c = colors(), rowH = 30, mt = 6, mb = 24;
    const W = Math.max(el.clientWidth, 280), H = mt + mb + rowH * rows.length;
    const svg = d3.select(el).append('svg').attr('class', 'rb-svg').attr('width', '100%').attr('viewBox', `0 0 ${W} ${H}`);
    const sgn = (v) => (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(2);
    const ml = Math.min(measure(svg, rows.map((r) => r.name)) + 12, W * 0.42), mr = 52;
    const x = d3.scaleLinear([-1, 1], [ml, W - mr]), y = (i) => mt + i * rowH + rowH / 2, bot = mt + rowH * rows.length;
    svg.append('rect').attr('x', x(-band)).attr('width', x(band) - x(-band)).attr('y', mt).attr('height', bot - mt).attr('fill', 'var(--grid)');
    const ticks = [-1, -0.5, 0, 0.5, 1];
    svg.append('g').selectAll('line').data(ticks).join('line').attr('class', (t) => (t === 0 ? 'rb-axis' : 'rb-gridline'))
      .attr('x1', (t) => x(t)).attr('x2', (t) => x(t)).attr('y1', mt).attr('y2', bot);
    svg.append('g').selectAll('text').data(ticks).join('text').attr('x', (t) => x(t)).attr('y', H - 6).attr('text-anchor', 'middle')
      .text((t) => (t === 0 ? '0' : (t > 0 ? '+' : '−') + Math.abs(t).toFixed(1)));
    svg.append('g').selectAll('text').data(rows).join('text').attr('x', ml - 8).attr('y', (r, i) => y(i)).attr('dy', '0.32em')
      .attr('text-anchor', 'end').text((r) => r.name);
    const bh = 12;
    svg.append('g').selectAll('rect').data(rows).join('rect').attr('x', (r) => x(Math.min(0, r.corr)))
      .attr('width', (r) => Math.max(1, Math.abs(x(r.corr) - x(0)))).attr('y', (r, i) => y(i) - bh / 2).attr('height', bh).attr('rx', 3)
      .attr('fill', (r) => (r.corr >= 0 ? c[1] : c[0]));
    svg.append('g').selectAll('line').data(rows.map((r, i) => ({ ...r, i })).filter((r) => r.corr_med5y != null)).join('line')
      .attr('x1', (r) => x(r.corr_med5y)).attr('x2', (r) => x(r.corr_med5y)).attr('y1', (r) => y(r.i) - 10).attr('y2', (r) => y(r.i) + 10)
      .attr('stroke', 'var(--color-fg)').attr('stroke-width', 2).attr('stroke-linecap', 'round');
    svg.append('g').selectAll('text').data(rows).join('text').attr('x', W - 4).attr('y', (r, i) => y(i)).attr('dy', '0.32em')
      .attr('text-anchor', 'end').attr('fill', 'var(--color-fg)').text((r) => sgn(r.corr));
    const word = (v) => (v >= band ? '同向' : v <= -band ? '反向' : '沒有可靠關係');
    svg.append('g').selectAll('rect').data(rows).join('rect').attr('x', 0).attr('width', W).attr('y', (r, i) => y(i) - rowH / 2).attr('height', rowH)
      .attr('fill', 'transparent')
      .on('pointermove', (event, r) => showTip(event, r.name, [
        { color: r.corr >= 0 ? c[1] : c[0], text: `現在  ${sgn(r.corr)}（${word(r.corr)}）` },
        { color: 'var(--cds-chart-muted)', text: `約六個月前  ${r.corr_6m == null ? '—' : sgn(r.corr_6m)}` },
        { color: 'var(--color-fg)', text: `五年中位  ${r.corr_med5y == null ? '—' : sgn(r.corr_med5y)}` }]))
      .on('pointerleave', () => hideTip());
  }

  function drawRbOil() {
    const c = colors(), el = (id) => document.getElementById(id);
    const oil = status(['oil']) === 'ok' ? dash.data('oil').data[0] : null;
    if (!oil) return;
    try {
      const lines = (oil.curve && oil.curve.lines) || {}, e = el('ch-rb-oilcurve');
      if (e && lines.latest) {
        rbCurveChart(e, [['latest', '最新', c[0], false], ['week', '一週前', c[1], false], ['month', '一個月前', 'var(--cds-chart-muted)', true]]
          .filter(([k]) => lines[k]).map(([k, name, color, dash]) => ({ name: `${name}（${lines[k].date}）`, color, dash,
            pts: Object.entries(lines[k].px).filter(([, v]) => v != null).map(([m, v]) => ({ m, v })).sort((a, b) => a.m.localeCompare(b.m)) })));
      }
    } catch (err) { console.error('oil curve chart', err); }
    try {
      const rows = (oil.positions && oil.positions.rows) || [], e = el('ch-rb-oilpos');
      if (e && rows.length) rbPosChart(e, rows);
    } catch (err) { console.error('oil positions chart', err); }
  }

"""

# Headings and notes of the two dashboard sections come from macro_summary (rotation_head, breadth_head) and are put in
# place of these markers by regroup().
ROTATION_HEAD = "<!--RB-ROTATION-HEAD-->"
BREADTH_HEAD = "<!--RB-BREADTH-HEAD-->"

# (exact source text, replacement). A missing text means the dashboard's page changed: see regroup().
PATCHES = [
    ('id="ch-ad" data-source="breadth" style="min-height: 13rem"></div>\n      </div>',
     'id="ch-ad" data-source="breadth" style="min-height: 13rem"></div>\n      </div>\n      <div class="rb-card" id="card-mcc">\n        <h2 class="rb-h2" data-en="McClellan oscillator">麥克連振盪指標</h2>\n        <p class="rb-sub" data-en="19-day minus 39-day exponential average of (advancers − decliners) ÷ (advancers + decliners), × 1,000. Above 0: advancers have led lately; below 0: decliners.">每日（上升 − 下跌）÷（上升 + 下跌）的 19 日指數平均減 39 日指數平均，乘 1,000。0 以上＝近期上升股數佔優，0 以下＝下跌股數佔優。</p>\n        <div class="rb-chart" id="ch-rb-mcc" style="min-height: 13rem"></div>\n      </div>'),
    ("lineChart(els[1], { series: adSeries, height: 240, yFmt: d3.format(','), tipFmt: d3.format(','), yRightFmt: fmt1 });",
     "lineChart(els[1], { series: adSeries, height: 240, yFmt: d3.format(','), tipFmt: d3.format(','), yRightFmt: fmt1 });\n      const mel = document.getElementById('ch-rb-mcc');\n      if (mel) lineChart(mel, { series: [{ name: L('麥克連振盪指標', 'McClellan oscillator'), color: c[0], values: b.map((r) => ({ d: r.d, v: r.mcclellan })) }],\n        height: 240, ref: 0, yFmt: d3.format(','), tipFmt: (v) => v.toFixed(1) });"),
    ("const on = p.id === page;", "const on = (window.RB_GROUPS[page] || [page]).includes(p.id);"),
    ("if (on && !state.shown.has(page)) { state.shown.add(page); p.classList.add('rb-in'); }", ""),
    ("if (state.page === 'oil') drawOil();",
     "if (RB_ON('rbmacro')) drawRbMacro();\n    if (RB_ON('useco')) drawRbUsEco();\n    if (RB_ON('oil')) { try { drawOil(); } catch (e) { console.error(e); } drawRbOil(); }"),
    ("if (state.page === 'rotation') {", "if (RB_ON('rotation')) {"),
    ("if (state.page === 'breadth') drawBreadth();", "if (RB_ON('breadth')) drawBreadth();"),
    ("const PAGES = ['rotation', 'breadth', 'oil'];",
     "const RB_ON = (p) => (window.RB_DRAW[state.page] || [state.page]).includes(p);\n  const PAGES = ['overview', 'oil', 'useco'];"),
    ("showPage(PAGES.includes(start) ? start : 'rotation', false);",
     "showPage(PAGES.includes(start) ? start : 'overview', false);"),
    # 美國經濟 charts span up to ten years: one label a year (two on narrow charts) instead of every few months
    ("const xt = days > 60 ? x.ticks(", "const xt = days > 1500 ? x.ticks(d3.utcYear.every(W < 520 ? 2 : 1)) : days > 60 ? x.ticks("),
    ("  function drawAll() {", RB_JS + us_economy_view.JS + "  function drawAll() {"),
    ('data-en="Sector rotation &amp; market breadth">板塊輪動與市寬<', 'data-en="Macro">宏觀<'),
    ("<title>板塊輪動與市寬</title>", "<title>宏觀</title>"),
    ('<section class="rb-page" id="rotation" role="tabpanel" aria-labelledby="tab-rotation" hidden>',
     '<section class="rb-page" id="rotation" role="tabpanel" aria-labelledby="tab-overview" hidden>\n    ' + ROTATION_HEAD),
    ('<section class="rb-page" id="breadth" role="tabpanel" aria-labelledby="tab-breadth" hidden>',
     '<section class="rb-page" id="breadth" role="tabpanel" aria-labelledby="tab-overview" hidden>\n    ' + BREADTH_HEAD),
]
OIL_OPEN = '<section class="rb-page" id="oil" role="tabpanel" aria-labelledby="tab-oil" hidden>'
ROTATION_OPEN = '<section class="rb-page" id="rotation"'
# where the oil page's new cards go (the dashboard's curve card stays in the page, hidden by HIDE)
OIL_CURVE_AT = '<div class="rb-card" id="oil-curve-card">'
OVX_AT = '<p class="rb-take-line" id="oil-ovx-reading"></p>'
POSITIONS_AT = '<div class="rb-card" id="oil-options-card">'
ODDS_OPEN = '<div class="rb-card" id="oil-odds-card">'
ODDS_CLOSE = '<p class="rb-sub" id="oil-gaps"></p>\n      </div>'


# The institutional board's look (institutional/index.html): its palette and system font, flat cards with a thin
# border, compact tables with sub-heading rows, and bordered buttons for tabs and switches. The dashboard's colour and
# font tokens are redefined for the whole page; component rules carry the #rb-wrap id so they win over the dashboard's
# own stylesheet, which comes later in the page. Light and dark are chosen as on the institutional board: the reader's
# prefers-color-scheme, overridable with data-theme="light" or "dark" on <html>. Each palette sets every colour token the
# page uses, so the dashboard's own light/dark tokens never leak into the other palette.
DARK = """color-scheme: dark;
  --surface: #1a1a19; --surface-2: #232321; --line: #383835; --grid: #2c2c2a; --ink: #f0efec; --ink-2: #c3c2b7; --ink-3: #8f8e86;
  --s1: #3987e5; --s2: #d95926; --cds-chart-axis: #4a4945; --cds-chart-muted: #6a6964;
  --color-warn: #e39a4a; --cds-shadow-popover: 0 6px 20px rgba(0, 0, 0, .5);
  --series-3: #9a80e6; --series-4: #3cc2b0; --series-5: #ea6fa5; --series-6: #9bc24a; --series-7: #c9a24a; --series-8: #86a5d6;"""
STYLE = """
:root { color-scheme: light;
  --surface: #fcfcfb; --surface-2: #f4f3f0; --line: #e2e1dc; --grid: #ecebe7; --ink: #0b0b0b; --ink-2: #52514e; --ink-3: #7c7b76;
  --s1: #2a78d6; --s2: #eb6834; --good: #0ca30c; --bad: #d03b3b;
  --font-anthropic-sans: -apple-system, BlinkMacSystemFont, "PingFang TC", "Noto Sans TC", "Helvetica Neue", sans-serif;
  --font-anthropic-serif: var(--font-anthropic-sans);
  --cds-font-size-caption: 13px; --cds-font-size-body: 14px; --cds-font-size-heading: 15px; --cds-font-size-title: 22px;
  --color-bg: var(--surface); --color-panel: var(--surface); --color-fg: var(--ink); --color-fg-muted: var(--ink-2);
  --color-border-line: var(--line); --cds-border: var(--line); --cds-text-secondary: var(--ink-2); --cds-surface-popover: var(--surface);
  --color-ok: var(--good); --color-bad: var(--bad); --color-warn: #b0600c; --cds-shadow-popover: 0 6px 20px rgba(20, 30, 45, .14);
  --cds-chart-grid: var(--grid); --cds-chart-axis: #c9c8c2; --cds-chart-reference: var(--ink-3); --cds-chart-muted: #a9a8a2;
  --series-1: var(--s1); --series-2: var(--s2);
  --series-3: #7b5cd6; --series-4: #179c8c; --series-5: #c43f7b; --series-6: #6c8f1f; --series-7: #8d6b1c; --series-8: #4b6fa6; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { __DARK__ } }
:root[data-theme="dark"] { __DARK__ }
body { background: var(--surface); color: var(--ink); font-size: 14px; line-height: 1.55; }
#rb-wrap .rb-divider { border-top-color: var(--line); }
#dash-root { padding: 20px 16px 12px; }
#rb-wrap { max-width: 1400px; }
.site-foot { max-width: 1400px; padding: 8px 16px 32px; font-size: 12px; color: var(--ink-3); }
#rb-wrap .rb-head { margin-block-end: 0; }
#rb-wrap .rb-title { font-family: var(--font-anthropic-sans); font-size: 24px; font-weight: 500; }
#rb-wrap .rb-tabs { gap: 6px; border-block-end: 0; margin: 16px 0 14px; }
#rb-wrap .rb-tabs button, #rb-wrap .rb-refresh, #rb-wrap .rb-seg button, #rb-wrap .rb-seg button + button {
  font: inherit; color: var(--ink); background: var(--surface-2); border: 1px solid var(--line); border-radius: 6px; padding: 5px 14px; margin: 0; cursor: pointer; }
#rb-wrap .rb-seg { border: 0; border-radius: 0; overflow: visible; gap: 6px; }
#rb-wrap .rb-seg button, #rb-wrap .rb-seg button + button { font-size: 13px; padding: 3px 10px; }
#rb-wrap .rb-tabs button[aria-selected="true"], #rb-wrap .rb-seg button[aria-pressed="true"] { border-color: var(--ink-2); font-weight: 600; background: var(--surface-2); }
#rb-wrap button:focus-visible { outline: 2px solid var(--s1); outline-offset: 1px; }
#rb-wrap button:disabled { opacity: .6; cursor: default; }
#rb-wrap .rb-page { gap: 14px; }
#rb-wrap .rb-card, #rb-wrap .rb-tile { background: transparent; border: 1px solid var(--line); border-radius: 8px; padding: 12px 14px; }
#rb-wrap .rb-h2 { font-size: 15px; font-weight: 600; }
#rb-wrap .rb-page > h2.rb-h2 { font-size: 18px; font-weight: 500; margin: 10px 0 0; }
#rb-wrap .rb-tval { font-family: var(--font-anthropic-sans); font-size: 22px; }
#rb-wrap .rb-sub { color: var(--ink-2); font-size: 13px; }
#rb-wrap .rb-tablebox { border: 0; border-radius: 0; }
#rb-wrap .rb-table { font-size: 13px; }
#rb-wrap .rb-table th, #rb-wrap .rb-table td { padding: 4px 6px; border-block-end: 1px solid var(--grid); }
#rb-wrap .rb-table th { font-size: 12px; font-weight: 500; color: var(--ink-2); background: var(--surface); }
#rb-wrap .rb-table tr.rb-sep td { background: transparent; color: var(--ink-3); font-size: 12px; font-weight: 400; padding-top: 8px; border-block-end: 1px solid var(--line); }
#rb-wrap .rb-table tr.rb-muted td { color: var(--ink-3); }
#rb-wrap #rb-summary { background: var(--surface-2); }
#rb-wrap #rb-summary p { margin: 0 0 8px; max-width: 120ch; } #rb-wrap #rb-summary ul { margin: 0 0 8px; padding-left: 20px; }
#rb-wrap .rb-card h3.rb-h2 { font-size: 14px; margin: 0 0 4px; }
#rb-wrap .rb-credit td, #rb-wrap .rb-credit th { text-align: right; } #rb-wrap .rb-credit .rb-left { text-align: left; }
#rb-wrap .rb-num td, #rb-wrap .rb-num th { text-align: right; } #rb-wrap .rb-num .rb-left { text-align: left; }
#rb-wrap .rb-credit tr.rb-hot td { color: var(--bad); font-weight: 700; }
#rb-wrap .rb-chain { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 8px; margin: 6px 0 8px; }
#rb-wrap .rb-node { border: 1px solid var(--line); border-radius: 6px; padding: 8px 10px; background: var(--surface); }
#rb-wrap .rb-node.hot { border: 2px solid var(--bad); }
#rb-wrap .rb-node .t { font-size: 12px; color: var(--ink-2); }
#rb-wrap .rb-node .v { font-size: 15px; font-weight: 600; margin-top: 2px; }
#rb-wrap .rb-node .st { font-size: 13px; color: var(--ink-2); margin-top: 2px; }
#rb-wrap .rb-node .st.worse { color: var(--ink); font-weight: 700; }
#rb-wrap .rb-node.hot .st.worse { color: var(--bad); }
#rb-wrap .rb-node .s { font-size: 12px; color: var(--ink-3); margin-top: 2px; }
#rb-wrap .rb-concl { margin: 4px 0; padding-left: 18px; } #rb-wrap .rb-concl li { margin: 6px 0; }
#rb-wrap .rb-credit tr.rb-sep td { text-align: left; min-width: 0; color: var(--ink); }
#rb-wrap .rb-credit td:last-child { white-space: normal; min-width: 14rem; color: var(--ink-2); }
#rb-wrap .rb-bondt td, #rb-wrap .rb-bondt th { text-align: right; } #rb-wrap .rb-bondt .rb-left { text-align: left; }
#rb-wrap #rotation, #rb-wrap #breadth { border: 1px solid var(--line); border-radius: 8px; padding: 12px 14px; gap: var(--cds-gap-sm); align-content: start; margin-top: 14px; }
#rb-wrap #rotation > h2.rb-h2, #rb-wrap #breadth > h2.rb-h2 { font-size: 15px; font-weight: 600; margin: 0; }
#rb-wrap #rotation > p, #rb-wrap #breadth > p { margin: 0; }
#rb-wrap #rotation .rb-card, #rb-wrap #breadth .rb-card { border: 0; padding: 0; }
#rb-wrap #rotation .rb-card h2.rb-h2, #rb-wrap #breadth .rb-card h2.rb-h2 { font-size: 14px; margin: 0 0 4px; }
#rb-wrap .rb-pair { display: grid; gap: 14px; grid-template-columns: repeat(auto-fit, minmax(min(100%, 22rem), 1fr)); }
#rb-wrap .rb-spreads, #rb-wrap .rb-ladder { margin: 0; padding-left: 20px; display: grid; gap: 6px; }
#rb-wrap .rb-spreads li, #rb-wrap .rb-ladder li { max-width: 120ch; padding: 1px 4px; }
#rb-wrap .rb-ladder li.rb-now { background: var(--surface-2); border-radius: 4px; }
#rb-wrap .rb-war th, #rb-wrap .rb-war td { text-align: left; vertical-align: top; }
#rb-wrap .rb-war td { white-space: normal; } #rb-wrap .rb-war td:first-child { white-space: nowrap; } #rb-wrap .rb-war td.rb-wrap { min-width: 11rem; }
@media (max-width: 600px) { #rb-wrap #rotation, #rb-wrap #breadth { padding: 10px; } }
@media (max-width: 600px) { #rb-wrap .rb-table th, #rb-wrap .rb-table td { padding: 3px 4px; } #rb-wrap .rb-table { font-size: 12px; }
  #rb-wrap .rb-card, #rb-wrap .rb-tile { padding: 10px; } #rb-wrap .rb-credit td:last-child { min-width: 10rem; } }
""".replace("__DARK__", DARK) + us_economy_view.STYLE


def missing_patches(html):
    need = [old for old, _ in PATCHES] + [OIL_OPEN, ROTATION_OPEN, OIL_CURVE_AT, OVX_AT, POSITIONS_AT, ODDS_OPEN, ODDS_CLOSE]
    return [x for x in need if x not in html] + ([] if re.search(r'<nav class="rb-tabs".*?</nav>', html, re.S) else ["nav"])


def regroup(html, parts):
    """The regrouped page; the original page with a visible notice if the source no longer matches.
    parts: {"macro": html of the 宏觀 cards, "rotation_head" and "breadth_head": the heading and note of the rotation and
    breadth sections, "oil": the 油市總結 card, "oil_curve": the Brent curve card, "ovx": the OVX lines, "oil_positions":
    the five-contract managed-money card, "war": the 戰事最新進展 card}."""
    missing = missing_patches(html)
    if missing:
        print("macro view: missing anchors", [m[:60] for m in missing], flush=True)
        notice = '<div style="background:#b3261e;color:#fff;padding:8px 12px">macro 頁面已改動，未能重組，暫時顯示原版。</div>'
        return html.replace("<body>", "<body>" + notice, 1)
    for old, new in PATCHES:
        html = html.replace(old, new, 1)
    html = re.sub(r'<nav class="rb-tabs".*?</nav>', NAV, html, count=1, flags=re.S)
    section = f'<section class="rb-page" id="rbmacro" role="tabpanel" aria-labelledby="tab-overview">\n{parts["macro"]}\n</section>\n  '
    # 市寬 before 板塊輪動 (user, 2026-11-22: the rotation graph goes to the bottom of the page)
    m = re.search(r'<section class="rb-page" id="breadth".*?</section>\s*', html, flags=re.S)
    breadth = ""
    if m:
        breadth, html = m.group(0), html.replace(m.group(0), "", 1)
    section2 = f'<section class="rb-page" id="rbmacro2" role="tabpanel" aria-labelledby="tab-overview">\n{parts.get("macro2", "")}\n</section>\n  '
    html = html.replace(ROTATION_OPEN, section + breadth + section2 + ROTATION_OPEN, 1)
    html = html.replace(ROTATION_HEAD, parts.get("rotation_head", ""), 1).replace(BREADTH_HEAD, parts.get("breadth_head", ""), 1)
    useco = f'<section class="rb-page" id="useco" role="tabpanel" aria-labelledby="tab-useco" hidden>\n{parts.get("useco", "")}\n</section>\n  '
    html = html.replace(OIL_OPEN, useco + OIL_OPEN + "\n" + parts["oil"], 1)
    html = html.replace(OIL_CURVE_AT, parts.get("oil_curve", "") + "\n      " + OIL_CURVE_AT, 1)
    html = html.replace(OVX_AT, OVX_AT + parts.get("ovx", ""), 1)
    html = html.replace(POSITIONS_AT, parts.get("oil_positions", "") + "\n      " + POSITIONS_AT, 1)
    html = html.replace(ODDS_OPEN, '<div class="rb-wide rb-pair">' + ODDS_OPEN, 1)
    html = html.replace(ODDS_CLOSE, ODDS_CLOSE + parts.get("war", "") + "</div>", 1)
    head = (f"<script>window.RB_VIEW = true; window.RB_GROUPS = {json.dumps(GROUPS)}; window.RB_DRAW = {json.dumps(DRAW)};</script>\n"
            f"<style>{','.join(HIDE)}{{display:none!important}} {HIDE_HAS}{{display:none!important}}</style>\n<style>{STYLE}</style>\n")
    return html.replace("</head>", head + "</head>", 1)
