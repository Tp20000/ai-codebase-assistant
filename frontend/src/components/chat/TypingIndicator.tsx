/**
 * Typing Indicator Component - Step 45
 * AI Codebase Assistant v2.0
 *
 * Three animated dots shown while AI is generating a response.
 */

import { motion } from "framer-motion";

/**
 * Animated three-dot typing indicator for AI responses.
 */
export function TypingIndicator() {
  return (
    <div className="flex items-center gap-1 px-4 py-3" aria-label="AI is typing">
      {[0, 1, 2].map((i) => (
        <motion.div
          key={i}
          className="w-2 h-2 rounded-full bg-[var(--text-muted)]"
          animate={{ y: [0, -6, 0], opacity: [0.4, 1, 0.4] }}
          transition={{
            duration: 0.9,
            repeat: Infinity,
            delay: i * 0.15,
            ease: "easeInOut",
          }}
        />
      ))}
    </div>
  );
}