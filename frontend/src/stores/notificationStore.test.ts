import { beforeEach, describe, expect, it } from "vitest";
import { useNotificationStore } from "./notificationStore";

describe("notificationStore", () => {
  beforeEach(() => {
    localStorage.clear();
    useNotificationStore.setState({
      notifications: [],
      unreadCount: 0,
      isPanelOpen: false,
    });
  });

  it("adds a notification and increments unread count", () => {
    useNotificationStore.getState().addNotification({
      title: "Upload Complete",
      message: "file.py uploaded",
      type: "success",
      priority: "low",
    });

    const state = useNotificationStore.getState();
    expect(state.notifications).toHaveLength(1);
    expect(state.unreadCount).toBe(1);
    expect(state.notifications[0].title).toBe("Upload Complete");
  });

  it("marks all notifications as read", () => {
    const store = useNotificationStore.getState();

    store.addNotification({
      title: "Test One",
      message: "Message One",
      type: "info",
      priority: "low",
    });

    store.addNotification({
      title: "Test Two",
      message: "Message Two",
      type: "warning",
      priority: "medium",
    });

    expect(useNotificationStore.getState().unreadCount).toBe(2);

    useNotificationStore.getState().markAllAsRead();

    const state = useNotificationStore.getState();
    expect(state.unreadCount).toBe(0);
    expect(state.notifications.every((item) => item.read)).toBe(true);
  });

  it("removes a notification", () => {
    const store = useNotificationStore.getState();

    store.addNotification({
      title: "Delete Me",
      message: "To be removed",
      type: "error",
      priority: "high",
    });

    const created = useNotificationStore.getState().notifications[0];
    useNotificationStore.getState().removeNotification(created.id);

    const state = useNotificationStore.getState();
    expect(state.notifications).toHaveLength(0);
    expect(state.unreadCount).toBe(0);
  });

  it("toggles panel open and closed", () => {
    expect(useNotificationStore.getState().isPanelOpen).toBe(false);

    useNotificationStore.getState().togglePanel();
    expect(useNotificationStore.getState().isPanelOpen).toBe(true);

    useNotificationStore.getState().togglePanel();
    expect(useNotificationStore.getState().isPanelOpen).toBe(false);
  });
});