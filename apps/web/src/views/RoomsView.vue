<template>
  <div>
    <PageHeader title="教室与摄像头">
      <template #actions><el-button :loading="loading" @click="load">刷新</el-button><el-button v-if="canEdit" type="primary" @click="editRoom()">新建教室</el-button></template>
    </PageHeader>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <section class="panel settings-section">
      <el-table v-loading="loading" :data="rooms" row-key="id" empty-text="暂无教室">
        <el-table-column prop="name" label="名称" min-width="180" />
        <el-table-column label="类型" width="100"><template #default="{ row }">{{ sceneLabels[row.sceneType as SceneType] }}</template></el-table-column>
        <el-table-column label="摄像头" min-width="180"><template #default="{ row }">{{ roomCamera(row.id)?.name || '未接入' }}</template></el-table-column>
        <el-table-column v-if="canEdit" label="操作" width="240"><template #default="{ row }"><el-button link type="primary" @click="editRoom(row)">编辑</el-button><el-button link type="primary" @click="bindCamera(row)">绑定摄像头</el-button><el-button link type="danger" @click="deleteRoom(row)">删除</el-button></template></el-table-column>
      </el-table>
    </section>

    <section class="panel settings-section">
      <header class="settings-section-header"><h2>摄像头</h2><div v-if="canEdit" class="page-actions"><el-button @click="editCamera(undefined, 'INTEGRATED')">添加前置摄像头</el-button><el-button @click="editCamera(undefined, 'USB')">添加 USB 摄像头</el-button><el-button @click="editCamera(undefined, 'NETWORK_RTSP')">添加网络摄像头</el-button></div></header>
      <el-table :data="cameras" row-key="id" empty-text="暂无摄像头">
        <el-table-column prop="name" label="名称" min-width="160" />
        <el-table-column label="来源" width="130"><template #default="{ row }">{{ sourceLabels[row.sourceType as SourceType] }}</template></el-table-column>
        <el-table-column label="地址 / 编号" min-width="190" show-overflow-tooltip><template #default="{ row }">{{ row.maskedSource || '0' }}</template></el-table-column>
        <el-table-column label="教室" min-width="140"><template #default="{ row }">{{ rooms.find((room) => room.id === row.zoneId)?.name || '未绑定' }}</template></el-table-column>
        <el-table-column v-if="canEdit" label="操作" width="270"><template #default="{ row }"><el-button link type="primary" @click="editCamera(row)">编辑</el-button><el-button link type="primary" @click="connectionInfo(row)">接入</el-button><el-button link type="danger" @click="deleteCamera(row)">删除</el-button></template></el-table-column>
      </el-table>
    </section>

    <el-dialog v-model="roomDialog" :title="roomId ? '编辑教室' : '新建教室'" width="min(440px, 92vw)">
      <el-form ref="roomFormRef" :model="roomForm" label-position="top">
        <el-form-item label="名称" prop="name" :rules="[{ required: true, whitespace: true, message: '填写教室名称', trigger: 'blur' }]"><el-input v-model="roomForm.name" maxlength="100" placeholder="如：教学楼 301" /></el-form-item>
        <el-form-item label="类型"><el-select v-model="roomForm.sceneType"><el-option v-for="(label, value) in sceneLabels" :key="value" :label="label" :value="value" /></el-select></el-form-item>
      </el-form>
      <template #footer><el-button @click="roomDialog = false">取消</el-button><el-button type="primary" :loading="saving" @click="saveRoom">保存</el-button></template>
    </el-dialog>

    <el-dialog v-model="bindingDialog" :title="`绑定摄像头 · ${bindingRoom?.name || ''}`" width="min(440px, 92vw)">
      <el-select v-model="bindingId" clearable placeholder="选择摄像头，清空可解除绑定" style="width:100%"><el-option v-for="camera in availableCameras" :key="camera.id" :label="camera.name" :value="camera.id" /></el-select>
      <p v-if="!availableCameras.length" class="muted">请先新增摄像头。</p>
      <template #footer><el-button @click="bindingDialog = false">取消</el-button><el-button type="primary" :loading="saving" @click="saveBinding">保存</el-button></template>
    </el-dialog>

    <el-dialog v-model="cameraDialog" :title="cameraId ? '编辑摄像头' : '新增摄像头'" width="min(500px, 92vw)">
      <el-form ref="cameraFormRef" :model="cameraForm" label-position="top">
        <el-form-item label="名称" prop="name" :rules="[{ required: true, whitespace: true, message: '填写摄像头名称', trigger: 'blur' }]"><el-input v-model="cameraForm.name" maxlength="100" placeholder="如：301 教室摄像头" /></el-form-item>
        <el-form-item label="来源"><el-select v-model="cameraForm.sourceType" @change="cameraForm.sourceUri = ''"><el-option label="内置摄像头" value="INTEGRATED" /><el-option label="USB 摄像头" value="USB" /><el-option label="网络摄像头（RTSP）" value="NETWORK_RTSP" /></el-select></el-form-item>
        <el-form-item v-if="cameraForm.sourceType === 'NETWORK_RTSP'" label="RTSP 地址" prop="sourceUri" :rules="[{ validator: validateAddress, trigger: 'blur' }]"><el-input v-model="cameraForm.sourceUri" type="password" show-password autocomplete="off" :placeholder="cameraId ? '留空保留原地址' : 'rtsp://用户名:密码@地址/路径'" /></el-form-item>
        <template v-else>
          <el-form-item label="本机设备"><el-select v-model="deviceIndex" placeholder="选择摄像头"><el-option v-for="device in devices" :key="device.index" :label="`${device.index} · ${device.name}`" :value="device.index" /></el-select><el-button :loading="scanning" @click="scanDevices">刷新设备</el-button></el-form-item>
          <p v-if="deviceError" class="muted">{{ deviceError }}</p>
          <el-form-item label="设备编号"><el-input-number v-model="deviceIndex" :min="0" :max="99" /></el-form-item>
        </template>
        <el-form-item label="识别帧率"><el-input-number v-model="cameraForm.targetFps" :min="1" :max="30" /><span class="field-hint">帧 / 秒</span></el-form-item>
      </el-form>
      <template #footer><el-button @click="cameraDialog = false">取消</el-button><el-button type="primary" :loading="saving" @click="saveCamera">保存</el-button></template>
    </el-dialog>

    <el-dialog v-model="connectionDialog" :title="`接入 · ${connectionCamera?.name || ''}`" width="min(660px, 92vw)">
      <template v-if="connectionCamera">
        <p v-if="!connectionCamera.zoneId">请先将摄像头绑定到教室。</p>
        <template v-else-if="connectionCamera.sourceType === 'INTEGRATED' || connectionCamera.sourceType === 'USB'">
          <p>设备编号 {{ connectionCamera.maskedSource || '0' }} · {{ runtime?.cameraId === connectionCamera.id ? runtimeLabel : '未运行' }}</p>
          <p v-if="runtime?.cameraId === connectionCamera.id && runtime.lastError" class="error-note">启动失败，请检查设备编号或关闭正在使用摄像头的应用。</p>
          <div class="page-actions"><el-button type="primary" :loading="controlling" :disabled="isMockMode || running" @click="startCamera">启动识别</el-button><el-button :loading="controlling" :disabled="isMockMode || !running" @click="stopCamera">停止摄像头</el-button><RouterLink v-if="runtime?.cameraId === connectionCamera.id && runtime.status === 'RUNNING'" class="text-link" to="/monitor">查看画面</RouterLink></div>
          <p v-if="isMockMode" class="muted">模拟模式不能启动实际摄像头。</p>
          <details class="result-details"><summary>命令行启动</summary><pre class="connection-command">{{ startCommand }}</pre><el-button @click="copyCommand">复制命令</el-button></details>
        </template>
        <template v-else>
          <p>将 RTSP 源接入 MediaMTX 的以下路径后，可在监控页查看视频。</p>
          <pre class="connection-command">raw/{{ connectionCamera.streamKey }}</pre>
          <p class="muted">当前识别服务支持本机摄像头；网络源暂仅用于视频预览。</p>
        </template>
        <p v-if="probeMessage" class="muted">{{ probeMessage }}</p>
      </template>
      <template #footer><el-button :loading="probing" @click="checkConfiguration">检查配置</el-button><el-button type="primary" @click="connectionDialog = false">关闭</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance } from 'element-plus'
import { isAxiosError } from 'axios'
import PageHeader from '@/components/PageHeader.vue'
import { cameraApi, inferenceApi, zoneApi } from '@/api'
import { isMockMode } from '@/api/client'
import { sceneLabels, sourceLabels } from '@/config/labels'
import { useAuthStore } from '@/stores/auth'
import type { Camera, CameraUpsert, InferenceRuntime, LocalCameraDevice, SceneType, SourceType, Zone, ZoneUpsert } from '@/types/domain'

const auth = useAuthStore()
const canEdit = computed(() => auth.user?.roles.some((role) => role === 'ADMIN' || role === 'OPERATOR'))
const rooms = ref<Zone[]>([])
const cameras = ref<Camera[]>([])
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const roomDialog = ref(false)
const roomId = ref<number>()
const roomFormRef = ref<FormInstance>()
const roomForm = reactive<ZoneUpsert>({ name: '', sceneType: 'CLASSROOM' })
const cameraDialog = ref(false)
const cameraId = ref<number>()
const cameraFormRef = ref<FormInstance>()
const cameraForm = reactive<CameraUpsert>({ name: '', sourceType: 'INTEGRATED', sourceUri: '', targetFps: 5 })
const deviceIndex = ref<number | undefined>(0)
const devices = ref<LocalCameraDevice[]>([])
const scanning = ref(false)
const deviceError = ref('')
const runtime = ref<InferenceRuntime>()
const controlling = ref(false)
let pollTimer: number | undefined
const running = computed(() => runtime.value?.status === 'RUNNING' || runtime.value?.status === 'STARTING')
const runtimeLabel = computed(() => ({ IDLE: '未启动', STARTING: '启动中', RUNNING: '运行中', STOPPED: '已停止', FAILED: '启动失败' }[runtime.value?.status || 'IDLE']))
async function scanDevices() {
  scanning.value = true
  try { devices.value = await cameraApi.localDevices(); deviceError.value = devices.value.length ? '' : '没有找到摄像头，插入 USB 摄像头后刷新' }
  catch (cause) { deviceError.value = message(cause) }
  finally { scanning.value = false }
}
async function pollRuntime() { if (isMockMode) return; try { runtime.value = await inferenceApi.runtime() } catch { runtime.value = undefined } }
async function startCamera() {
  if (!connectionCamera.value) return
  controlling.value = true
  try { runtime.value = await cameraApi.start(connectionCamera.value.id); ElMessage.success('正在启动') }
  catch (cause) { ElMessage.error(message(cause)) } finally { controlling.value = false }
}
async function stopCamera() {
  controlling.value = true
  try { runtime.value = await cameraApi.stop(); ElMessage.success('已停止') }
  catch (cause) { ElMessage.error(message(cause)) } finally { controlling.value = false }
}
const bindingDialog = ref(false)
const bindingRoom = ref<Zone>()
const bindingId = ref<number>()
const availableCameras = computed(() => cameras.value.filter((camera) => !camera.zoneId || camera.zoneId === bindingRoom.value?.id))
const connectionDialog = ref(false)
const connectionCamera = ref<Camera>()
const probing = ref(false)
const probeMessage = ref('')
const startCommand = computed(() => `powershell -ExecutionPolicy Bypass -File .\\scripts\\windows\\start-inference.ps1 -LiveCamera -ZoneId ${connectionCamera.value?.zoneId} -CameraId ${connectionCamera.value?.id} -CameraIndex ${/^\d{1,2}$/.test(connectionCamera.value?.maskedSource || '') ? connectionCamera.value?.maskedSource : '0'} -TargetFps ${connectionCamera.value?.targetFps || 5}`)

function message(cause: unknown) {
  if (isAxiosError(cause)) return cause.response?.data?.message || '操作失败，请重试'
  return cause instanceof Error ? cause.message : '操作失败，请重试'
}
async function load() {
  loading.value = true
  try { [rooms.value, cameras.value] = await Promise.all([zoneApi.list(), cameraApi.list()]); error.value = '' }
  catch { error.value = '加载失败，请刷新' }
  finally { loading.value = false }
}
function roomCamera(id: number) { return cameras.value.find((camera) => camera.zoneId === id) }
function editRoom(room?: Zone) { roomId.value = room?.id; Object.assign(roomForm, { name: room?.name || '', sceneType: room?.sceneType || 'CLASSROOM' }); roomDialog.value = true; roomFormRef.value?.clearValidate() }
async function saveRoom() {
  if (!await roomFormRef.value?.validate().catch(() => false)) return
  saving.value = true
  try { const input = { ...roomForm, name: roomForm.name.trim() }; if (roomId.value) await zoneApi.update(roomId.value, input); else await zoneApi.create(input); roomDialog.value = false; await load(); ElMessage.success('已保存') }
  catch (cause) { ElMessage.error(message(cause)) }
  finally { saving.value = false }
}
async function deleteRoom(room: Zone) {
  try { await ElMessageBox.confirm(`删除“${room.name}”？已有预警记录会保留。`, '删除教室', { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }) }
  catch { return }
  try { await zoneApi.delete(room.id); await load(); ElMessage.success('已删除') } catch (cause) { ElMessage.error(message(cause)) }
}
function bindCamera(room: Zone) { bindingRoom.value = room; bindingId.value = roomCamera(room.id)?.id; bindingDialog.value = true }
async function saveBinding() {
  if (!bindingRoom.value) return
  saving.value = true
  try { await zoneApi.replaceBindings(bindingRoom.value.id, bindingId.value ? [{ cameraId: bindingId.value, viewRole: 'SINGLE', weight: 1 }] : []); bindingDialog.value = false; await load(); ElMessage.success('已保存') }
  catch (cause) { ElMessage.error(message(cause)) } finally { saving.value = false }
}
function editCamera(camera?: Camera, sourceType: SourceType = 'INTEGRATED') { cameraId.value = camera?.id; Object.assign(cameraForm, { name: camera?.name || (sourceType === 'USB' ? 'USB 摄像头' : sourceType === 'INTEGRATED' ? '前置摄像头' : ''), sourceType: camera?.sourceType || sourceType, sourceUri: '', targetFps: camera?.targetFps || 5 }); deviceIndex.value = /^\d+$/.test(camera?.maskedSource || '') ? Number(camera?.maskedSource) : (camera?.sourceType || sourceType) === 'USB' ? undefined : 0; cameraDialog.value = true; void scanDevices(); cameraFormRef.value?.clearValidate() }
function validateAddress(_rule: unknown, value: string, callback: (error?: Error) => void) {
  if (!value && cameraId.value && cameras.value.find((camera) => camera.id === cameraId.value)?.sourceType === 'NETWORK_RTSP') { callback(); return }
  try { const url = new URL(value); if (url.protocol !== 'rtsp:' || !url.hostname) throw new Error(); callback() }
  catch { callback(new Error('填写完整的 RTSP 地址')) }
}
async function saveCamera() {
  if (cameraForm.sourceType !== 'NETWORK_RTSP' && deviceIndex.value == null) { ElMessage.warning('请选择摄像头'); return }
  if (!await cameraFormRef.value?.validate().catch(() => false)) return
  saving.value = true
  try {
    const input = { ...cameraForm, name: cameraForm.name.trim(), sourceUri: cameraForm.sourceType === 'NETWORK_RTSP' ? cameraForm.sourceUri?.trim() || undefined : String(deviceIndex.value ?? 0) }
    if (cameraId.value) await cameraApi.update(cameraId.value, input); else await cameraApi.create(input)
    cameraDialog.value = false; await load(); ElMessage.success('已保存')
  } catch (cause) { ElMessage.error(message(cause)) } finally { saving.value = false }
}
async function deleteCamera(camera: Camera) {
  try { await ElMessageBox.confirm(`删除“${camera.name}”？`, '删除摄像头', { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }) }
  catch { return }
  try { await cameraApi.delete(camera.id); await load(); ElMessage.success('已删除') } catch (cause) { ElMessage.error(message(cause)) }
}
function connectionInfo(camera: Camera) { connectionCamera.value = camera; probeMessage.value = ''; connectionDialog.value = true }
async function checkConfiguration() {
  if (!connectionCamera.value) return
  probing.value = true
  try { probeMessage.value = (await cameraApi.probe(connectionCamera.value.id)).message || '已检查' } catch (cause) { ElMessage.error(message(cause)) }
  finally { probing.value = false }
}
async function copyCommand() { try { await navigator.clipboard.writeText(startCommand.value); ElMessage.success('已复制') } catch { ElMessage.warning('请手动复制命令') } }
onMounted(() => { void load(); void pollRuntime(); pollTimer = window.setInterval(pollRuntime, 1500) })
onBeforeUnmount(() => window.clearInterval(pollTimer))
</script>
