<template>
  <main class="login-page"><section class="login-form-wrap panel">
    <h1>火灾识别与预警系统</h1>
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent="submit">
      <el-form-item label="账号" prop="username"><el-input v-model="form.username" autocomplete="username" :prefix-icon="User" /></el-form-item>
      <el-form-item label="密码" prop="password"><el-input v-model="form.password" type="password" autocomplete="current-password" show-password :prefix-icon="Lock" /></el-form-item>
      <el-button type="primary" native-type="submit" :loading="auth.loading">登录</el-button>
    </el-form>
    <p class="muted">本地演示账号：admin / 123456</p>
  </section></main>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Lock, User } from '@element-plus/icons-vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const formRef = ref<FormInstance>()
const form = reactive({ username: 'admin', password: '123456' })
const rules: FormRules = {
  username: [{ required: true, message: '请输入账号', trigger: 'blur' }, { min: 3, message: '账号至少 3 位', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }, { min: 6, message: '密码至少 6 位', trigger: 'blur' }],
}

async function submit() {
  try {
    await formRef.value?.validate()
    await auth.login(form.username, form.password)
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/monitor'
    await router.replace(redirect)
  } catch (error) {
    if (error instanceof Error) ElMessage.error(error.message)
  }
}
</script>
