import { ref, computed, type Ref, type ComputedRef } from 'vue';

// 会话「当前机构」单一事实源（仿 useProductRole 的轻量 ref 单源）。
//
// 背景：#298 已让后端按可信会话 caller_org_code 写 owner（功能正确），但前端两个供数向导
// （P5InlineCatalogWizard / P5ApiServiceWizard）的「提供方 / 所属部门」只读回显仍硬编码
// 「省大数据局」——非省大数据局部门用户看到的提供方显示是错的（仅显示骗人）。前端原先不跟踪
// current_org_code。此处把 /auth/iaf/session 响应里的 current_org_code + current_org_name
// 缓存为模块级 ref，供向导只读回显消费；取不到诚实留空，不把机构码当展示名。

const _currentOrgCode: Ref<string> = ref('');
const _currentOrgName: Ref<string> = ref('');

export function getCurrentOrgCode(): Ref<string> {
  return _currentOrgCode;
}

export function getCurrentOrgName(): Ref<string> {
  return _currentOrgName;
}

/** 机构展示名只取 current_org_name；缺名诚实留空，机构码保留给机器字段。 */
export function getCurrentOrgDisplay(): ComputedRef<string> {
  return computed(() => _currentOrgName.value || '');
}

/** 登录 / 会话刷新后由 useAuth 调用，把会话当前机构同步进单源。 */
export function setCurrentOrg(orgCode: string, orgName: string): void {
  _currentOrgCode.value = String(orgCode || '');
  _currentOrgName.value = String(orgName || '');
}
