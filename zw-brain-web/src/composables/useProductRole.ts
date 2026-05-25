import { ref, type Ref } from 'vue';

/** 顶栏「当前岗位」与路由守卫共享的单一事实来源。 */
const currentProductRole: Ref<string> = ref('ROLE_ORGAN_OPERATER');

export function getProductRole(): Ref<string> {
  return currentProductRole;
}

export function setProductRole(role: string): void {
  currentProductRole.value = role;
}
