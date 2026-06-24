import { useAgentChat, type AgentChatMessage } from './useAgentChat';

export const PLATFORM_GUIDE_AGENT_ID = 'a-zw-platform-guide';

/** 兼容旧引用：平台指南对话消息类型 = 通用 Agent 对话消息。 */
export type GuideChatMessage = AgentChatMessage;

/**
 * 平台指南副驾对话。现为通用 ``useAgentChat`` 的薄包装（单一引擎，避免重复维护
 * 「提交→轮询」逻辑）；公开 API 与返回结构保持不变。
 */
export function usePlatformGuideChat() {
  return useAgentChat(PLATFORM_GUIDE_AGENT_ID, { requestPrefix: 'UI-GUIDE', logPrefix: 'PlatformGuide' });
}
