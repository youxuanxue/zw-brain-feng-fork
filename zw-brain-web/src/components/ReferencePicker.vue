<script setup lang="ts">
/** 全局机构/区划选择器：解决 18750 机构 / 16731 区划无法靠扁平下拉选取的硬伤。
 *
 *  - mode=region：行政区划逐级下钻（省→市→县→乡→村），面包屑回退、可选中间级。每级小列表，不一次吐全树。
 *  - mode=organ ：机构关键词搜索 + 分页（DB 层 LIKE + total），可选按已选区划缩小范围。
 *
 *  设计为通用组件，供表单填报及任何需选机构/区划的页面复用。选中只 emit code，
 *  联动带出（organ→区划派生）由调用方的 request.field.update 服务端完成，本组件不掺业务。
 */
import { computed, nextTick, ref, watch } from 'vue';
import { type OrganPage, type RefOption, fetchOrganOptions, fetchRegionOptions } from '@/lib/formFields';

const REGION_ROOT = '000000000000';

const props = withDefaults(
  defineProps<{
    mode: 'region' | 'organ';
    modelValue: string;
    displayName?: string;
    regionCode?: string;
    rootCode?: string;
    disabled?: boolean;
    placeholder?: string;
    testid?: string;
  }>(),
  { displayName: '', regionCode: '', rootCode: REGION_ROOT, disabled: false, placeholder: '', testid: 'reference-picker' },
);

const emit = defineEmits<{
  (e: 'update:modelValue', code: string): void;
  (e: 'picked', opt: RefOption): void;
  (e: 'cleared'): void;
}>();

const open = ref(false);
const loading = ref(false);

// ── 区划下钻状态 ──
const stack = ref<RefOption[]>([]); // 面包屑栈（不含根之上）；末项=当前所在层
const levelItems = ref<RefOption[]>([]);

// ── 机构搜索状态 ──
const keyword = ref('');
const results = ref<RefOption[]>([]);
const page = ref<Pick<OrganPage, 'total' | 'offset' | 'limit'>>({ total: 0, offset: 0, limit: 20 });
let kwTimer: ReturnType<typeof setTimeout> | undefined;

// R12：不把机构/区划裸码（12-18 位）显给用户——有名显名，已选无名显「已选择」，未选显默认提示。
const placeholderLabel = computed(() => props.placeholder || (props.mode === 'organ' ? '请选择机构' : '请选择区划'));
const triggerLabel = computed(() => props.displayName || (props.modelValue ? '已选择' : placeholderLabel.value));
const pageCount = computed(() => Math.max(1, Math.ceil(page.value.total / page.value.limit)));
const pageNo = computed(() => Math.floor(page.value.offset / page.value.limit) + 1);

async function loadRegionLevel(parentCode: string): Promise<void> {
  loading.value = true;
  try {
    levelItems.value = await fetchRegionOptions(parentCode);
  } catch {
    levelItems.value = [];
  } finally {
    loading.value = false;
  }
}

async function loadOrgans(offset = 0): Promise<void> {
  loading.value = true;
  try {
    const r = await fetchOrganOptions(props.regionCode || '', keyword.value.trim(), offset, page.value.limit);
    results.value = r.options;
    page.value = { total: r.total, offset: r.offset, limit: r.limit };
  } catch {
    results.value = [];
    page.value = { total: 0, offset: 0, limit: 20 };
  } finally {
    loading.value = false;
  }
}

const popEl = ref<HTMLElement | null>(null);

async function openPicker(): Promise<void> {
  if (props.disabled) return;
  open.value = true;
  if (props.mode === 'region') {
    stack.value = [];
    await loadRegionLevel(props.rootCode);
  } else {
    keyword.value = '';
    await loadOrgans(0);
  }
  // 聚焦弹层 → Esc 关闭可靠 + 机构模式光标落搜索框（无需再点一下）。
  await nextTick();
  (popEl.value?.querySelector('.rp-search-input') as HTMLInputElement | null)?.focus();
  popEl.value?.focus();
}

function closePicker(): void {
  open.value = false;
}

// ── 区划：下钻 / 回退 / 选中 ──
async function drill(item: RefOption): Promise<void> {
  stack.value = [...stack.value, item];
  await loadRegionLevel(item.code);
}
async function breadcrumbTo(index: number): Promise<void> {
  // index = -1 → 根；否则回到栈中该级
  stack.value = stack.value.slice(0, index + 1);
  const parent = index < 0 ? props.rootCode : stack.value[index].code;
  await loadRegionLevel(parent);
}
function pickRegion(item: RefOption): void {
  emit('update:modelValue', item.code);
  emit('picked', item);
  closePicker();
}

// ── 机构：搜索（debounce）/ 翻页 / 选中 ──
function onKeyword(): void {
  if (kwTimer) clearTimeout(kwTimer);
  kwTimer = setTimeout(() => void loadOrgans(0), 300);
}
function turnPage(delta: number): void {
  const next = page.value.offset + delta * page.value.limit;
  if (next < 0 || next >= page.value.total) return;
  void loadOrgans(next);
}
function pickOrgan(item: RefOption): void {
  emit('update:modelValue', item.code);
  emit('picked', item);
  closePicker();
}

function clearSelection(): void {
  emit('update:modelValue', '');
  emit('cleared');
  closePicker();
}

// regionCode 变（如改区划范围）→ 若机构面板开着，重搜。
watch(
  () => props.regionCode,
  () => {
    if (open.value && props.mode === 'organ') void loadOrgans(0);
  },
);
</script>

<template>
  <div class="ref-picker" :class="{ 'is-disabled': disabled }">
    <button
      type="button"
      class="rp-trigger"
      :data-testid="testid"
      :disabled="disabled"
      @click="openPicker"
    >
      <span class="rp-trigger-label" :class="{ 'is-empty': !displayName && !modelValue }">{{ triggerLabel }}</span>
      <span class="rp-caret" aria-hidden="true">▾</span>
    </button>

    <div v-if="open" ref="popEl" tabindex="-1" class="rp-pop" @keydown.esc="closePicker">
      <header class="rp-pop-head">
        <strong>{{ mode === 'organ' ? '选择机构' : '选择区划' }}</strong>
        <button type="button" class="rp-x" @click="closePicker" aria-label="关闭">×</button>
      </header>

      <!-- 区划逐级下钻 -->
      <template v-if="mode === 'region'">
        <nav class="rp-crumbs">
          <button type="button" class="rp-crumb" @click="breadcrumbTo(-1)">全国</button>
          <template v-for="(c, i) in stack" :key="c.code">
            <span class="rp-sep">›</span>
            <button type="button" class="rp-crumb" @click="breadcrumbTo(i)">{{ c.name }}</button>
          </template>
        </nav>
        <div class="rp-list" :data-testid="`${testid}-list`">
          <p v-if="loading" class="rp-hint">加载中…</p>
          <p v-else-if="!levelItems.length" class="rp-hint">无下级区划</p>
          <button
            v-for="it in levelItems"
            :key="it.code"
            type="button"
            class="rp-item"
            @click="drill(it)"
          >
            <span>{{ it.name }}</span>
            <span class="rp-pick" :title="`选「${it.name}」`" @click.stop="pickRegion(it)">选 ✓</span>
          </button>
        </div>
        <footer class="rp-foot">
          <button v-if="stack.length" type="button" class="rp-link" @click="pickRegion(stack[stack.length - 1])">
            选中当前「{{ stack[stack.length - 1].name }}」
          </button>
          <button type="button" class="rp-link rp-clear" @click="clearSelection">清空</button>
        </footer>
      </template>

      <!-- 机构搜索分页 -->
      <template v-else>
        <div class="rp-search">
          <input
            v-model="keyword"
            type="text"
            class="rp-search-input"
            :data-testid="`${testid}-search`"
            placeholder="输入机构名称或编码搜索"
            @input="onKeyword"
          />
          <span v-if="regionCode" class="rp-scope">已限定所选区划范围</span>
        </div>
        <div class="rp-list" :data-testid="`${testid}-list`">
          <p v-if="loading" class="rp-hint">搜索中…</p>
          <p v-else-if="!results.length" class="rp-hint">未找到机构，换个关键词试试</p>
          <button v-for="it in results" :key="it.code" type="button" class="rp-item" @click="pickOrgan(it)">
            <span>{{ it.name }}</span>
          </button>
        </div>
        <footer class="rp-foot">
          <span class="rp-total">共 {{ page.total }} 条</span>
          <span class="rp-pager">
            <button type="button" class="rp-link" :disabled="pageNo <= 1" @click="turnPage(-1)">‹ 上一页</button>
            {{ pageNo }}/{{ pageCount }}
            <button type="button" class="rp-link" :disabled="pageNo >= pageCount" @click="turnPage(1)">下一页 ›</button>
          </span>
          <button type="button" class="rp-link rp-clear" @click="clearSelection">清空</button>
        </footer>
      </template>
    </div>
    <div v-if="open" class="rp-backdrop" @click="closePicker" />
  </div>
</template>

<style scoped>
.ref-picker { position: relative; display: inline-block; flex: 1 1 240px; min-width: 200px; }
.rp-trigger {
  width: 100%;
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  padding: 5px 10px; border: 1px solid var(--b-border, #d4e2f4); border-radius: 6px;
  background: #fff; font-size: 13px; cursor: pointer; text-align: left;
}
.rp-trigger:disabled { background: #f4f7fb; cursor: not-allowed; }
.rp-trigger-label.is-empty { color: #9aa4b2; }
.rp-caret { color: #6b7280; font-size: 11px; }
.rp-backdrop { position: fixed; inset: 0; z-index: 40; }
.rp-pop {
  position: absolute; z-index: 41; top: calc(100% + 4px); left: 0; min-width: 320px; max-width: 420px;
  background: #fff; border: 1px solid var(--b-border, #d4e2f4); border-radius: 8px;
  box-shadow: 0 8px 28px rgba(16, 42, 76, 0.16); padding: 10px;
}
.rp-pop-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.rp-x { border: none; background: none; font-size: 18px; cursor: pointer; color: #6b7280; }
.rp-crumbs { display: flex; flex-wrap: wrap; align-items: center; gap: 2px; margin-bottom: 6px; font-size: 12px; }
.rp-crumb { border: none; background: none; color: var(--b-primary, #006be6); cursor: pointer; padding: 0 2px; }
.rp-sep { color: #9aa4b2; }
.rp-search { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.rp-search-input { flex: 1; padding: 5px 9px; border: 1px solid var(--b-border, #d4e2f4); border-radius: 6px; font-size: 13px; }
.rp-scope { font-size: 12px; color: #6b7280; white-space: nowrap; }
.rp-list { max-height: 240px; overflow-y: auto; display: flex; flex-direction: column; }
.rp-item {
  display: flex; justify-content: space-between; align-items: center; gap: 8px;
  padding: 7px 8px; border: none; border-bottom: 1px solid #f0f2f5; background: #fff;
  font-size: 13px; cursor: pointer; text-align: left; width: 100%;
}
.rp-item:hover { background: #f4f8ff; }
.rp-pick { color: var(--b-primary, #006be6); font-size: 12px; white-space: nowrap; }
.rp-hint { color: #9aa4b2; font-size: 13px; padding: 12px 4px; }
.rp-foot { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-top: 8px; font-size: 12px; flex-wrap: wrap; }
.rp-pager { display: inline-flex; align-items: center; gap: 6px; color: #6b7280; }
.rp-link { border: none; background: none; color: var(--b-primary, #006be6); cursor: pointer; font-size: 12px; }
.rp-link:disabled { color: #c0c8d2; cursor: not-allowed; }
.rp-total { color: #6b7280; }
.rp-clear { color: #6b7280; }
</style>
