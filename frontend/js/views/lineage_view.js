export const lineageViewTemplate = `
<section class="panel">
  <h2>轴重血缘</h2>
  <p class="hint">记录驳载分票、二次过磅升代等轴重血缘边；同车同提单正式票须唯一（升代互斥）。</p>
  <p v-if="tickets.filter(t => t.status !== '作废').length !== new Set(tickets.filter(t => t.status !== '作废').map(t => t.vehicle_plate + '|' + t.bl_ref)).size" class="action-err">同车双正式并存：对账按升代互斥仅计各车最新正式票，须走二次过磅升代互斥写路径解冲突。</p>
  <div class="form-row">
    <div><label>起点票</label>
      <select v-model.number="lineageForm.from_ticket_id">
        <option v-for="t in tickets" :key="t.id" :value="t.id">{{ t.ticket_code }}</option>
      </select>
    </div>
    <div><label>终点票(可空)</label>
      <select v-model.number="lineageForm.to_ticket_id">
        <option :value="null">—</option>
        <option v-for="t in tickets" :key="t.id" :value="t.id">{{ t.ticket_code }}</option>
      </select>
    </div>
    <div><label>类型</label><input v-model="lineageForm.edge_type"/></div>
    <div><label>说明</label><input v-model="lineageForm.detail"/></div>
  </div>
  <div class="actions">
    <button @click="addLineage">登记边</button>
    <button class="secondary" @click="refresh">刷新</button>
  </div>
  <table class="data-table">
    <thead><tr><th>自</th><th>自票态</th><th>至</th><th>至票态</th><th>类型</th><th>说明</th></tr></thead>
    <tbody>
      <tr v-for="e in lineageEdges" :key="e.id">
        <td>{{ e.from_code || e.from_ticket_id }}</td>
        <td><span class="badge" :class="ticketClass(e.from_status)">{{ e.from_status || '—' }}</span></td>
        <td>{{ e.to_code || '—' }}</td>
        <td><span class="badge" :class="ticketClass(e.to_status)">{{ e.to_status || '—' }}</span></td>
        <td>{{ e.edge_type }}</td>
        <td>{{ e.detail }}</td>
      </tr>
    </tbody>
  </table>
</section>
`;
