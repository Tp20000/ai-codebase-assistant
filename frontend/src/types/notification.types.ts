/**
 * Notification system TypeScript interfaces
 * AI Codebase Assistant v2.0
 */

export type NotificationType =
  | 'success'
  | 'error'
  | 'warning'
  | 'info'
  | 'agent_complete'
  | 'upload_complete'
  | 'indexing_complete'
  | 'chat_response';

export type NotificationPriority = 'low' | 'medium' | 'high' | 'critical';

export interface Notification {
  id: string;
  type: NotificationType;
  title: string;
  message: string;
  priority: NotificationPriority;
  read: boolean;
  createdAt: string;
  metadata?: Record<string, unknown>;
  actionLabel?: string;
  actionUrl?: string;
  projectId?: string;
  projectName?: string;
  agentType?: string;
  taskId?: string;
  autoExpire?: boolean;
  expiresAt?: string;
}

export interface NotificationState {
  notifications: Notification[];
  unreadCount: number;
  isPanelOpen: boolean;
}

export interface NotificationActions {
  addNotification: (notification: Omit<Notification, 'id' | 'createdAt' | 'read'>) => void;
  markAsRead: (id: string) => void;
  markAllAsRead: () => void;
  removeNotification: (id: string) => void;
  clearAll: () => void;
  togglePanel: () => void;
  closePanel: () => void;
}

export type NotificationStore = NotificationState & NotificationActions;

export interface ApiNotification {
  id: string;
  type: NotificationType;
  title: string;
  message: string;
  priority: NotificationPriority;
  read: boolean;
  created_at: string;
  metadata: Record<string, unknown> | null;
}
