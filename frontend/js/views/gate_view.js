export const gateViewTemplate = `
<section class="panel">
  <h2>闸口放行</h2>
  <p class="hint">口径唯一：开放超重未清禁放行。禁放票不进入放行候选，放行意图原子拒收且正式册零增。</p>
  <div class="form-row">
    <div><label>过磅票（仅可放行票）</label>
      <select v-model.number="gateForm.ticket_id">
        <option v-for="t in releasableTickets" :key="t.id" :value="t.id">{{ t.ticket_code }}</option>
      </select>
    </div>
    <div><label>值班员</label><input v-model="gateForm.officer"/></div>
  </div>
  <div class="actions">
    <button @click="releaseGate">确认放行</button>
    <button class="secondary" @click="refresh">刷新</button>
  </div>

  <div v-if="tickets.filter(isReleaseBlocked).length" class="detail-box" style="border-color:var(--bad)">
    <p class="bad" style="margin:0 0 6px">超重禁放（未闭环，禁止抬杆）：</p>
    <ul style="margin:0;padding-left:18px">
      <li v-for="t in tickets.filter(isReleaseBlocked)" :key="t.id">
        <span class="mono">{{ t.ticket_code }}</span>
        <span class="badge fail">{{ blockReasonText(t) }}</span>
      </li>
    </ul>
  </div>

  <table class="data-table" style="margin-top:14px">
    <thead><tr><th>放行号</th><th>票号</th><th>车道</th><th>值班员</th><th>时间</th></tr></thead>
    <tbody>
      <tr v-for="g in gateReleases" :key="g.id">
        <td>{{ g.release_ref }}</td>
        <td>{{ g.ticket_code }}</td>
        <td>{{ g.lane_code }}</td>
        <td>{{ g.officer }}</td>
        <td>{{ g.released_at }}</td>
      </tr>
    </tbody>
  </table>

  <h3 style="margin:18px 0 6px;font-size:14px;color:var(--harbor)">超重禁放命运条（当日封存·只追加）</h3>
  <table class="data-table">
    <thead><tr><th>票号</th><th>裁决</th><th>原因</th><th>值班员</th><th>正式册</th><th>封存时间</th></tr></thead>
    <tbody>
      <tr v-for="f in releaseFates" :key="f.id">
        <td class="mono">{{ f.ticket_code }}</td>
        <td><span class="badge" :class="f.verdict==='禁放'?'fail':'pass'">{{ f.verdict }}</span></td>
        <td>{{ f.reason_code }}</td>
        <td>{{ f.officer }}</td>
        <td>{{ f.formal_written ? '已写正式行' : '零增' }}</td>
        <td>{{ f.sealed_at }}</td>
      </tr>
      <tr v-if="!releaseFates.length"><td colspan="6" class="muted">暂无命运条</td></tr>
    </tbody>
  </table>
</section>
`;
