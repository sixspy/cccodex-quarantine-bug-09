import { api } from '../api.js';

export async function renderSettings(el) {
  const [data, gate] = await Promise.all([
    api('/api/settings'),
    api('/api/mappings/gate'),
  ]);
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
    </div>
    <div class="card">
      <h3>切版口径（只读）</h3>
      <p class="muted">切版操作统一在「映射页」进行，本页仅展示现行凭证，不在此改绑。</p>
      <div class="stat-strip">
        <div class="stat"><span class="muted">切版徽标</span><b>${gate.badge || '未亮'}</b></div>
        <div class="stat"><span class="muted">现行映射号</span><b>${gate.mapping_no || '无'}</b></div>
        <div class="stat"><span class="muted">映射键</span><b>${gate.mapping_key || '—'}</b></div>
        <div class="stat"><span class="muted">现行落点</span><b>#${gate.landing_id || '—'}</b></div>
      </div>
      <p class="${gate.aligned ? 'hint-box' : 'hint-box err'}">
        列指纹 <code>${gate.column_fingerprint || '空'}</code>
        ${gate.aligned ? '· 口径对齐，采集放行' : `· ${gate.reason || '口径未对齐，拒采集'}`}
      </p>
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
}
