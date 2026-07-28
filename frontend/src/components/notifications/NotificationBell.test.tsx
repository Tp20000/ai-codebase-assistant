import { beforeEach, describe, expect, it } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { NotificationBell } from "./NotificationBell";
import { useNotificationStore } from "../../stores/notificationStore";

describe("NotificationBell", () => {
  beforeEach(() => {
    localStorage.clear();
    useNotificationStore.setState({
      notifications: [],
      unreadCount: 0,
      isPanelOpen: false,
    });
  });

  it("renders notification button", () => {
    render(<NotificationBell />);
    expect(
      screen.getByRole("button", { name: /notifications/i })
    ).toBeInTheDocument();
  });

  it("shows unread badge when unreadCount > 0", () => {
    act(() => {
      useNotificationStore.getState().addNotification({
        title: "Upload Complete",
        message: "file.py uploaded",
        type: "success",
        priority: "low",
      });
    });

    render(<NotificationBell />);
    expect(screen.getByText("1")).toBeInTheDocument();
  });

  it("toggles the panel when clicked", () => {
    render(<NotificationBell />);

    const button = screen.getByRole("button", { name: /notifications/i });
    fireEvent.click(button);

    expect(useNotificationStore.getState().isPanelOpen).toBe(true);
  });
});