import { api } from '../api.js';

export async function renderCaptures(el) {
  const [data, bins, gateData] = await Promise.all([
    api('/api/batches'),
    api('/api/bins'),
    api('/api/mappings/gate'),
  ]);
  const openBin = (bins.items || []).find((b) => b.status === '开放');
  const gate = gateData || {};
  const gateBlock = gate.aligned
    ? `<span class="chip ok">切版徽标 ${gate.badge}</span>
       <span class="chip">现行映射 ${gate.mapping_no}</span>
       <span class="muted">落点 #${gate.landing_id} · 指纹 <code>${gate.column_fingerprint}</code></span>`
    : `<span class="chip bad">切版口径未对齐 · 拒采集</span>
       <span class="err">${gate.reason || ''}</span>`;

  el.innerHTML = `
    <div class="card">
      <h2>抓取批次</h2>
      <div class="row" style="margin-bottom:10px">${gateBlock}</div>
      <div class="row">
        <input id="src" placeholder="来源名" />
        <input id="note" placeholder="备注" />
        <button id="create">新建批次</button>
      </div>
    </div>
    <div class="card">
      <table>
        <thead><tr><th>批号</th><th>来源</th><th>状态</th><th>条目/坏件</th><th>现行映射号</th><th>操作</th></tr></thead>
        <tbody>
          ${(data.items || []).map((b) => `
            <tr>
              <td>${b.batch_code}</td>
              <td>${b.source_name}</td>
              <td><span class="chip">${b.status}</span></td>
              <td>${b.item_count} / <span class="chip bad">${b.bad_count}</span></td>
              <td><span class="chip">${b.current_mapping_no || '—'}</span></td>
              <td class="row">
                <button data-open="${b.id}">详情</button>
                <button data-close="${b.id}">关闭</button>
                ${openBin ? `<button data-auto="${b.id}">坏件入舱</button>` : ''}
              </td>
            </tr>`).join('')}
        </tbody>
      </table>
      <div id="detail" class="grid" style="margin-top:12px"></div>
    </div>`;

  const reload = () => renderCaptures(el);
  el.querySelector('#create').onclick = async () => {
    await api('/api/batches', {
      method: 'POST',
      body: JSON.stringify({
        source_name: el.querySelector('#src').value,
        note: el.querySelector('#note').value,
      }),
    });
    await reload();
  };
  el.querySelectorAll('[data-close]').forEach((btn) => {
    btn.onclick = async () => {
      await api(`/api/batches/${btn.dataset.close}/close`, { method: 'POST', body: '{}' });
      await reload();
    };
  });
  el.querySelectorAll('[data-auto]').forEach((btn) => {
    btn.onclick = async () => {
      if (!openBin) return;
      await api('/api/quarantine/auto-enter', {
        method: 'POST',
        body: JSON.stringify({ batch_id: Number(btn.dataset.auto), bin_id: openBin.id }),
      });
      await reload();
    };
  });
  el.querySelectorAll('[data-open]').forEach((btn) => {
    btn.onclick = async () => {
      const d = await api(`/api/batches/${btn.dataset.open}`);
      const box = el.querySelector('#detail');
      // 按现行映射的列结构渲染录入格，避免按旧映射写错列
      const mappings = (await api('/api/mappings')).items || [];
      const current = mappings.find((m) => m.mapping_no === gate.mapping_no);
      const cols = current ? JSON.parse(current.columns_json) : [];
      box.innerHTML = `
        <h3>${d.batch_code} 条目</h3>
        <div class="row">
          <input id="ikey" placeholder="条目键" />
          <select id="iq">
            <option>合格</option><option>缺字段</option><option>编码空</option><option>重复键</option>
          </select>
          ${cols.map((c) => `<input data-col="${c}" placeholder="列 ${c}" value="${c === 'title' ? '样例标题' : c === 'code' ? 'C-001' : '0.00'}" />`).join('')}
          <button id="addItem" ${gate.aligned ? '' : 'disabled'}>追加条目</button>
        </div>
        <p class="err" id="addErr"></p>
        <table>
          <thead><tr><th>键</th><th>质量</th><th>状态</th><th>映射号</th><th>列指纹</th></tr></thead>
          <tbody>
            ${(d.items || []).map((i) => `
              <tr>
                <td>${i.item_key}</td>
                <td><span class="chip ${i.quality === '合格' ? 'ok' : 'bad'}">${i.quality}</span></td>
                <td>${i.status}</td>
                <td><span class="chip">${i.mapping_no || '—'}</span></td>
                <td><code>${i.column_fingerprint || '—'}</code></td>
              </tr>`).join('')}
          </tbody>
        </table>`;
      box.querySelector('#addItem').onclick = async () => {
        const errBox = box.querySelector('#addErr');
        errBox.textContent = '';
        const payload = {};
        box.querySelectorAll('input[data-col]').forEach((inp) => {
          payload[inp.dataset.col] = inp.value;
        });
        try {
          await api(`/api/batches/${d.id}/items`, {
            method: 'POST',
            body: JSON.stringify({
              item_key: box.querySelector('#ikey').value,
              quality: box.querySelector('#iq').value,
              payload: JSON.stringify(payload),
            }),
          });
          btn.click();
        } catch (e) {
          errBox.textContent = e.message;
        }
      };
    };
  });
}
