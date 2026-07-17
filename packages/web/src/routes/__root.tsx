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
    ],
    links: [{ rel: "stylesheet", href: appCss }],
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
