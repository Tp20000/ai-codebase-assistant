/**
 * NotificationBell Component
 * Header bell icon with animated unread badge.
 * AI Codebase Assistant v2.0
 */

import React, { useEffect, useRef, useState } from 'react';
import { Bell } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useNotificationStore } from '../../stores/notificationStore';

interface NotificationBellProps {
  className?: string;
}

export const NotificationBell: React.FC<NotificationBellProps> = ({ className = '' }) => {
  const unreadCount = useNotificationStore((s) => s.unreadCount);
  const togglePanel = useNotificationStore((s) => s.togglePanel);
  const isPanelOpen = useNotificationStore((s) => s.isPanelOpen);
  const prevCountRef = useRef(unreadCount);
  const [shouldShake, setShouldShake] = useState(false);

  useEffect(() => {
    if (unreadCount > prevCountRef.current) {
      setShouldShake(true);
      const timer = setTimeout(() => setShouldShake(false), 600);
      prevCountRef.current = unreadCount;
      return () => clearTimeout(timer);
    }
    prevCountRef.current = unreadCount;
  }, [unreadCount]);

  const displayCount = unreadCount > 99 ? '99+' : unreadCount;

  return (
    <motion.button
      onClick={togglePanel}
      className={[
        'relative p-2 rounded-lg transition-colors duration-150',
        'hover:bg-white/10 focus:outline-none focus:ring-2 focus:ring-blue-500/50',
        isPanelOpen ? 'bg-white/10 text-blue-400' : 'text-gray-400 hover:text-white',
        className,
      ].join(' ')}
      animate={shouldShake ? { rotate: [0, -15, 15, -10, 10, 0] } : {}}
      transition={{ duration: 0.5 }}
      aria-label={`Notifications${unreadCount > 0 ? ` (${unreadCount} unread)` : ''}`}
      title="Notifications"
    >
      <Bell size={20} />

      <AnimatePresence>
        {unreadCount > 0 && (
          <motion.span
            key="badge"
            initial={{ scale: 0, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0, opacity: 0 }}
            transition={{ type: 'spring', stiffness: 500, damping: 25 }}
            className={[
              'absolute -top-1 -right-1 flex items-center justify-center',
              'rounded-full text-white font-bold leading-none',
              'bg-red-500 ring-2 ring-gray-900',
              displayCount === '99+' ? 'min-w-[20px] h-5 px-1 text-[9px]' : 'w-5 h-5 text-[10px]',
            ].join(' ')}
          >
            {displayCount}
          </motion.span>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {shouldShake && unreadCount > 0 && (
          <motion.span
            key="pulse"
            initial={{ scale: 1, opacity: 0.6 }}
            animate={{ scale: 2, opacity: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.6 }}
            className="absolute inset-0 rounded-full bg-red-500 pointer-events-none"
          />
        )}
      </AnimatePresence>
    </motion.button>
  );
};
