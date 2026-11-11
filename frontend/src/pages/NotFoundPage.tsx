import { Link } from "react-router-dom";

import { FullPageMessage } from "@/components/FullPageMessage";

export function NotFoundPage() {
  return (
    <FullPageMessage title="Page not found" embedded>
      <Link to="/" className="font-medium text-indigo-600 hover:text-indigo-500">
        Back to the dashboard
      </Link>
    </FullPageMessage>
  );
}
