<script setup lang="ts">
import { ref } from "vue"
import { useRouter } from "vue-router"
import { ElMessage } from "element-plus"
import { api, saveSession } from "../api/client"
import type { LoginResult } from "../api/types"
import { messageOf } from "../labels"

const router = useRouter()
const username = ref("admin")
const password = ref("")
const loading = ref(false)

async function submit() {
  loading.value = true
  try {
    const result = await api<LoginResult>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username: username.value, password: password.value }),
    })
    saveSession(result)
    await router.push("/rooms")
  } catch (error) {
    ElMessage.error(messageOf(error))
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <form class="login-card" @submit.prevent="submit">
      <h1>火情监控</h1>
      <el-form label-position="top">
        <el-form-item label="用户名">
          <el-input v-model="username" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="password" type="password" show-password />
        </el-form-item>
        <el-button type="primary" native-type="submit" :loading="loading">登录</el-button>
      </el-form>
    </form>
  </div>
</template>
