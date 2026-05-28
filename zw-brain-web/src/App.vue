<script setup lang="ts">
import { onMounted, ref, computed, watch } from 'vue';
import { RouterLink, RouterView, useRouter, useRoute } from 'vue-router';
import {
  bootstrap as bootstrapAuth,
  getCurrentUser,
  getSession,
  getAllowedProductRoles,
  hasAllowedProductRoles,
  hasPendingOAuthCallback,
  isAuthLoading,
  logout,
  PRODUCT_ROLE_LABELS,
} from '@/composables/useAuth';
import { loadSnapshot, useWebUiConfig, useSnapshot } from '@/composables/useSnapshot';
import { pushToast } from '@/composables/useActionStub';
import ActionToast from '@/components/ActionToast.vue';
import ProductTopNav from '@/components/ProductTopNav.vue';
import { getProductRole, setProductRole } from '@/composables/useProductRole';
import { defaultRouteForRole, isRouteAllowedForRole } from '@/lib/pageAccess';

const router = useRouter();
const route = useRoute();
const user = getCurrentUser();
const session = getSession();
const authLoading = isAuthLoading();

const userMenuTitle = computed(() => {
  if (session.value?.development_iam_bypass) {
    return '开发环境免统一身份登录（IAM bypass）';
  }
  const u = user.value;
  if (!u) return '';
  const extra = [u.username, u.orgCode].filter(Boolean).join(' · ');
  return extra || u.displayName;
});
const { source: snapSource } = useSnapshot();
const webui = useWebUiConfig();
const currentRole = getProductRole();
const initError = ref<string | null>(null);

const deploymentLabel = computed(() => String(webui.value.deploymentLabel ?? ''));
const legalNotice = computed(() => String(webui.value.legalNotice ?? ''));
const allowRoleSwitch = computed(() => Boolean(webui.value.allowRoleSwitch));
const isLoginRoute = computed(() => route.path === '/login');
const roleSwitchBusy = ref(false);
const allowedRoles = computed(() => {
  if (!user.value) return [];
  void session.value;
  return getAllowedProductRoles();
});

const currentRoleLabel = computed(() => PRODUCT_ROLE_LABELS[currentRole.value] ?? currentRole.value);

const showRoleControl = computed(() => Boolean(user.value && !isLoginRoute.value && currentRoleLabel.value));
const canSwitchRole = computed(() => allowRoleSwitch.value && allowedRoles.value.length > 1);

const missingProductRole = computed(
  () => Boolean(user.value && !isLoginRoute.value && !hasAllowedProductRoles())
);

async function refreshAll() {
  initError.value = null;
  try {
    await bootstrapAuth();
    if (!user.value) {
      if (!isLoginRoute.value) await router.replace('/login');
      return;
    }
    if (!hasAllowedProductRoles()) {
      if (route.path !== '/workbench') await router.replace('/workbench');
      return;
    }
    await loadSnapshot(currentRole.value);
  } catch (e) {
    const detail = e instanceof Error ? e.message : String(e);
    initError.value = detail;
    if (!user.value && !isLoginRoute.value) await router.replace('/login');
  }
}

watch(
  allowedRoles,
  (roles) => {
    if (!roles.length || !user.value) return;
    if (!roles.includes(currentRole.value)) {
      const prev = currentRole.value;
      const next = roles[0];
      setProductRole(next);
      pushToast({
        kind: 'info',
        title: '岗位已自动调整',
        detail: `当前登录身份无权使用「${PRODUCT_ROLE_LABELS[prev] ?? prev}」，已切换为「${PRODUCT_ROLE_LABELS[next] ?? next}」。`,
      });
    }
  },
  { immediate: true }
);

async function onRoleChange(event: Event) {
  const target = event.target as HTMLSelectElement;
  const chosen = target.value;
  if (chosen === currentRole.value) return;
  setProductRole(chosen);
  roleSwitchBusy.value = true;
  try {
    await loadSnapshot(currentRole.value, { soft: true });
  } finally {
    roleSwitchBusy.value = false;
  }
  const roleLabel = PRODUCT_ROLE_LABELS[chosen] ?? chosen;
  if (!isRouteAllowedForRole(router.currentRoute.value.path, currentRole.value)) {
    const dest = defaultRouteForRole(currentRole.value, router.currentRoute.value.path);
    await router.replace(dest);
    pushToast({
      kind: 'info',
      title: '已切换岗位',
      detail: `当前身份：${roleLabel}。该岗位无权停留在此页，已跳转到可用入口。`,
    });
    return;
  }
  pushToast({
    kind: 'info',
    title: '已切换岗位',
    detail: `当前身份：${roleLabel}。页面与权限已按新岗位刷新。`,
  });
}

onMounted(() => {
  void refreshAll();
});

watch(
  () => route.path,
  (path) => {
    // IAM 回跳时 onMounted 与路由重定向会并发 bootstrap；跳过二次换票以免 state 被提前消费。
    if (hasPendingOAuthCallback()) return;
    if (path !== '/login' && !user.value) void refreshAll();
  }
);
</script>

<template>
  <header class="global-header">
    <div class="global-header-inner">
      <RouterLink to="/workbench" class="global-brand">
        <span class="gov-logo-mark" aria-hidden="true"></span>
        <div>
          <div class="brand-title">政务数据大脑</div>
          <div class="brand-subtitle">一脑通数智，万事惠民生</div>
        </div>
      </RouterLink>
      <div v-if="deploymentLabel" class="deployment-label">{{ deploymentLabel }}</div>
      <nav v-if="!isLoginRoute" class="helper-links" aria-label="顶部辅助入口">
        <button
          v-if="!user"
          type="button"
          class="header-auth-link"
          title="前往登录页"
          :disabled="authLoading"
          @click="router.push('/login')"
        >{{ authLoading ? '登录中…' : '登录' }}</button>
      </nav>
      <div class="global-actions">
        <div v-if="user && !isLoginRoute" class="user-menu">
          <span class="user-menu-button" :title="userMenuTitle">{{ user.displayName || user.username || '当前用户' }}</span>
          <button type="button" class="user-menu-logout" @click="logout">退出</button>
        </div>
        <div v-else-if="!isLoginRoute" class="identity-label" aria-live="polite">当前账号</div>
        <div v-if="showRoleControl && !missingProductRole" class="role-control">
          <span>当前岗位</span>
          <template v-if="canSwitchRole">
            <label class="sr-only" for="role-switch">切换岗位身份</label>
            <select
              id="role-switch"
              class="role-select"
              :class="{ 'role-select-busy': roleSwitchBusy }"
              :value="currentRole"
              :disabled="roleSwitchBusy"
              @change="onRoleChange"
            >
              <option
                v-for="code in allowedRoles"
                :key="code"
                :value="code"
              >{{ PRODUCT_ROLE_LABELS[code] || code }}</option>
            </select>
          </template>
          <span v-else class="role-readonly" :title="currentRole">{{ currentRoleLabel }}</span>
        </div>
      </div>
    </div>
  </header>

  <main class="app-shell-main">
    <section v-if="missingProductRole" class="app-frame app-frame-live no-product-role-shell">
      <div class="login-gate-wrap">
        <section class="login-gate-card no-product-role-card" aria-labelledby="no-product-role-title">
          <header class="login-gate-card-header">
            <h1 id="no-product-role-title" class="login-gate-card-title">暂无可用岗位权限</h1>
            <p class="login-gate-card-sub">
              您的账号已登录，但尚未分配政务数据大脑的产品岗位。请联系系统管理员在身份治理中为您的账号添加用户角色权限后，再重新登录使用。
            </p>
          </header>
          <div class="login-gate-card-body">
            <div class="login-gate-iam-box no-product-role-hint">
              若您刚完成 IAM 绑定，请等待管理员同步岗位后刷新页面；仍无法进入时请提供登录账号与所属组织，便于管理员排查。
            </div>
            <div class="login-gate-actions">
              <button
                id="no-product-role-logout"
                type="button"
                class="gov-btn gov-btn-primary"
                @click="logout"
              >退出登录</button>
            </div>
          </div>
        </section>
      </div>
    </section>
    <section v-else class="app-frame app-frame-live">
      <div id="app-router" class="min-w-0">
        <div
          v-if="!isLoginRoute && snapSource === 'loading' && !roleSwitchBusy"
          class="boot-banner boot-banner-info"
        >正在加载数据……</div>
        <div v-else-if="snapSource === 'error'" class="boot-banner boot-banner-warn">
          数据暂不可达。请确认 brain REST（8800）已启动后刷新。
        </div>
        <ProductTopNav v-if="!isLoginRoute && !authLoading" :role="currentRole" />
        <div v-if="authLoading && !isLoginRoute" class="boot-banner boot-banner-info">正在完成登录…</div>
        <RouterView v-if="!authLoading || isLoginRoute" />
        <div v-if="initError && !missingProductRole" class="boot-banner boot-banner-warn">初始化告警：{{ initError }}</div>
      </div>
    </section>
  </main>

  <footer class="site-footer">
    <div class="site-footer-inner">
      <span>政务数据大脑</span>
      <span v-if="legalNotice">{{ legalNotice }}</span>
    </div>
  </footer>

  <ActionToast />
</template>

<style scoped>
.boot-banner {
  padding: 8px 12px;
  border-radius: 8px;
  font-size: 13px;
  margin-bottom: 12px;
}
.boot-banner-info {
  background: #e8f2fc;
  color: #0048a8;
  border: 1px solid #d4e2f4;
}
.boot-banner-ok {
  background: #effaee;
  color: #1f5e1f;
  border: 1px solid #9ad29a;
}
.boot-banner-warn {
  background: #fff8e6;
  color: #6b4f00;
  border: 1px solid #f0c674;
}
.global-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  text-decoration: none;
  color: inherit;
}
.gov-logo-mark {
  width: 24px;
  height: 24px;
  border-radius: 8px;
  background: linear-gradient(135deg, #006be6, #0048a8);
  display: inline-block;
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
.min-w-0 {
  min-width: 0;
}
.role-select-busy {
  opacity: 0.65;
  cursor: wait;
}
.role-readonly {
  font-size: 13px;
  color: var(--b-text, #1a1a1a);
  padding: 4px 8px;
  border: 1px solid var(--b-border, #d4e2f4);
  border-radius: 6px;
  background: #f7faff;
}
.no-product-role-shell {
  display: flex;
  justify-content: center;
  padding-top: 48px;
}
.no-product-role-card {
  max-width: 560px;
}
.no-product-role-hint {
  color: var(--b-muted, #5c6370);
}
</style>
