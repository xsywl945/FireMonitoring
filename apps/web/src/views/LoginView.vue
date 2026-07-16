<template>
  <main class="login-page">
    <section class="login-visual">
      <div class="login-grid" />
      <div class="login-brand">
        <div class="brand-mark brand-mark-large"><span class="brand-flame" /></div>
        <span>燧巡 · 智能火灾监控</span>
      </div>
      <div class="login-story">
        <p class="page-eyebrow">DUAL-VIEW FIRE INTELLIGENCE</p>
        <h1>看见早期风险，<br /><em>让预警更有依据。</em></h1>
        <p>融合双视角视觉定位、时序证据与云端多模态研判，为教室和实验室提供可解释的实时火灾预警。</p>
        <div class="login-capabilities">
          <span><i /> 双视角决策融合</span>
          <span><i /> YOLO 实时检测</span>
          <span><i /> 语义风险研判</span>
        </div>
      </div>
      <div class="login-signal" aria-hidden="true">
        <div class="signal-orbit orbit-one" />
        <div class="signal-orbit orbit-two" />
        <div class="signal-core"><span /></div>
      </div>
      <footer>面向教学场景的研究型原型 · 非消防设施替代品</footer>
    </section>

    <section class="login-panel">
      <div class="login-form-wrap">
        <div class="login-mobile-brand">
          <div class="brand-mark"><span class="brand-flame" /></div>
          <strong>燧巡</strong>
        </div>
        <p class="page-eyebrow">OPERATOR CONSOLE</p>
        <h2>欢迎回来</h2>
        <p class="login-intro">登录后进入实时监控与事件处置控制台</p>

        <el-form ref="formRef" :model="form" :rules="rules" label-position="top" size="large" @submit.prevent="submit">
          <el-form-item label="账号" prop="username">
            <el-input v-model="form.username" autocomplete="username" placeholder="请输入操作员账号" :prefix-icon="User" />
          </el-form-item>
          <el-form-item label="密码" prop="password">
            <el-input v-model="form.password" type="password" autocomplete="current-password" placeholder="至少 8 位" show-password :prefix-icon="Lock" @keyup.enter="submit" />
          </el-form-item>
          <div class="login-options"><el-checkbox v-model="remember">保持登录</el-checkbox><span>仅用于本机演示</span></div>
          <el-button class="login-submit" type="primary" native-type="submit" :loading="auth.loading">进入控制台</el-button>
        </el-form>
        <div class="demo-credential">
          <span>演示账号</span><code>admin</code><span class="divider">/</span><code>FireAdmin123!</code>
        </div>
        <p class="security-note"><el-icon><CircleCheck /></el-icon> 访问凭证仅保存在当前浏览器中</p>
      </div>
    </section>
  </main>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { CircleCheck, Lock, User } from '@element-plus/icons-vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const formRef = ref<FormInstance>()
const remember = ref(true)
const form = reactive({ username: 'admin', password: 'FireAdmin123!' })
const rules: FormRules = {
  username: [{ required: true, message: '请输入账号', trigger: 'blur' }, { min: 3, message: '账号至少 3 位', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }, { min: 8, message: '密码至少 8 位', trigger: 'blur' }],
}

async function submit() {
  try {
    await formRef.value?.validate()
    await auth.login(form.username, form.password)
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/dashboard'
    await router.replace(redirect)
  } catch (error) {
    if (error instanceof Error) ElMessage.error(error.message)
  }
}
</script>
