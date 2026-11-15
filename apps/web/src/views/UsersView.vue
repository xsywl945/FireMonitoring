<script setup lang="ts">
import { onMounted, reactive, ref } from "vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { api } from "../api/client"
import type { User } from "../api/types"
import { messageOf, roleLabels } from "../labels"

const users = ref<User[]>([])
const visible = ref(false)
const editing = ref<User | null>(null)
const form = reactive({
  username: "",
  display_name: "",
  password: "",
  role: "operator" as "admin" | "operator",
})

async function load() {
  users.value = await api<User[]>("/users")
}

function openCreate() {
  editing.value = null
  form.username = ""
  form.display_name = ""
  form.password = ""
  form.role = "operator"
  visible.value = true
}

function openEdit(row: User) {
  editing.value = row
  form.username = row.username
  form.display_name = row.display_name
  form.password = ""
  form.role = row.role
  visible.value = true
}

async function save() {
  try {
    if (editing.value) {
      const body: { display_name: string; role: string; password?: string } = {
        display_name: form.display_name,
        role: form.role,
      }
      if (form.password) body.password = form.password
      await api(`/users/${editing.value.id}`, { method: "PATCH", body: JSON.stringify(body) })
    } else {
      await api("/users", {
        method: "POST",
        body: JSON.stringify({
          username: form.username,
          display_name: form.display_name,
          password: form.password,
          role: form.role,
        }),
      })
    }
    visible.value = false
    await load()
  } catch (error) {
    ElMessage.error(messageOf(error))
  }
}

async function remove(row: User) {
  try {
    await ElMessageBox.confirm(`删除账号 ${row.username}？`, "删除")
  } catch {
    return
  }
  try {
    await api(`/users/${row.id}`, { method: "DELETE" })
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
      <strong>用户</strong>
      <el-button type="primary" @click="openCreate">新建</el-button>
    </div>
    <el-table :data="users" border>
      <el-table-column prop="username" label="账号" width="160" />
      <el-table-column prop="display_name" label="姓名" />
      <el-table-column label="角色" width="120">
        <template #default="{ row }">{{ roleLabels[row.role] || row.role }}</template>
      </el-table-column>
      <el-table-column label="操作" width="140">
        <template #default="{ row }">
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button link type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-dialog v-model="visible" :title="editing ? '编辑用户' : '新建用户'" width="420px">
      <el-form label-position="top">
        <el-form-item label="账号"><el-input v-model="form.username" :disabled="!!editing" /></el-form-item>
        <el-form-item label="姓名"><el-input v-model="form.display_name" /></el-form-item>
        <el-form-item label="角色">
          <el-select v-model="form.role">
            <el-option label="管理员" value="admin" />
            <el-option label="值班员" value="operator" />
          </el-select>
        </el-form-item>
        <el-form-item :label="editing ? '重置密码' : '密码'">
          <el-input v-model="form.password" type="password" show-password :placeholder="editing ? '留空则不修改' : ''" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>
