import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { keys, notifications } from "@/api/resources";

export function NotificationBell() {
  const unread = useQuery({
    queryKey: keys.unreadCount,
    queryFn: notifications.unreadCount,
    refetchInterval: 30_000,
  });
  const count = unread.data?.unread ?? 0;
  const label = count ? `Notifications, ${count} unread` : "Notifications";

  return (
    <Link
      to="/notifications"
      aria-label={label}
      title={label}
      className="relative rounded-md p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-900"
    >
      <svg aria-hidden viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="h-5 w-5">
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M14.857 17.082a23.848 23.848 0 0 0 5.454-1.31A8.967 8.967 0 0 1 18 9.75V9A6 6 0 0 0 6 9v.75a8.967 8.967 0 0 1-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 0 1-5.714 0m5.714 0a3 3 0 1 1-5.714 0"
        />
      </svg>
      {count > 0 && (
        <span className="absolute -right-0.5 -top-0.5 min-w-[1.25rem] rounded-full bg-red-600 px-1 text-center text-[11px] font-semibold leading-5 text-white">
          {count > 99 ? "99+" : count}
        </span>
      )}
    </Link>
  );
}
