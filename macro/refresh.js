/* Data-only update control for the local build (the 更新數據 button and source dates). No API keys or AI calls. */
(() => {
  const button = document.getElementById('update-data');
  const status = document.getElementById('update-status');
  if (!button || !status) return;
  const en = () => window.dash?.params().lang === 'en';
  const say = (zh, english) => { status.textContent = en() ? english : zh; };
  let running = false, available = false, token = '', timer;
  function dates() {
    const result = window.dash?.data('refresh_meta');
    const rows = result?.status === 'ok' ? result.data[0]?.groups : null;
    const detail = document.getElementById('update-dates');
    if (!rows?.length) return;
    detail.hidden = false;
    const list = document.getElementById('update-date-list'); list.replaceChildren();
    const cadence = {daily:'每日收市',daily_release:'每日查新公布',weekly:'每週公布',completed_week:'完整週結'};
    for (const row of rows) {
      const line = document.createElement('div');
      line.textContent = `${row.name} · ${en() ? row.cadence : cadence[row.cadence]} · ${row.dates.join(' / ')}${row.state === 'same_observation_dates' ? (en() ? ' · observation dates unchanged' : ' · 觀察日期未變') : ''}`;
      list.append(line);
    }
    for (const row of result.data[0].borrower_references || []) {
      const line = document.createElement('div');
      line.textContent = `${row.issuer} · ${row.date || '未確認'} · ${row.state === 'unconfirmed' ? '未取得可確認新報價，保留原資料' : '債價／YTW參考；信用改善未確認'}`;
      list.append(line);
    }
  }
  function label() {
    button.textContent = running ? (en() ? 'Updating…' : '更新中…') : (en() ? 'Update data' : '更新數據');
    button.disabled = running || !available;
    dates();
  }
  async function getState() {
    const response = await fetch('api/update', {cache:'no-store'});
    if (!response.ok) throw new Error('Local updater unavailable');
    const value = await response.json(); token = value.token || token; return value;
  }
  async function poll() {
    try {
      const result = await getState();
      if (result.state === 'running') { timer = setTimeout(poll, 2500); return; }
      running = false; label();
      if (result.state === 'success') {
        sessionStorage.setItem('board-update-complete',result.session);
        location.reload();
      } else say('更新未完成，保留上一個有效版本。詳情見本地更新紀錄。', 'Update did not complete; the previous snapshot was preserved. See local update logs.');
    } catch (_) { running = false; label(); say('無法連接本地更新服務；原有看板保留。', 'Local update service unavailable; the existing board is preserved.'); }
  }
  button.addEventListener('click', async () => {
    if (running) return;
    running = true; label();
    say('正在抓取及核對數據，可能需數分鐘；AI摘要不會改寫。', 'Fetching and validating data; this may take a few minutes. AI summary will not be rewritten.');
    try {
      await getState();
      const response = await fetch('api/update', {method:'POST', headers:{'X-Refresh-Token':token}});
      if (!response.ok) throw new Error('Update request rejected');
      const result = await response.json();
      if (result.state === 'external_running') {
        running = false; label(); say('已有另一個更新進行中；完成後重新整理即可。', 'Another refresh is running; reload when it finishes.');
      } else poll();
    } catch (_) { running = false; label(); say('未能啟動更新，原有資料保留。', 'Could not start the refresh; existing data is preserved.'); }
  });
  async function init() {
    button.hidden = false;
    try {
      const result = await getState(); available = true;
      if (result.state === 'running') { running = true; say('已有更新進行中…', 'An update is already running…'); poll(); }
      else {
        const completed = sessionStorage.getItem('board-update-complete');
        if (completed) { say(`數據更新完成，股價截至 ${completed}；AI摘要保留自己的日期。`, `Data refresh complete; prices through ${completed}. AI summary retains its own date.`); sessionStorage.removeItem('board-update-complete'); }
        else say('只更新數據及圖表；AI摘要由既有收市排程另行更新。', 'Updates data and charts only; AI analysis follows the existing after-close schedule.');
      }
    } catch (_) { say('靜態版本：2026-11-27 21:36（英國時間）匯出，數據截至 2026-11-27 收市；更新按鈕、盤中報價及自動新聞擷取只在本地看板運作。', 'Static snapshot exported 2026-11-27 21:36 UK time, data through the 2026-11-27 close; updates, live quotes and the news fetch run only on the local board.'); }
    label();
  }
  window.dash?.onData(label);
  addEventListener('pagehide',()=>clearTimeout(timer));
  init();
})();
