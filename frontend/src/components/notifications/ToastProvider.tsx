/**
 * ToastProvider Component
 * Global React Hot Toast configuration with dark-mode themed styles.
 * AI Codebase Assistant v2.0
 */

import React from 'react';
import { Toaster } from 'react-hot-toast';

export const ToastProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  return (
    <>
      {children}
      <Toaster
        position="top-right"
        gutter={8}
        containerStyle={{ top: 60, right: 16 }}
        toastOptions={{
          duration: 4000,
          style: {
            background: '#1e1e2e',
            color: '#e2e8f0',
            border: '1px solid rgba(255,255,255,0.1)',
            borderRadius: '10px',
            fontSize: '13px',
            fontFamily: 'Inter, sans-serif',
            padding: '10px 14px',
            boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
            maxWidth: '380px',
          },
          success: {
            duration: 4000,
            iconTheme: { primary: '#22c55e', secondary: '#1e1e2e' },
            style: {
              background: '#1e1e2e',
              color: '#e2e8f0',
              border: '1px solid rgba(34,197,94,0.3)',
            },
          },
          error: {
            duration: 6000,
            iconTheme: { primary: '#ef4444', secondary: '#1e1e2e' },
            style: {
              background: '#1e1e2e',
              color: '#e2e8f0',
              border: '1px solid rgba(239,68,68,0.3)',
            },
          },
          loading: {
            style: {
              background: '#1e1e2e',
              color: '#e2e8f0',
              border: '1px solid rgba(59,130,246,0.3)',
            },
          },
        }}
      />
    </>
  );
};
