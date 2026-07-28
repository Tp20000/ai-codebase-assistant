/**
 * NotificationCenter Component
 * Full notification history panel with read/unread states and date grouping.
 * AI Codebase Assistant v2.0
 */

import React, { useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { formatDistanceToNow } from 'date-fns';
import {
  X, CheckCheck, Trash2, Bell, BellOff,
  CheckCircle, XCircle, AlertTriangle, Info,
  Bot, Upload, Search, MessageSquare,
} from 'lucide-react';
import { useNotificationStore, selectGroupedNotifications } from '../../stores/notificationStore';
import type { Notification, NotificationType } from '../../types/notification.types';

interface TypeStyle {
  icon: React.ReactNode;
  bg: string;
  text: string;
}

function getTypeStyle(type: NotificationType): TypeStyle {
  const size = 16;
  switch (type) {
    case 'success':
      return { icon: <CheckCircle size={size} />, bg: 'bg-green-500/20', text: 'text-green-400' };
    case 'error':
      return { icon: <XCircle size={size} />, bg: 'bg-red-500/20', text: 'text-red-400' };
    case 'warning':
      return { icon: <AlertTriangle size={size} />, bg: 'bg-yellow-500/20', text: 'text-yellow-400' };
    case 'agent_complete':
      return { icon: <Bot size={size} />, bg: 'bg-purple-500/20', text: 'text-purple-400' };
    case 'upload_complete':
      return { icon: <Upload size={size} />, bg: 'bg-blue-500/20', text: 'text-blue-400' };
    case 'indexing_complete':
      return { icon: <Search size={size} />, bg: 'bg-cyan-500/20', text: 'text-cyan-400' };
    case 'chat_response':
      return { icon: <MessageSquare size={size} />, bg: 'bg-indigo-500/20', text: 'text-indigo-400' };
    case 'info':
    default:
      return { icon: <Info size={size} />, bg: 'bg-gray-500/20', text: 'text-gray-400' };
  }
}

interface NotificationItemProps {
  notification: Notification;
  onRead: (id: string) => void;
  onRemove: (id: string) => void;
}

const NotificationItem: React.FC<NotificationItemProps> = ({ notification, onRead, onRemove }) => {
  const style = getTypeStyle(notification.type);

  const timeAgo = React.useMemo(() => {
    try {
      return formatDistanceToNow(new Date(notification.createdAt), { addSuffix: true });
    } catch {
      return 'just now';
    }
  }, [notification.createdAt]);

  const handleClick = () => {
    if (!notification.read) onRead(notification.id);
    if (notification.actionUrl) window.open(notification.actionUrl, '_blank', 'noopener');
  };

  return (
    <motion.div
      layout
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -20, height: 0 }}
      transition={{ duration: 0.2 }}
      className={[
        'group relative flex gap-3 p-3 rounded-lg border cursor-pointer',
        'transition-all duration-150 hover:bg-white/5',
        notification.read ? 'border-white/5 opacity-60' : `border-white/10 ${style.bg}`,
      ].join(' ')}
      onClick={handleClick}
      role="listitem"
    >
      {!notification.read && (
        <span className="absolute top-3 right-8 w-2 h-2 rounded-full bg-blue-500" />
      )}

      <div className={['flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center', style.bg, style.text].join(' ')}>
        {style.icon}
      </div>

      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-white truncate">{notification.title}</p>
        <p className="text-xs text-gray-400 mt-0.5 line-clamp-2">{notification.message}</p>
        {notification.projectName && (
          <span className="inline-flex items-center gap-1 mt-1 px-1.5 py-0.5 rounded text-[10px] bg-white/10 text-gray-300">
            📁 {notification.projectName}
          </span>
        )}
        <p className="text-[10px] text-gray-500 mt-1">{timeAgo}</p>
        {notification.actionLabel && (
          <button className="text-xs text-blue-400 hover:text-blue-300 mt-1 transition-colors">
            {notification.actionLabel} →
          </button>
        )}
      </div>

      <button
        onClick={(e) => { e.stopPropagation(); onRemove(notification.id); }}
        className="flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded hover:bg-white/10 text-gray-500 hover:text-red-400"
        aria-label="Remove notification"
      >
        <X size={12} />
      </button>
    </motion.div>
  );
};

export const NotificationCenter: React.FC = () => {
  const isPanelOpen = useNotificationStore((s) => s.isPanelOpen);
  const closePanel = useNotificationStore((s) => s.closePanel);
  const markAsRead = useNotificationStore((s) => s.markAsRead);
  const markAllAsRead = useNotificationStore((s) => s.markAllAsRead);
  const removeNotification = useNotificationStore((s) => s.removeNotification);
  const clearAll = useNotificationStore((s) => s.clearAll);
  const unreadCount = useNotificationStore((s) => s.unreadCount);
  const notifications = useNotificationStore((s) => s.notifications);
  const groupedNotifications = useNotificationStore(selectGroupedNotifications);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isPanelOpen) return;
    const handleClick = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) closePanel();
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [isPanelOpen, closePanel]);

  useEffect(() => {
    if (!isPanelOpen) return;
    const handleKey = (e: KeyboardEvent) => { if (e.key === 'Escape') closePanel(); };
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [isPanelOpen, closePanel]);

  const dateGroups = Object.entries(groupedNotifications);

  if (process.env.NODE_ENV === 'development' && isPanelOpen) {
    console.log('[NotificationCenter] Panel open — notifications:', notifications.length);
  }

  return (
    <AnimatePresence>
      {isPanelOpen && (
        <>
          <motion.div
            key="backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-40 bg-black/20 backdrop-blur-[2px]"
            onClick={closePanel}
          />

          <motion.div
            key="panel"
            ref={panelRef}
            initial={{ opacity: 0, y: -10, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -10, scale: 0.97 }}
            transition={{ duration: 0.18, ease: 'easeOut' }}
            className="fixed top-14 right-4 z-50 w-96 max-h-[600px] flex flex-col bg-gray-900 border border-white/10 rounded-xl shadow-2xl shadow-black/50 overflow-hidden"
            role="dialog"
            aria-label="Notification Center"
          >
            <div className="flex items-center justify-between px-4 py-3 border-b border-white/10 flex-shrink-0">
              <div className="flex items-center gap-2">
                <Bell size={16} className="text-blue-400" />
                <h2 className="text-sm font-semibold text-white">Notifications</h2>
                {unreadCount > 0 && (
                  <span className="px-1.5 py-0.5 text-[10px] font-bold bg-blue-500 text-white rounded-full">
                    {unreadCount}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-1">
                {unreadCount > 0 && (
                  <button
                    onClick={markAllAsRead}
                    className="flex items-center gap-1 px-2 py-1 rounded text-xs text-gray-400 hover:text-white hover:bg-white/10 transition-colors"
                    title="Mark all as read"
                  >
                    <CheckCheck size={12} /> All read
                  </button>
                )}
                {notifications.length > 0 && (
                  <button
                    onClick={clearAll}
                    className="flex items-center gap-1 px-2 py-1 rounded text-xs text-gray-400 hover:text-red-400 hover:bg-white/10 transition-colors"
                    title="Clear all"
                  >
                    <Trash2 size={12} /> Clear
                  </button>
                )}
                <button
                  onClick={closePanel}
                  className="p-1 rounded hover:bg-white/10 text-gray-400 hover:text-white transition-colors"
                  aria-label="Close"
                >
                  <X size={14} />
                </button>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto">
              {notifications.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-48 gap-3 text-center px-6">
                  <div className="w-12 h-12 rounded-full bg-white/5 flex items-center justify-center">
                    <BellOff size={20} className="text-gray-500" />
                  </div>
                  <p className="text-sm font-medium text-gray-400">No notifications yet</p>
                  <p className="text-xs text-gray-600">
                    You will be notified when agents complete, uploads finish, or errors occur.
                  </p>
                </div>
              ) : (
                <div className="p-3 space-y-4" role="list">
                  {dateGroups.map(([date, items]) => (
                    <div key={date}>
                      <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider mb-2 px-1">
                        {date}
                      </p>
                      <div className="space-y-1.5">
                        <AnimatePresence initial={false}>
                          {items.map((notification) => (
                            <NotificationItem
                              key={notification.id}
                              notification={notification}
                              onRead={markAsRead}
                              onRemove={removeNotification}
                            />
                          ))}
                        </AnimatePresence>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {notifications.length > 0 && (
              <div className="px-4 py-2 border-t border-white/10 flex-shrink-0">
                <p className="text-[10px] text-gray-500 text-center">
                  {notifications.length} notification{notifications.length !== 1 ? 's' : ''} • Stored locally
                </p>
              </div>
            )}
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
};
