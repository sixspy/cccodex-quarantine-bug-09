import { api } from '../api.js';

export async function renderSettings(el) {
  const data = await api('/api/settings');
  el.innerHTML = `
    <div class="card">
      <h2>台参数</h2>
      <table>
        <thead><tr><th>项</th><th>说明</th><th>值</th><th></th></tr></thead>
        <tbody>
          ${(data.items || []).map((s) => `
            <tr>
              <td>${s.key}</td>
              <td>${s.label}</td>
              <td><input data-key="${s.key}" value="${s.value}" /></td>
              <td><button data-save="${s.key}">保存</button></td>
            </tr>`).join('')}
        </tbody>
      </table>
    </div>`;
  el.querySelectorAll('[data-save]').forEach((btn) => {
    btn.onclick = async () => {
      const input = el.querySelector(`input[data-key="${btn.dataset.save}"]`);
      await api('/api/settings/update', {
        method: 'POST',
        body: JSON.stringify({ key: btn.dataset.save, value: input.value }),
      });
      await renderSettings(el);
    };
  });

  try {
    const dash = await api('/api/map_cutover/dash');
    el.innerHTML += `<div class="card" style="margin-top:1rem">
      <h3>映射切版</h3>
      <span class="chip">${dash.chip}</span>
      <p class="muted">读轨 ${dash.active_read} · 切流指纹 ${dash.cutover_fp || '空'} · 拒回刷 ${dash.reject_refresh} · 归档 ${dash.archive_count} · 新旗 ${dash.live_flag || '空'} · 对齐差 ${dash.panel_pack_mismatch}</p>
      <div class="row">
        <button id="go_map_cutover" type="button">落台</button>
        <button id="half_map_cutover" type="button">半修对齐</button>
        <button id="cut_map_cutover" type="button">切流账册</button>
        <button id="dual_map_cutover" type="button">双写两轨</button>
      </div>
    </div>`;
    const go = el.querySelector('#go_map_cutover');
    if (go) go.onclick = async () => {
      await api('/api/map_cutover/commit', { method:'POST', body: JSON.stringify({ref:1}) });
      await renderSettings(el);
    };
    const half = el.querySelector('#half_map_cutover');
    if (half) half.onclick = async () => {
      await api('/api/map_cutover/half', { method:'POST', body:'{}' });
      await renderSettings(el);
    };
    const cut = el.querySelector('#cut_map_cutover');
    if (cut) cut.onclick = async () => {
      await api('/api/map_cutover/cutover', { method:'POST', body: JSON.stringify({ref_id:1, note:'映射切版'}) });
      await renderSettings(el);
    };
    const dual = el.querySelector('#dual_map_cutover');
    if (dual) dual.onclick = async () => {
      await api('/api/map_cutover/dual', { method:'POST', body: JSON.stringify({note:'映射切版'}) });
      await renderSettings(el);
    };
  } catch (e) { /* optional surface */ }

}
