<template>
  <div class="devices-page">
    <PageHeader eyebrow="CONFIGURATION" title="区域与设备" description="管理监控区域与视频源；当前阶段使用一路摄像头">
      <template #actions>
        <el-button plain :icon="Plus" @click="zoneDialog = true">新建区域</el-button>
        <el-button type="primary" :icon="VideoCamera" @click="cameraDialog = true">添加摄像头</el-button>
      </template>
    </PageHeader>

    <div class="device-summary-strip">
      <div><span>监控区域</span><strong>{{ zones.length }}</strong><small>全部已布防</small></div>
      <div><span>摄像头</span><strong>{{ cameras.length }}</strong><small>{{ onlineCount }} 路在线</small></div>
      <div><span>双视角预留</span><strong>{{ pairedZones }}</strong><small>当前未启用</small></div>
      <div><span>未绑定设备</span><strong>{{ unboundCameras }}</strong><small>等待分配视角</small></div>
    </div>

    <section class="panel zone-panel">
      <header class="panel-header"><div><h2>监控区域</h2><p>当前使用 VIEW_A；VIEW_B 为后续双摄扩展预留</p></div></header>
      <div class="zone-card-grid">
        <article v-for="zone in zones" :key="zone.id" class="zone-card">
          <header>
            <div class="zone-icon"><el-icon><School v-if="zone.sceneType === 'CLASSROOM'" /><Cpu v-else /></el-icon></div>
            <div><h3>{{ zone.name }}</h3><span>{{ sceneLabels[zone.sceneType] }} · ID {{ zone.id }}</span></div>
            <span class="armed-status"><i /> 已布防</span>
          </header>
          <div class="binding-slots">
            <div v-for="role in (['VIEW_A', 'VIEW_B'] as ViewRole[])" :key="role" class="binding-slot" :class="{ empty: !cameraFor(zone.id, role) }">
              <span class="binding-role">{{ role }}</span>
              <template v-if="cameraFor(zone.id, role)">
                <strong>{{ cameraFor(zone.id, role)?.name }}</strong>
                <span><i class="online-dot" /> {{ cameraStatusLabels[cameraFor(zone.id, role)!.status] }} · 权重 {{ role === 'VIEW_A' ? '0.55' : '0.45' }}</span>
              </template>
              <template v-else><strong>未绑定</strong><span>可添加第二视角</span></template>
            </div>
          </div>
          <footer><span>最近事件：{{ zone.id === 1 ? '3 分钟前' : '46 分钟前' }}</span><el-button link type="primary" @click="openBinding(zone)">调整绑定</el-button></footer>
        </article>
      </div>
    </section>

    <section class="panel camera-table-panel">
      <header class="panel-header"><div><h2>摄像头设备</h2><p>视频源地址已脱敏，前端不会获得 RTSP 凭据</p></div><el-input v-model="search" placeholder="搜索设备" clearable :prefix-icon="Search" /></header>
      <el-table v-loading="loading" :data="filteredCameras" class="data-table" table-layout="fixed">
        <el-table-column label="设备" min-width="220">
          <template #default="{ row }"><div class="camera-name-cell"><span><el-icon><VideoCamera /></el-icon></span><div><strong>{{ row.name }}</strong><small>{{ row.maskedSource || '未设置来源' }}</small></div></div></template>
        </el-table-column>
        <el-table-column label="类型" width="150"><template #default="{ row }">{{ sourceLabels[row.sourceType as SourceType] }}</template></el-table-column>
        <el-table-column label="区域 / 视角" min-width="190"><template #default="{ row }"><span v-if="row.zoneId">{{ zoneName(row.zoneId) }} · <b>{{ row.viewRole }}</b></span><span v-else class="muted">未绑定</span></template></el-table-column>
        <el-table-column label="状态" width="120"><template #default="{ row }"><span class="camera-state" :class="row.status.toLowerCase()"><i /> {{ cameraStatusLabels[row.status as CameraStatus] }}</span></template></el-table-column>
        <el-table-column label="最后心跳" width="160"><template #default="{ row }">{{ row.lastSeenAt ? formatTime(row.lastSeenAt) : '—' }}</template></el-table-column>
        <el-table-column label="操作" width="130" fixed="right"><template #default="{ row }"><el-button link type="primary" :loading="probingId === row.id" @click="probe(row)">连接测试</el-button></template></el-table-column>
      </el-table>
    </section>

    <el-dialog v-model="cameraDialog" title="添加摄像头" width="min(520px, 92vw)" destroy-on-close>
      <el-form ref="cameraFormRef" :model="cameraForm" :rules="cameraRules" label-position="top">
        <el-form-item label="设备名称" prop="name"><el-input v-model="cameraForm.name" placeholder="如：USB 侧视摄像头" /></el-form-item>
        <el-form-item label="视频源类型" prop="sourceType"><el-select v-model="cameraForm.sourceType" style="width:100%"><el-option v-for="(label, value) in sourceLabels" :key="value" :label="label" :value="value" /></el-select></el-form-item>
        <el-form-item label="视频源" prop="sourceUri"><el-input v-model="cameraForm.sourceUri" :placeholder="sourcePlaceholder" /><div class="form-tip">网络摄像头账号和密码只会提交给后端，不会回显。</div></el-form-item>
        <el-form-item label="目标分析帧率"><el-input-number v-model="cameraForm.targetFps" :min="1" :max="30" /><span class="inline-hint">推荐 5 FPS</span></el-form-item>
      </el-form>
      <template #footer><el-button @click="cameraDialog = false">取消</el-button><el-button type="primary" :loading="saving" @click="createCamera">保存设备</el-button></template>
    </el-dialog>

    <el-dialog v-model="zoneDialog" title="新建监控区域" width="min(480px, 92vw)" destroy-on-close>
      <el-form ref="zoneFormRef" :model="zoneForm" :rules="zoneRules" label-position="top">
        <el-form-item label="区域名称" prop="name"><el-input v-model="zoneForm.name" placeholder="如：求实楼 301 智慧教室" /></el-form-item>
        <el-form-item label="场景类型" prop="sceneType"><el-radio-group v-model="zoneForm.sceneType"><el-radio-button v-for="(label, value) in sceneLabels" :key="value" :value="value">{{ label }}</el-radio-button></el-radio-group></el-form-item>
      </el-form>
      <template #footer><el-button @click="zoneDialog = false">取消</el-button><el-button type="primary" :loading="saving" @click="createZone">创建区域</el-button></template>
    </el-dialog>

    <el-dialog v-model="bindingDialog" title="调整摄像头绑定" width="min(560px, 92vw)">
      <p class="dialog-description">{{ bindingZone?.name }} · 每个视角只能绑定一路设备</p>
      <div class="binding-editor">
        <label>VIEW_A <small>主视角 · 权重 0.55</small></label>
        <el-select v-model="bindingForm.viewA" clearable placeholder="选择摄像头"><el-option v-for="camera in cameras" :key="camera.id" :label="camera.name" :value="camera.id" :disabled="camera.id === bindingForm.viewB" /></el-select>
        <label>VIEW_B <small>辅助视角 · 权重 0.45</small></label>
        <el-select v-model="bindingForm.viewB" clearable placeholder="选择摄像头"><el-option v-for="camera in cameras" :key="camera.id" :label="camera.name" :value="camera.id" :disabled="camera.id === bindingForm.viewA" /></el-select>
      </div>
      <template #footer><el-button @click="bindingDialog = false">取消</el-button><el-button type="primary" :loading="saving" @click="saveBindings">保存绑定</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, onMounted } from 'vue'
import { Cpu, Plus, School, Search, VideoCamera } from '@element-plus/icons-vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import PageHeader from '@/components/PageHeader.vue'
import { cameraApi, zoneApi } from '@/api'
import { cameraStatusLabels, sceneLabels, sourceLabels } from '@/config/labels'
import type { Camera, CameraStatus, CameraUpsert, SceneType, SourceType, ViewRole, Zone } from '@/types/domain'

const loading = ref(true)
const saving = ref(false)
const cameras = ref<Camera[]>([])
const zones = ref<Zone[]>([])
const search = ref('')
const cameraDialog = ref(false)
const zoneDialog = ref(false)
const bindingDialog = ref(false)
const probingId = ref<number>()
const bindingZone = ref<Zone>()
const cameraFormRef = ref<FormInstance>()
const zoneFormRef = ref<FormInstance>()
const cameraForm = reactive<CameraUpsert>({ name: '', sourceType: 'USB', sourceUri: '', targetFps: 5 })
const zoneForm = reactive<{ name: string; sceneType: SceneType }>({ name: '', sceneType: 'CLASSROOM' })
const bindingForm = reactive<{ viewA?: number; viewB?: number }>({})
const cameraRules: FormRules = { name: [{ required: true, message: '请输入设备名称', trigger: 'blur' }], sourceType: [{ required: true, message: '请选择来源类型', trigger: 'change' }] }
const zoneRules: FormRules = { name: [{ required: true, message: '请输入区域名称', trigger: 'blur' }], sceneType: [{ required: true, message: '请选择场景类型', trigger: 'change' }] }
const onlineCount = computed(() => cameras.value.filter((camera) => camera.status === 'ONLINE').length)
const unboundCameras = computed(() => cameras.value.filter((camera) => !camera.zoneId).length)
const pairedZones = computed(() => zones.value.filter((zone) => cameraFor(zone.id, 'VIEW_A') && cameraFor(zone.id, 'VIEW_B')).length)
const filteredCameras = computed(() => cameras.value.filter((camera) => camera.name.toLowerCase().includes(search.value.toLowerCase())))
const sourcePlaceholder = computed(() => cameraForm.sourceType === 'NETWORK_RTSP' ? 'rtsp://user:password@192.168.1.10/stream' : cameraForm.sourceType === 'INTEGRATED' ? 'Integrated Camera' : cameraForm.sourceType === 'USB' ? 'USB Camera' : 'D:\\demo\\fire.mp4')

function cameraFor(zoneId: number, role: ViewRole) { return cameras.value.find((camera) => camera.zoneId === zoneId && camera.viewRole === role) }
function zoneName(zoneId: number) { return zones.value.find((zone) => zone.id === zoneId)?.name || `区域 ${zoneId}` }
function formatTime(date: string) { return new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(new Date(date)) }

async function load() {
  loading.value = true
  try { ;[zones.value, cameras.value] = await Promise.all([zoneApi.list(), cameraApi.list()]) } finally { loading.value = false }
}
async function probe(camera: Camera) {
  probingId.value = camera.id
  try {
    const result = await cameraApi.probe(camera.id)
    ElMessage.success(`${result.message || '连接测试完成'} · ${result.width}×${result.height} @ ${result.fps} FPS`)
    await load()
  } catch { ElMessage.error('连接测试失败') } finally { probingId.value = undefined }
}
async function createCamera() {
  try { await cameraFormRef.value?.validate() } catch { return }
  saving.value = true
  try { await cameraApi.create(cameraForm); cameraDialog.value = false; Object.assign(cameraForm, { name: '', sourceType: 'USB', sourceUri: '', targetFps: 5 }); await load(); ElMessage.success('摄像头已添加') } finally { saving.value = false }
}
async function createZone() {
  try { await zoneFormRef.value?.validate() } catch { return }
  saving.value = true
  try { await zoneApi.create(zoneForm); zoneDialog.value = false; Object.assign(zoneForm, { name: '', sceneType: 'CLASSROOM' }); await load(); ElMessage.success('监控区域已创建') } finally { saving.value = false }
}
function openBinding(zone: Zone) {
  bindingZone.value = zone
  bindingForm.viewA = cameraFor(zone.id, 'VIEW_A')?.id
  bindingForm.viewB = cameraFor(zone.id, 'VIEW_B')?.id
  bindingDialog.value = true
}
async function saveBindings() {
  if (!bindingZone.value || (!bindingForm.viewA && !bindingForm.viewB)) { ElMessage.warning('至少绑定一路摄像头'); return }
  saving.value = true
  try {
    await zoneApi.replaceBindings(bindingZone.value.id, [
      ...(bindingForm.viewA ? [{ cameraId: bindingForm.viewA, viewRole: 'VIEW_A' as const, weight: 0.55 }] : []),
      ...(bindingForm.viewB ? [{ cameraId: bindingForm.viewB, viewRole: 'VIEW_B' as const, weight: 0.45 }] : []),
    ])
    bindingDialog.value = false; await load(); ElMessage.success('摄像头绑定已更新')
  } finally { saving.value = false }
}
onMounted(load)
</script>
