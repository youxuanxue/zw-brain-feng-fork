<script setup lang="ts">
import { onMounted, ref, computed } from 'vue';
import { RouterLink, RouterView } from 'vue-router';
import {
  bootstrap as bootstrapAuth,
  getCurrentUser,
  getAllowedProductRoles,
  logout,
  startLogin,
  PRODUCT_ROLE_LABELS,
} from '@/composables/useAuth';
import { loadSnapshot, useWebUiConfig, useSnapshot } from '@/composables/useSnapshot';
import ActionToast from '@/components/ActionToast.vue';

const user = getCurrentUser();
const { source: snapSource } = useSnapshot();
const webui = useWebUiConfig();
const currentRole = ref<string>('ROLE_ORGAN_OPERATER');
const allowedRoles = ref<string[]>([]);
const initError = ref<string | null>(null);

const deploymentLabel = computed(() => String(webui.value.deploymentLabel ?? ''));
const legalNotice = computed(() => String(webui.value.legalNotice ?? ''));
const allowRoleSwitch = computed(() => Boolean(webui.value.allowRoleSwitch));

async function refreshAll() {
  try {
    await bootstrapAuth();
    allowedRoles.value = getAllowedProductRoles();
    if (allowedRoles.value.length && !allowedRoles.value.includes(currentRole.value)) {
      currentRole.value = allowedRoles.value[0];
    }
    await loadSnapshot(currentRole.value);
  } catch (e) {
    initError.value = e instanceof Error ? e.message : String(e);
  }
}

async function onRoleChange(event: Event) {
  const target = event.target as HTMLSelectElement;
  currentRole.value = target.value;
  await loadSnapshot(currentRole.value);
}

onMounted(() => {
  void refreshAll();
});
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
      <nav class="helper-links" aria-label="顶部辅助入口">
        <button
          v-if="!user"
          type="button"
          class="header-auth-link"
          title="前往统一身份登录"
          @click="startLogin"
        >登录</button>
      </nav>
      <div class="global-actions">
        <div v-if="user" class="user-menu">
          <span class="user-menu-button">{{ user.displayName || user.username || '当前用户' }}</span>
          <button type="button" class="user-menu-item" @click="logout">退出登录</button>
        </div>
        <div v-else class="identity-label" aria-live="polite">当前账号</div>
        <div v-if="allowRoleSwitch && allowedRoles.length" class="role-control">
          <span>当前岗位</span>
          <label class="sr-only" for="role-switch">切换岗位身份</label>
          <select id="role-switch" class="role-select" :value="currentRole" @change="onRoleChange">
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
        <div v-if="snapSource === 'loading'" class="boot-banner boot-banner-info">正在加载 sd-default 数据……</div>
        <div v-else-if="snapSource === 'error'" class="boot-banner boot-banner-warn">
          后端 /api/snapshot 暂不可达。已切到只读骨架；启动 brain REST（端口 8800）后刷新页面即可装载真实数据。
        </div>
        <div v-else-if="snapSource === 'live'" class="boot-banner boot-banner-ok">已连接 brain · sd-default 单租户单省（山东）</div>
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
.user-menu {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.user-menu-button {
  font-size: 14px;
  font-weight: 600;
}
.user-menu-item {
  background: none;
  border: 1px solid var(--b-border, #d4e2f4);
  border-radius: 6px;
  padding: 4px 10px;
  cursor: pointer;
  font-size: 13px;
}
.user-menu-item:hover {
  background: var(--b-bg-subtle, #e8f2fc);
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
</style>
