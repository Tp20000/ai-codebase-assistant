/**
 * Frontend security utilities.
 * Prevents common XSS and validation issues.
 */

/**
 * Escape unsafe HTML characters.
 */
export function sanitizeHtml(input: string): string {
  const map: Record<string, string> = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#x27;",
    "/": "&#x2F;",
  };

  return input.replace(/[&<>"'/]/g, (char) => map[char] ?? char);
}

/**
 * Sanitize filenames for UI display.
 */
export function sanitizeFilename(filename: string): string {
  return filename
    .replace(/\.\./g, "")
    .replace(/[/\\:*?"<>|]/g, "_")
    .trim()
    .slice(0, 255);
}

/**
 * Validate UUID v4.
 */
export function isValidUUID(id: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(id);
}

/**
 * Validate email address.
 */
export function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) && email.length <= 254;
}

/**
 * Validate password strength.
 */
export function validatePassword(password: string): { valid: boolean; message: string } {
  if (password.length < 8) {
    return { valid: false, message: "Password must be at least 8 characters" };
  }
  if (!/[A-Z]/.test(password)) {
    return { valid: false, message: "Password must include an uppercase letter" };
  }
  if (!/[a-z]/.test(password)) {
    return { valid: false, message: "Password must include a lowercase letter" };
  }
  if (!/[0-9]/.test(password)) {
    return { valid: false, message: "Password must include a number" };
  }
  return { valid: true, message: "Password is strong" };
}

/**
 * Safe truncation for UI display.
 */
export function truncateForDisplay(input: string, maxLength = 100): string {
  const safe = sanitizeHtml(input);
  return safe.length <= maxLength ? safe : safe.slice(0, maxLength) + "…";
}

/**
 * Frontend click-rate limiter.
 */
const actionTimestamps = new Map<string, number>();

export function rateLimitAction(key: string, limitMs = 1000): boolean {
  const now = Date.now();
  const previous = actionTimestamps.get(key) ?? 0;
  if (now - previous < limitMs) {
    return false;
  }
  actionTimestamps.set(key, now);
  return true;
}

/**
 * Scoped localStorage helper.
 */
export const secureStorage = {
  set(key: string, value: string, expiryMs?: number): void {
    const item = {
      value,
      expiry: expiryMs ? Date.now() + expiryMs : null,
    };
    try {
      localStorage.setItem(key, JSON.stringify(item));
    } catch {
      console.warn("[secureStorage] failed to save value");
    }
  },

  get(key: string): string | null {
    try {
      const raw = localStorage.getItem(key);
      if (!raw) return null;
      const parsed = JSON.parse(raw) as { value: string; expiry: number | null };
      if (parsed.expiry && Date.now() > parsed.expiry) {
        localStorage.removeItem(key);
        return null;
      }
      return parsed.value;
    } catch {
      return null;
    }
  },

  remove(key: string): void {
    localStorage.removeItem(key);
  },

  clearAll(prefix = "aca_"): void {
    const keys = Object.keys(localStorage).filter((key) => key.startsWith(prefix));
    keys.forEach((key) => localStorage.removeItem(key));
  },
};
