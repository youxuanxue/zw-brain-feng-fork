<script setup lang="ts">
import { onMounted, ref, computed, watch } from 'vue';
import { RouterLink, RouterView, useRouter, useRoute } from 'vue-router';
import {
  bootstrap as bootstrapAuth,
  getCurrentUser,
  getSession,
  getAllowedProductRoles,
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

async function refreshAll() {
  try {
    await bootstrapAuth();
    if (!user.value) {
      if (!isLoginRoute.value) await router.replace('/login');
      return;
    }
    await loadSnapshot(currentRole.value);
  } catch (e) {
    initError.value = e instanceof Error ? e.message : String(e);
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
    const dest = defaultRouteForRole(currentRole.value);
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
          <div class="brand-subtitle">让数据共享少填、快办、可追溯</div>
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
        <div v-if="allowRoleSwitch && allowedRoles.length && !isLoginRoute" class="role-control">
          <span>当前岗位</span>
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
        </div>
      </div>
    </div>
  </header>

  <main class="app-shell-main">
    <section class="app-frame app-frame-live">
      <div id="app-router" class="min-w-0">
        <div
          v-if="!isLoginRoute && snapSource === 'loading' && !roleSwitchBusy"
          class="boot-banner boot-banner-info"
        >正在加载数据……</div>
        <div v-else-if="snapSource === 'error'" class="boot-banner boot-banner-warn">
          数据暂不可达。请确认 brain REST（8800）已启动后刷新。
        </div>
        <ProductTopNav v-if="!isLoginRoute" :role="currentRole" />
        <RouterView />
        <div v-if="initError" class="boot-banner boot-banner-warn">初始化告警：{{ initError }}</div>
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
</style>
