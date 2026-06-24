import { useAgentChat, type AgentChatMessage } from './useAgentChat';

export const PLATFORM_GUIDE_AGENT_ID = 'a-platform-copilot';

/** 兼容旧引用：平台指南对话消息类型 = 通用 Agent 对话消息。 */
export type GuideChatMessage = AgentChatMessage;

/**
 * 平台前台统一助手。保留旧函数名是为了避免前端调用面发散；后端 Agent 已从
 * 文档问答专用的 a-zw-platform-guide 升级为只读编排型 a-platform-copilot。
 */
export function usePlatformGuideChat() {
  return useAgentChat(PLATFORM_GUIDE_AGENT_ID, { requestPrefix: 'UI-COPILOT', logPrefix: 'PlatformCopilot' });
}
