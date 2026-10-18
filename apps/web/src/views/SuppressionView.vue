<template>
  <div>
    <PageHeader title="自动喷水">
      <template #actions>
        <RouterLink class="text-link" to="/incidents">识别记录</RouterLink>
        <el-button :loading="loading" @click="load">刷新</el-button>
        <el-button v-if="canStop" type="danger" :disabled="isMockMode || !status?.enabled" :loading="stopping" @click="stop">紧急停止并锁定</el-button>
      </template>
    </PageHeader>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-alert v-if="isMockMode" title="模拟模式：未连接实际水泵" type="info" :closable="false" />
    <section class="panel settings-section">
      <h2>水泵控制状态</h2>
      <dl v-if="status" class="runtime-facts">
        <div><dt>自动联动</dt><dd>{{ status.inhibited ? '已紧急锁定，重启服务后恢复' : status.enabled ? '已启用' : '未启用，请完成硬件配置' }}</dd></div>
        <div><dt>覆盖教室</dt><dd>{{ rooms.find((room) => room.id === status?.zoneId)?.name || (status.zoneId ? `教室 #${status.zoneId}` : '未配置') }}</dd></div>
        <div><dt>控制器连接</dt><dd>{{ status.enabled ? status.connected ? '已连接' : '未连接' : '未启用' }}</dd></div>
        <div><dt>水泵输出</dt><dd>{{ { ON: '已开启', OFF: '已关闭', UNKNOWN: '未知，请检查设备', DISABLED: '未启用' }[status.deviceState] }}</dd></div>
        <div><dt>启动来源</dt><dd>{{ status.deviceState !== 'ON' ? '—' : status.activationSource === 'BOOT' ? 'BOOT 按钮强制喷水' : '自动识别' }}</dd></div>
        <div><dt>单次时长 / 冷却时间</dt><dd>{{ status.durationMs / 1000 }} 秒 / {{ status.cooldownSeconds }} 秒</dd></div>
      </dl>
      <p v-if="status?.lastError" class="error-note">{{ reasonLabel(status.lastError) }}</p>
      <p class="muted">{{ status?.recognitionMode === 'VLM' ? '火灾时序识别 → 大模型确认 → 自动启动水泵。' : '本地 YOLO 火灾时序确认 → 自动启动水泵，大模型接口暂时关闭。' }}支持单摄或双摄独立识别，共用一只泵，仅对覆盖教室生效。</p>
      <p class="muted">BOOT：正常启动后按住喷水，松开停止，单次最多 30 秒。紧急停止优先于持续按住的 BOOT。</p>
      <p class="muted">状态来自控制器回执；当前没有水流传感器，无法确认实际出水。紧急停止后需检查现场并重启推理服务才能恢复自动联动。</p>
    </section>
    <section class="panel settings-section">
      <h2>自动联动记录</h2>
      <el-table :data="status?.records || []" empty-text="暂无自动联动记录">
        <el-table-column label="时间" min-width="170"><template #default="{ row }">{{ new Date(row.createdAt).toLocaleString('zh-CN', { hour12: false }) }}</template></el-table-column>
        <el-table-column label="教室" min-width="120"><template #default="{ row }">{{ rooms.find((room) => room.id === row.zoneId)?.name || `#${row.zoneId}` }}</template></el-table-column>
        <el-table-column prop="cameraId" label="摄像头编号" width="120" />
        <el-table-column label="指令状态" min-width="120"><template #default="{ row }">{{ recordLabels[row.status as PumpRecord['status']] }}</template></el-table-column>
        <el-table-column label="说明" min-width="230"><template #default="{ row }">{{ row.reason ? reasonLabel(row.reason) : '设备已确认开启输出' }}</template></el-table-column>
        <el-table-column prop="traceId" label="事件追踪号" min-width="240" show-overflow-tooltip />
      </el-table>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import PageHeader from '@/components/PageHeader.vue'
import { pumpApi, zoneApi } from '@/api'
import { isMockMode } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import type { PumpRecord, PumpStatus, Zone } from '@/types/domain'

const auth = useAuthStore()
const canStop = computed(() => auth.user?.roles.some((role) => ['ADMIN', 'OPERATOR'].includes(role)))
const status = ref<PumpStatus>()
const rooms = ref<Zone[]>([])
const loading = ref(false)
const stopping = ref(false)
const error = ref('')
let timer: number | undefined
const recordLabels: Record<PumpRecord['status'], string> = {
  ATTEMPTING: '发送中', RUNNING: '已确认开启', STOPPED: '已确认关闭',
  UNKNOWN: '结果未知', SKIPPED: '未启动',
}
const reasons: Record<string, string> = {
  PUMP_DISABLED: '水泵联动未启用', ZONE_NOT_COVERED: '不在水泵覆盖教室',
  VLM_NOT_CONFIRMED: '大模型未确认', STALE_EVIDENCE: '证据已过期',
  LOCAL_FIRE_NOT_CONFIRMED: '本地火灾时序证据未达标（仅烟雾不启动）',
  BOOT_ACTIVE: 'BOOT 按钮正在强制喷水', BOOT_OVERRIDE: 'BOOT 接管，原自动指令结果不再跟踪',
  CAMERA_STOPPED: '摄像头已停止', EMERGENCY_STOP_LATCHED: '紧急停止已锁定',
  COOLDOWN: '水泵处于冷却时间内', DEVICE_ACK_UNAVAILABLE: '未收到设备确认，未自动重发',
  DEVICE_REPORTED_OFF: '控制器已报告关闭', EMERGENCY_STOP: '已紧急停止',
  SERVICE_RESTARTED: '服务重启，原指令结果未知',
  DEVICE_STATUS_UNAVAILABLE: '无法读取控制器状态，请检查串口与供电',
  STOP_ACK_UNAVAILABLE: '未收到停止确认，请立即检查并切断水泵电源',
}
function reasonLabel(value: string) { return reasons[value] || value }
async function load() {
  if (loading.value || stopping.value) return
  loading.value = true
  try { status.value = await pumpApi.status(); error.value = '' }
  catch { status.value = undefined; error.value = '无法读取水泵状态，请检查业务服务与推理服务。' }
  finally { loading.value = false }
}
async function stop() {
  stopping.value = true
  try {
    status.value = await pumpApi.stop()
    if (status.value.lastError) ElMessage.error(reasonLabel(status.value.lastError))
    else ElMessage.success('已停止并锁定自动联动')
  } catch { ElMessage.error('停止请求失败，请检查设备并切断水泵电源') }
  finally { stopping.value = false }
}
onMounted(async () => {
  await load()
  try { rooms.value = await zoneApi.list() } catch { /* IDs remain available. */ }
  timer = window.setInterval(load, 1500)
})
onBeforeUnmount(() => window.clearInterval(timer))
</script>
