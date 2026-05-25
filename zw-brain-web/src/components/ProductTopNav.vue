<script setup lang="ts">
import { computed } from 'vue';
import { RouterLink, useRoute } from 'vue-router';
import { activeShellKey, visibleShellNav } from '@/config/productShellNav';

const props = defineProps<{
  role: string;
}>();

const route = useRoute();
const items = computed(() => visibleShellNav(props.role));
const active = computed(() => activeShellKey(route.path));
</script>

<template>
  <nav v-if="items.length" class="top-nav" aria-label="主导航">
    <div class="top-nav-inner">
      <RouterLink
        v-for="item in items"
        :key="item.key"
        :to="item.to"
        class="top-nav-item"
        :class="{ 'is-active': item.key === active }"
        :aria-current="item.key === active ? 'page' : undefined"
      >
        {{ item.navLabel }}
      </RouterLink>
    </div>
  </nav>
</template>
