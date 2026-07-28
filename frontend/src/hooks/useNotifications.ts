/**
 * useNotifications Hook
 * Provides notification dispatch helpers integrated with Zustand + React Hot Toast.
 * AI Codebase Assistant v2.0
 */

import { useCallback } from 'react';
import toast from 'react-hot-toast';
import { useNotificationStore } from '../stores/notificationStore';
import type { NotificationType, NotificationPriority } from '../types/notification.types';

interface NotifyOptions {
  title: string;
  message: string;
  type: NotificationType;
  priority?: NotificationPriority;
  showToast?: boolean;
  projectId?: string;
  projectName?: string;
  agentType?: string;
  taskId?: string;
  actionLabel?: string;
  actionUrl?: string;
  metadata?: Record<string, unknown>;
}

function getToastEmoji(type: NotificationType): string {
  const map: Record<NotificationType, string> = {
    success: 'âœ…',
    error: 'âŒ',
    warning: 'âš ï¸',
    info: 'â„¹ï¸',
    agent_complete: 'ðŸ¤–',
    upload_complete: 'ðŸ“',
    indexing_complete: 'ðŸ”',
    chat_response: 'ðŸ’¬',
  };
  return map[type] ?? 'â„¹ï¸';
}

export function useNotifications() {
  const addNotification = useNotificationStore((s) => s.addNotification);
  const markAsRead = useNotificationStore((s) => s.markAsRead);
  const markAllAsRead = useNotificationStore((s) => s.markAllAsRead);
  const removeNotification = useNotificationStore((s) => s.removeNotification);
  const clearAll = useNotificationStore((s) => s.clearAll);
  const togglePanel = useNotificationStore((s) => s.togglePanel);
  const closePanel = useNotificationStore((s) => s.closePanel);
  const unreadCount = useNotificationStore((s) => s.unreadCount);
  const notifications = useNotificationStore((s) => s.notifications);
  const isPanelOpen = useNotificationStore((s) => s.isPanelOpen);

  const notify = useCallback(
    (options: NotifyOptions) => {
      const { title, message, type, priority, showToast = true, ...rest } = options;

      addNotification({ title, message, type, priority: priority ?? "low", ...rest });

      if (process.env.NODE_ENV === 'development') {
        console.log('[useNotifications] notify:', { title, type });
      }

      if (showToast) {
        const toastMessage = `${getToastEmoji(type)} ${title}`;
        switch (type) {
          case 'success':
          case 'agent_complete':
          case 'upload_complete':
          case 'indexing_complete':
            toast.success(toastMessage, { duration: 4000 });
            break;
          case 'error':
            toast.error(toastMessage, { duration: 6000 });
            break;
          case 'warning':
            toast(toastMessage, {
              duration: 5000,
              icon: 'âš ï¸',
              style: { background: '#f59e0b', color: '#000' },
            });
            break;
          default:
            toast(toastMessage, { duration: 3000 });
        }
      }
    },
    [addNotification]
  );

  const notifySuccess = useCallback(
    (title: string, message: string, opts?: Partial<NotifyOptions>) =>
      notify({ title, message, type: 'success', ...opts }),
    [notify]
  );

  const notifyError = useCallback(
    (title: string, message: string, opts?: Partial<NotifyOptions>) =>
      notify({ title, message, type: 'error', priority: 'high', ...opts }),
    [notify]
  );

  const notifyWarning = useCallback(
    (title: string, message: string, opts?: Partial<NotifyOptions>) =>
      notify({ title, message, type: 'warning', priority: 'medium', ...opts }),
    [notify]
  );

  const notifyInfo = useCallback(
    (title: string, message: string, opts?: Partial<NotifyOptions>) =>
      notify({ title, message, type: 'info', ...opts }),
    [notify]
  );

  const notifyAgentComplete = useCallback(
    (agentType: string, projectName: string, opts?: Partial<NotifyOptions>) =>
      notify({
        title: 'Agent Task Complete',
        message: `${agentType} finished analyzing ${projectName}`,
        type: 'agent_complete',
        agentType,
        projectName,
        ...opts,
      }),
    [notify]
  );

  const notifyUploadComplete = useCallback(
    (fileName: string, projectName: string, opts?: Partial<NotifyOptions>) =>
      notify({
        title: 'Upload Complete',
        message: `${fileName} uploaded to ${projectName}`,
        type: 'upload_complete',
        projectName,
        ...opts,
      }),
    [notify]
  );

  return {
    notifications,
    unreadCount,
    isPanelOpen,
    notify,
    notifySuccess,
    notifyError,
    notifyWarning,
    notifyInfo,
    notifyAgentComplete,
    notifyUploadComplete,
    markAsRead,
    markAllAsRead,
    removeNotification,
    clearAll,
    togglePanel,
    closePanel,
  };
}
