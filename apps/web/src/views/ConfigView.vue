<script setup lang="ts">
import { onMounted, ref } from "vue"
import { ElMessage } from "element-plus"
import { api } from "../api/client"
import { messageOf } from "../labels"

type Draft = { [key: string]: DraftValue }
type DraftValue = boolean | string | string[] | Draft

const titles: Record<string, string> = {
  server: "服务",
  database: "数据库",
  minio: "MinIO",
  mediamtx: "MediaMTX",
  llm: "大模型",
  sms: "短信",
  model: "模型",
  temporal: "时序",
  localization: "定位",
  panel: "报警节点",
  pump: "水泵",
  auth: "登录",
  cameras: "摄像头默认值",
  health: "画面健康",
  suppression: "灭火控制",
  demo: "演示",
  timezone: "时区",
}

const sample = ref<Record<string, unknown> | null>(null)
const draft = ref<Draft>({})
const notice = ref("")

function isRecord(value: DraftValue): value is Draft {
  return typeof value === "object" && !Array.isArray(value)
}

function toDraft(value: unknown): DraftValue {
  if (typeof value === "boolean") return value
  if (Array.isArray(value)) return value.map(String)
  if (value && typeof value === "object") {
    const out: Draft = {}
    for (const [key, item] of Object.entries(value as Record<string, unknown>)) out[key] = toDraft(item)
    return out
  }
  return value === null || value === undefined ? "" : String(value)
}

function fromDraft(value: DraftValue, current: unknown): unknown {
  if (typeof current === "boolean") return value
  if (Array.isArray(current)) return (value as string[]).map((item) => item.trim()).filter((item) => item !== "")
  if (current && typeof current === "object") {
    const out: Record<string, unknown> = {}
    const source = value as Draft
    for (const [key, item] of Object.entries(current as Record<string, unknown>)) {
      out[key] = fromDraft(source[key], item)
    }
    return out
  }
  if (typeof current === "number") return Number(value)
  if (current === null) {
    const text = String(value).trim()
    return text === "" ? null : Number(text)
  }
  return value
}

async function load() {
  const config = await api<Record<string, unknown>>("/config")
  sample.value = config
  draft.value = toDraft(config) as Draft
}

async function save() {
  if (!sample.value) return
  try {
    const result = await api<{ restart_required: boolean; config: Record<string, unknown> }>("/config", {
      method: "PUT",
      body: JSON.stringify(fromDraft(draft.value, sample.value)),
    })
    sample.value = result.config
    draft.value = toDraft(result.config) as Draft
    notice.value = "已写入 config.json。需要重启后端后才会生效。"
  } catch (error) {
    ElMessage.error(messageOf(error))
  }
}

onMounted(load)
</script>

<template>
  <div v-if="sample" class="stack">
    <el-alert
      type="warning"
      :closable="false"
      title="这里只改非密钥项。密钥不返回，也不能在这里修改。保存后写入 config.json，需要重启后端才生效。"
    />
    <el-alert v-if="notice" type="success" :closable="false" :title="notice" />
    <div v-for="(section, sectionName) in draft" :key="sectionName" class="panel">
      <h2 class="section-title">{{ titles[sectionName] || sectionName }}</h2>
      <template v-if="isRecord(section)">
        <div v-for="(field, fieldName) in section" :key="fieldName" class="config-row">
          <div>{{ fieldName }}</div>
          <div v-if="isRecord(field)">
            <div v-for="(child, childName) in field" :key="childName" class="config-row">
              <div>{{ childName }}</div>
              <el-switch
                v-if="typeof child === 'boolean'"
                :model-value="child"
                @update:model-value="field[childName] = Boolean($event)"
              />
              <el-input
                v-else-if="Array.isArray(child)"
                type="textarea"
                :model-value="child.join('\n')"
                @update:model-value="field[childName] = String($event).split('\n')"
              />
              <el-input v-else :model-value="String(child)" @update:model-value="field[childName] = String($event)" />
            </div>
          </div>
          <el-switch
            v-else-if="typeof field === 'boolean'"
            :model-value="field"
            @update:model-value="section[fieldName] = Boolean($event)"
          />
          <el-input
            v-else-if="Array.isArray(field)"
            type="textarea"
            :model-value="field.join('\n')"
            @update:model-value="section[fieldName] = String($event).split('\n')"
          />
          <el-input v-else :model-value="String(field)" @update:model-value="section[fieldName] = String($event)" />
        </div>
      </template>
      <el-input v-else :model-value="String(section)" @update:model-value="draft[sectionName] = String($event)" />
    </div>
    <div>
      <el-button type="primary" @click="save">保存</el-button>
    </div>
  </div>
</template>
