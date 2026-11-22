import { api } from '../api.js';

export async function renderMappings(el) {
  const data = await api('/api/mappings');
  const gate = data.gate || {};
  const mappings = data.items || [];
  const landings = data.landings || [];
  const current = mappings.find((m) => m.mapping_no === gate.mapping_no);
  const columnsText = current ? JSON.parse(current.columns_json).join('、') : '—';

  el.innerHTML = `
    <div class="card">
      <h2>字段映射切版</h2>
      <p class="muted">甲路冻凭证：切版当刻冻结映射键与列指纹，落点行只读归档；采集侧只认现行落点。</p>
      <div class="stat-strip">
        <div class="stat">
          <span class="muted">切版徽标</span>
          <b><span class="chip ${gate.aligned ? 'ok' : 'bad'}">${gate.badge || '未亮'}</span></b>
        </div>
        <div class="stat">
          <span class="muted">现行映射号</span>
          <b>${gate.mapping_no || '无'}</b>
        </div>
        <div class="stat">
          <span class="muted">映射键</span>
          <b>${gate.mapping_key || '—'}</b>
        </div>
        <div class="stat">
          <span class="muted">现行落点</span>
          <b>#${gate.landing_id || '—'}</b>
        </div>
      </div>
      ${gate.aligned
        ? `<p class="hint-box">徽标与现行映射号一致，列指纹 <code>${gate.column_fingerprint}</code>，口径：${columnsText}</p>`
        : `<p class="hint-box err">口径未对齐：${gate.reason || '禁止采集'}</p>`}
    </div>

    <div class="card">
      <h3>映射目录</h3>
      <table>
        <thead><tr><th>映射号</th><th>映射键</th><th>标题</th><th>列</th><th>列指纹</th><th>状态</th></tr></thead>
        <tbody>
          ${mappings.map((m) => `
            <tr ${m.mapping_no === gate.mapping_no ? 'class="active-row"' : ''}>
              <td>${m.mapping_no}${m.mapping_no === gate.mapping_no ? ' <span class="chip ok">现行</span>' : ''}</td>
              <td>${m.mapping_key}</td>
              <td>${m.title}</td>
              <td>${JSON.parse(m.columns_json).join('、')}</td>
              <td><code>${m.column_fingerprint}</code></td>
              <td>${m.status}</td>
            </tr>`).join('')}
        </tbody>
      </table>
      <div class="row" style="margin-top:10px">
        <select id="cutTarget">
          ${mappings.filter((m) => m.mapping_no !== gate.mapping_no)
            .map((m) => `<option value="${m.mapping_no}">${m.mapping_no} · ${m.title}</option>`).join('')}
        </select>
        <input id="cutReason" placeholder="切版缘由" />
        <button id="doCut">执行切版（单事务）</button>
        <span id="cutMsg" class="err"></span>
      </div>
    </div>

    <div class="card">
      <h3>切版落点（只读凭证）</h3>
      <table>
        <thead><tr><th>落点</th><th>映射号</th><th>映射键</th><th>冻结列指纹</th><th>缘由</th><th>钉点时间</th><th>状态</th></tr></thead>
        <tbody>
          ${landings.slice().reverse().map((r) => `
            <tr ${r.is_active ? 'class="active-row"' : ''}>
              <td>#${r.id}</td>
              <td>${r.mapping_no}</td>
              <td>${r.mapping_key}</td>
              <td><code>${r.column_fingerprint}</code></td>
              <td>${r.reason}</td>
              <td>${r.created_at}</td>
              <td>${r.is_active ? '<span class="chip ok">现行</span>' : '<span class="chip">归档只读</span>'}</td>
            </tr>`).join('')}
        </tbody>
      </table>
    </div>`;

  el.querySelector('#doCut').onclick = async () => {
    const msg = el.querySelector('#cutMsg');
    msg.textContent = '';
    try {
      await api('/api/mappings/cutover', {
        method: 'POST',
        body: JSON.stringify({
          mapping_no: el.querySelector('#cutTarget').value,
          reason: el.querySelector('#cutReason').value,
        }),
      });
      await renderMappings(el);
    } catch (e) {
      msg.textContent = e.message;
    }
  };
}
