<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import {
  bootstrap,
  getCurrentUser,
  hasAllowedProductRoles,
  loginWithDevBypass,
  loginWithIam,
  isAuthLoading,
} from '@/composables/useAuth';
import { loadSnapshot } from '@/composables/useSnapshot';
import { getProductRole } from '@/composables/useProductRole';
import { pushToast } from '@/composables/useActionStub';
import { apiUrl } from '@/composables/useApiBase';

const router = useRouter();
const user = getCurrentUser();
const authLoading = isAuthLoading();
const devBypass = ref(false);
const iafConfigured = ref(true);
const configLoading = ref(true);
const submitting = ref<'iam' | 'dev' | null>(null);

async function finishLoginEntry(): Promise<void> {
  if (!hasAllowedProductRoles()) {
    await router.replace('/workbench');
    return;
  }
  await loadSnapshot(getProductRole().value);
  await router.replace('/workbench');
}

async function enterWithIam(): Promise<void> {
  if (submitting.value || !iafConfigured.value) return;
  submitting.value = 'iam';
  try {
    await loginWithIam();
  } catch (e) {
    const detail = e instanceof Error ? e.message : String(e);
    pushToast({
      kind: 'error',
      title: '登录失败',
      detail: /iaf|统一身份/i.test(detail)
        ? '无法连接统一身份服务，请确认 IAM 配置或联系管理员。'
        : detail,
    });
    submitting.value = null;
  }
}

async function enterWithDevBypass(): Promise<void> {
  if (submitting.value) return;
  submitting.value = 'dev';
  try {
    if (!user.value) await loginWithDevBypass();
    await finishLoginEntry();
  } catch (e) {
    const detail = e instanceof Error ? e.message : String(e);
    pushToast({
      kind: 'error',
      title: '进入失败',
      detail: detail,
    });
  } finally {
    submitting.value = null;
  }
}

onMounted(async () => {
  await bootstrap();
  try {
    const resp = await fetch(apiUrl('/auth/iaf/config'), { headers: { Accept: 'application/json' }, credentials: 'include' });
    if (resp.ok) {
      const cfg = (await resp.json()) as {
        configured?: boolean;
        development_iam_bypass_enabled?: boolean;
      };
      devBypass.value = cfg.development_iam_bypass_enabled === true;
      iafConfigured.value = cfg.configured !== false;
    }
  } catch {
    devBypass.value = false;
    iafConfigured.value = false;
  } finally {
    configLoading.value = false;
  }
  if (user.value) {
    await finishLoginEntry();
  }
});
</script>

<template>
  <main class="focus-page login-page">
    <div class="login-gate-wrap">
      <section class="login-gate-card" aria-labelledby="login-gate-title">
        <header class="login-gate-card-header">
          <h1 id="login-gate-title" class="login-gate-card-title">登录政务数据大脑</h1>
          <p class="login-gate-card-sub">使用统一身份认证进入系统，岗位与权限由 IAM 与治理策略共同决定。</p>
        </header>
        <div class="login-gate-card-body">
          <div class="login-gate-field">
            <label for="login-gate-iam">统一身份认证</label>
            <div class="login-gate-iam-box">
              通过<strong>浪潮云统一身份（IAF）</strong>登录；登录成功后将回到工作台。
              <template v-if="!configLoading && !iafConfigured">
                <span class="login-gate-config-warn">当前环境尚未完成 IAM 配置，请联系管理员。</span>
              </template>
            </div>
            <div class="login-gate-actions">
              <button
                id="login-gate-iam"
                type="button"
                class="gov-btn gov-btn-primary"
                :disabled="authLoading || submitting !== null || configLoading || !iafConfigured"
                @click="enterWithIam"
              >
                {{ submitting === 'iam' || authLoading ? '跳转中…' : '统一身份登录' }}
              </button>
            </div>
          </div>

          <div v-if="devBypass" class="login-gate-divider" role="separator" aria-label="或">
            <span>或</span>
          </div>

          <div v-if="devBypass" class="login-gate-field login-gate-dev-section">
            <label for="login-gate-submit">开发环境</label>
            <div class="login-gate-iam-box login-gate-dev-box">
              当前为<strong>开发环境</strong>：可直接进入系统体验各岗位页面，无需连接统一身份中心。
            </div>
            <div class="login-gate-actions">
              <button
                id="login-gate-submit"
                type="button"
                class="gov-btn gov-btn-secondary"
                :disabled="authLoading || submitting !== null"
                @click="enterWithDevBypass"
              >
                {{ submitting === 'dev' ? '进入中…' : '进入系统（开发环境）' }}
              </button>
            </div>
            <p class="login-gate-footnote">
              开发免登录仅用于本机调试；客户现场部署请勿启用 IAM bypass 相关环境变量。
            </p>
          </div>
        </div>
      </section>
    </div>
  </main>
</template>

<style scoped>
.login-page {
  min-height: calc(100vh - 160px);
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding-top: 48px;
}
.login-gate-divider {
  display: flex;
  align-items: center;
  gap: 12px;
  color: var(--b-muted);
  font-size: 13px;
}
.login-gate-divider::before,
.login-gate-divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: var(--b-border);
}
.login-gate-dev-section {
  padding-top: 2px;
}
.login-gate-dev-box {
  border-style: solid;
  background: #fffdf5;
}
.login-gate-config-warn {
  display: block;
  margin-top: 8px;
  color: #8a4b00;
}
</style>
