/**
 * Notification Zustand Store
 * Manages all in-app notifications with persistence and badge counting.
 * AI Codebase Assistant v2.0
 */

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { v4 as uuidv4 } from 'uuid';
import type {
  Notification,
  NotificationStore,
  NotificationType,
  NotificationPriority,
} from '../types/notification.types';

const MAX_NOTIFICATIONS = 50;

function defaultPriorityForType(type: NotificationType): NotificationPriority {
  switch (type) {
    case 'error':
      return 'high';
    case 'agent_complete':
    case 'upload_complete':
    case 'indexing_complete':
      return 'medium';
    case 'warning':
      return 'medium';
    case 'success':
    case 'chat_response':
    case 'info':
    default:
      return 'low';
  }
}

export const useNotificationStore = create<NotificationStore>()(
  persist(
    (set, get) => ({
      notifications: [],
      unreadCount: 0,
      isPanelOpen: false,

      addNotification: (notification) => {
        const newNotification: Notification = {
          ...notification,
          id: uuidv4(),
          read: false,
          createdAt: new Date().toISOString(),
          priority: notification.priority ?? defaultPriorityForType(notification.type),
        };
        set((state) => {
          const updated = [newNotification, ...state.notifications].slice(0, MAX_NOTIFICATIONS);
          return {
            notifications: updated,
            unreadCount: updated.filter((n) => !n.read).length,
          };
        });
        if (process.env.NODE_ENV === 'development') {
          console.log('[NotificationStore] Added:', newNotification);
        }
      },

      markAsRead: (id) => {
        set((state) => {
          const updated = state.notifications.map((n) =>
            n.id === id ? { ...n, read: true } : n
          );
          return {
            notifications: updated,
            unreadCount: updated.filter((n) => !n.read).length,
          };
        });
      },

      markAllAsRead: () => {
        set((state) => ({
          notifications: state.notifications.map((n) => ({ ...n, read: true })),
          unreadCount: 0,
        }));
      },

      removeNotification: (id) => {
        set((state) => {
          const updated = state.notifications.filter((n) => n.id !== id);
          return {
            notifications: updated,
            unreadCount: updated.filter((n) => !n.read).length,
          };
        });
      },

      clearAll: () => {
        set({ notifications: [], unreadCount: 0 });
      },

      togglePanel: () => {
        const { isPanelOpen, markAllAsRead } = get();
        if (!isPanelOpen) {
          setTimeout(() => markAllAsRead(), 800);
        }
        set({ isPanelOpen: !isPanelOpen });
      },

      closePanel: () => {
        set({ isPanelOpen: false });
      },
    }),
    {
      name: 'ai-assistant-notifications',
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        notifications: state.notifications.slice(0, 20),
      }),
      onRehydrateStorage: () => (state) => {
        if (state) {
          state.unreadCount = state.notifications.filter((n) => !n.read).length;
          state.isPanelOpen = false;
          if (process.env.NODE_ENV === 'development') {
            console.log('[NotificationStore] Rehydrated:', state.notifications.length, 'notifications');
          }
        }
      },
    }
  )
);

export const selectUnreadNotifications = (state: NotificationStore) =>
  state.notifications.filter((n) => !n.read);

export const selectGroupedNotifications = (
  state: NotificationStore
): Record<string, Notification[]> => {
  const groups: Record<string, Notification[]> = {};
  state.notifications.forEach((n) => {
    const date = new Date(n.createdAt).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
    if (!groups[date]) groups[date] = [];
    groups[date].push(n);
  });
  return groups;
};
