/**
 * Resizable Panel Component
 * AI Codebase Assistant v2.0
 *
 * Updated: supports minimum size for BOTH panels.
 */

import {
  useRef,
  useCallback,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { clsx } from "clsx";

interface ResizablePanelProps {
  first: ReactNode;
  second: ReactNode;
  direction?: "horizontal" | "vertical";
  initialSize?: number;
  minSize?: number;
  maxSize?: number;
  secondMinSize?: number;
  className?: string;
  onResize?: (size: number) => void;
}

export function ResizablePanel({
  first,
  second,
  direction = "horizontal",
  initialSize = 240,
  minSize = 120,
  maxSize = 600,
  secondMinSize = 220,
  className,
  onResize,
}: ResizablePanelProps) {
  const [size, setSize] = useState(initialSize);
  const [isDragging, setIsDragging] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const startPosRef = useRef(0);
  const startSizeRef = useRef(initialSize);

  const isHorizontal = direction === "horizontal";

  const clampSize = useCallback(
    (rawSize: number) => {
      const container = containerRef.current;
      if (!container) {
        return Math.max(minSize, Math.min(maxSize, rawSize));
      }

      const containerSize = isHorizontal
        ? container.clientWidth
        : container.clientHeight;

      // first panel can never exceed total - secondMinSize
      const dynamicMax = Math.max(
        minSize,
        Math.min(maxSize, containerSize - secondMinSize)
      );

      return Math.max(minSize, Math.min(dynamicMax, rawSize));
    },
    [isHorizontal, minSize, maxSize, secondMinSize]
  );

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      setIsDragging(true);
      startPosRef.current = isHorizontal ? e.clientX : e.clientY;
      startSizeRef.current = size;
    },
    [size, isHorizontal]
  );

  useEffect(() => {
    if (!isDragging) return;

    const handleMouseMove = (e: MouseEvent) => {
      const delta = isHorizontal
        ? e.clientX - startPosRef.current
        : e.clientY - startPosRef.current;

      const newSize = clampSize(startSizeRef.current + delta);
      setSize(newSize);
    };

    const handleMouseUp = () => {
      setIsDragging(false);
      onResize?.(size);
    };

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);

    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [isDragging, isHorizontal, clampSize, onResize, size]);

  // Re-clamp on mount and window resize
  useEffect(() => {
    const applyClamp = () => setSize((prev) => clampSize(prev));
    applyClamp();
    window.addEventListener("resize", applyClamp);
    return () => window.removeEventListener("resize", applyClamp);
  }, [clampSize]);

  return (
    <div
      ref={containerRef}
      className={clsx(
        "h-full min-h-0 flex overflow-hidden",
        isHorizontal ? "flex-row" : "flex-col",
        isDragging && (isHorizontal ? "cursor-col-resize" : "cursor-row-resize"),
        className
      )}
    >
      {/* First panel */}
      <div
        style={
          isHorizontal
            ? { width: size, flexShrink: 0 }
            : { height: size, flexShrink: 0 }
        }
        className="h-full min-h-0 overflow-hidden"
      >
        {first}
      </div>

      {/* Drag handle */}
      <div
        onMouseDown={handleMouseDown}
        className={clsx(
          "flex-shrink-0 bg-[var(--border)] transition-colors hover:bg-blue-500/50 active:bg-blue-500",
          isHorizontal
            ? "w-px cursor-col-resize hover:w-0.5"
            : "h-px cursor-row-resize hover:h-0.5"
        )}
      />

      {/* Second panel */}
      <div
        style={
          isHorizontal
            ? { minWidth: secondMinSize }
            : { minHeight: secondMinSize }
        }
        className="flex-1 min-h-0 overflow-hidden"
      >
        {second}
      </div>
    </div>
  );
}
