import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useNotifications } from "./useNotifications";
import { useNotificationStore } from "../stores/notificationStore";

// Correct mock for react-hot-toast
vi.mock("react-hot-toast", () => {
  const toast = Object.assign(vi.fn(), {
    success: vi.fn(),
    error: vi.fn(),
    loading: vi.fn(),
    dismiss: vi.fn(),
  });
  return { default: toast };
});

describe("useNotifications", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    useNotificationStore.setState({
      notifications: [],
      unreadCount: 0,
      isPanelOpen: false,
    });
  });

  it("notifySuccess adds a notification", () => {
    const { result } = renderHook(() => useNotifications());
    act(() => {
      result.current.notifySuccess("Upload Complete", "file.py uploaded", { showToast: false });
    });
    expect(result.current.notifications).toHaveLength(1);
    expect(result.current.unreadCount).toBe(1);
    expect(result.current.notifications[0].title).toBe("Upload Complete");
  });

  it("notifyError adds an error notification", () => {
    const { result } = renderHook(() => useNotifications());
    act(() => {
      result.current.notifyError("Upload Failed", "Network error", { showToast: false });
    });
    expect(result.current.notifications).toHaveLength(1);
    expect(result.current.notifications[0].type).toBe("error");
  });

  it("markAllAsRead clears unread count", () => {
    const { result } = renderHook(() => useNotifications());
    act(() => {
      result.current.notifySuccess("Test", "Message", { showToast: false });
    });
    expect(result.current.unreadCount).toBe(1);
    act(() => {
      result.current.markAllAsRead();
    });
    expect(result.current.unreadCount).toBe(0);
  });

  it("togglePanel updates panel state", () => {
    const { result } = renderHook(() => useNotifications());
    expect(result.current.isPanelOpen).toBe(false);
    act(() => {
      result.current.togglePanel();
    });
    expect(result.current.isPanelOpen).toBe(true);
  });

  it("removeNotification removes correct item", () => {
    const { result } = renderHook(() => useNotifications());
    act(() => {
      result.current.notifySuccess("Item 1", "First", { showToast: false });
      result.current.notifySuccess("Item 2", "Second", { showToast: false });
    });
    expect(result.current.notifications).toHaveLength(2);
    const idToRemove = result.current.notifications[0].id;
    act(() => {
      result.current.removeNotification(idToRemove);
    });
    expect(result.current.notifications).toHaveLength(1);
  });

  it("clearAll empties all notifications", () => {
    const { result } = renderHook(() => useNotifications());
    act(() => {
      result.current.notifySuccess("One", "msg", { showToast: false });
      result.current.notifySuccess("Two", "msg", { showToast: false });
    });
    act(() => {
      result.current.clearAll();
    });
    expect(result.current.notifications).toHaveLength(0);
    expect(result.current.unreadCount).toBe(0);
  });
});