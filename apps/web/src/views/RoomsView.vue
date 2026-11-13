<script setup lang="ts">
import { onMounted, reactive, ref } from "vue"
import { useRouter } from "vue-router"
import { ElMessage, ElMessageBox } from "element-plus"
import { api, currentRole } from "../api/client"
import type { Room } from "../api/types"
import { messageOf, sceneLabels } from "../labels"

const router = useRouter()
const admin = currentRole() === "admin"
const rooms = ref<Room[]>([])
const visible = ref(false)
const editing = ref<Room | null>(null)
const form = reactive({ name: "", scene_type: "classroom" })

async function load() {
  rooms.value = await api<Room[]>("/rooms")
}

function openCreate() {
  editing.value = null
  form.name = ""
  form.scene_type = "classroom"
  visible.value = true
}

function openEdit(row: Room) {
  editing.value = row
  form.name = row.name
  form.scene_type = row.scene_type
  visible.value = true
}

async function save() {
  const body = JSON.stringify(form)
  try {
    if (editing.value) {
      await api(`/rooms/${editing.value.id}`, { method: "PUT", body })
    } else {
      await api("/rooms", { method: "POST", body })
    }
    visible.value = false
    await load()
  } catch (error) {
    ElMessage.error(messageOf(error))
  }
}

async function remove(row: Room) {
  try {
    await ElMessageBox.confirm(`删除教室 ${row.name}？`, "删除")
  } catch {
    return
  }
  try {
    await api(`/rooms/${row.id}`, { method: "DELETE" })
    await load()
  } catch (error) {
    ElMessage.error(messageOf(error))
  }
}

onMounted(load)
</script>

<template>
  <div class="panel">
    <div class="toolbar">
      <strong>教室</strong>
      <el-button v-if="admin" type="primary" @click="openCreate">新建</el-button>
    </div>
    <el-table :data="rooms" border>
      <el-table-column prop="name" label="名称" />
      <el-table-column label="场景">
        <template #default="{ row }">{{ sceneLabels[row.scene_type] || row.scene_type }}</template>
      </el-table-column>
      <el-table-column label="摄像头">
        <template #default="{ row }">{{ row.cameras.length }} 路</template>
      </el-table-column>
      <el-table-column label="操作" width="220">
        <template #default="{ row }">
          <el-button link type="primary" @click="router.push(`/rooms/${row.id}`)">详情</el-button>
          <el-button v-if="admin" link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button v-if="admin" link type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-dialog v-model="visible" :title="editing ? '编辑教室' : '新建教室'" width="420px">
      <el-form label-position="top">
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="场景">
          <el-select v-model="form.scene_type">
            <el-option v-for="(label, value) in sceneLabels" :key="value" :label="label" :value="value" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>
