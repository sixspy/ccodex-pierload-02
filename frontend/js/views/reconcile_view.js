export const reconcileViewTemplate = `
<section class="grid-2">
  <section class="panel">
    <h2>提单对账</h2>
    <p class="hint">汇总过磅毛重与提单申报吨比对；票级放行只认正式册，禁放票不得计入已放行。</p>
    <div class="form-row">
      <div><label>提单号</label><input v-model="reconCode"/></div>
    </div>
    <div class="actions">
      <button @click="loadReconcile">对账</button>
      <button class="secondary" @click="loadAllReconcile">全量</button>
    </div>
    <div v-if="reconOne" class="detail-box">
      <p>申报 {{ reconOne.declared_gross_t }}t · 过磅合计 {{ reconOne.ticket_sum_t }}t</p>
      <p :class="reconOne.balanced ? 'ok' : 'bad'">{{ reconOne.balanced ? '账实平衡' : '偏差待查' }}</p>
      <p>快照数 {{ reconOne.seal_count }} · 已放行票 {{ reconOne.released_ticket_count ?? 0 }} ·
        <span :class="(reconOne.blocked_ticket_count ?? 0) ? 'bad' : 'ok'">禁放票 {{ reconOne.blocked_ticket_count ?? 0 }}</span>
      </p>
      <p :class="reconOne.proof_ready ? 'ok' : 'bad'">可出证明 {{ reconOne.proof_ready ? '是' : '否（含禁放票时不出绿）' }}</p>
      <table class="data-table" v-if="reconOne.tickets && reconOne.tickets.length">
        <thead><tr><th>票号</th><th>毛重</th><th>放行口径</th></tr></thead>
        <tbody>
          <tr v-for="t in reconOne.tickets" :key="t.id || t.ticket_code">
            <td class="mono">{{ t.ticket_code }}</td>
            <td>{{ t.gross_t }}t</td>
            <td>
              <span v-if="t.release_blocked" class="badge fail">{{ blockReasonText(t) }}</span>
              <span v-else-if="t.released" class="badge pass">已放行</span>
              <span v-else class="badge muted">未放行</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <ul v-if="reconAllItems.length">
      <li v-for="r in reconAllItems" :key="r.bl_code">{{ r.bl_code }} · {{ r.balanced ? '平' : '偏' }}</li>
    </ul>
  </section>
  <section class="panel">
    <h2>单票证明</h2>
    <div class="form-row"><div><label>票号</label><input v-model="proofCode"/></div></div>
    <div class="actions"><button @click="loadProof">拉证明</button></div>
    <div v-if="proofOne" class="detail-box">
      <p>提单匹配 {{ proofOne.manifest_matches_bl ? '是' : '否' }}</p>
      <p>超重闭环 {{ proofOne.overload_closed ? '是' : '否' }}</p>
      <p>已放行 {{ proofOne.released ? '是' : '否' }}</p>
      <p v-if="proofOne.release_blocked">
        放行口径：<span class="badge fail">{{ proofOne.block_reason_code === 'OPEN_OVERLOAD' ? '开放超重禁放' : '禁放' }}</span>
      </p>
      <p :class="proofOne.coherent ? 'ok' : 'bad'">一致 {{ proofOne.coherent ? '是' : '否' }}</p>
    </div>
  </section>
</section>
`;
