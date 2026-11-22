import { api } from '../api.js';

export async function renderBins(el) {
  const [bins, rows] = await Promise.all([api('/api/bins'), api('/api/rows')]);
  el.innerHTML = `
    <div class="card">
      <h2>隔离舱</h2>
      <table>
        <thead><tr><th>舱号</th><th>标题</th><th>状态</th><th>占用/容量</th><th>待复核</th></tr></thead>
        <tbody>
          ${(bins.items || []).map((b) => `
            <tr>
              <td>${b.bin_code}</td>
              <td>${b.title}</td>
              <td><span class="chip">${b.status}</span></td>
              <td>${b.row_count}/${b.capacity}</td>
              <td>${b.pending_count}</td>
            </tr>`).join('')}
        </tbody>
      </table>
    </div>
    <div class="card">
      <h2>舱内行 · 切版留痕</h2>
      <table>
        <thead><tr><th>舱</th><th>条目键</th><th>质量</th><th>原因</th><th>状态</th><th>映射号</th><th>列指纹</th></tr></thead>
        <tbody>
          ${(rows.items || []).map((r) => `
            <tr>
              <td>${r.bin_code}</td>
              <td>${r.item_key}</td>
              <td>${r.quality}</td>
              <td>${r.reason}</td>
              <td><span class="chip">${r.status}</span></td>
              <td><span class="chip">${r.mapping_no || '—'}</span></td>
              <td><code>${r.column_fingerprint || '—'}</code></td>
            </tr>`).join('')}
        </tbody>
      </table>
    </div>`;
}
