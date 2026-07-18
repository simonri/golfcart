import {
  createRootRoute,
  HeadContent,
  Outlet,
  Scripts,
} from "@tanstack/react-router";
import "@/lib/client";

import { ReactQueryProvider } from "@/providers/react-query";

import appCss from "../styles.css?url";

export const Route = createRootRoute({
  notFoundComponent: () => <p>Page not found</p>,
  head: () => ({
    meta: [
      { charSet: "utf-8" },
      {
        name: "viewport",
        content: "width=device-width, initial-scale=1, viewport-fit=cover",
      },
      { name: "theme-color", content: "#131418" },
      { title: "Golfcart" },
      // iOS ignores the manifest for "Add to Home Screen" and reads these instead.
      { name: "mobile-web-app-capable", content: "yes" },
      { name: "apple-mobile-web-app-capable", content: "yes" },
      { name: "apple-mobile-web-app-title", content: "Golfcart" },
      {
        name: "apple-mobile-web-app-status-bar-style",
        content: "black-translucent",
      },
    ],
    links: [
      { rel: "stylesheet", href: appCss },
      { rel: "manifest", href: "/manifest.webmanifest" },
      { rel: "icon", href: "/icons/icon.svg", type: "image/svg+xml" },
      { rel: "icon", href: "/icons/favicon-32.png", sizes: "32x32" },
      { rel: "apple-touch-icon", href: "/icons/apple-touch-icon.png" },
    ],
  }),
  component: RootComponent,
});

function RootComponent() {
  return (
    <html lang="en" className="dark">
      <head>
        <HeadContent />
      </head>
      <body>
        <ReactQueryProvider>
          <Outlet />
        </ReactQueryProvider>
        <Scripts />
      </body>
    </html>
  );
}
