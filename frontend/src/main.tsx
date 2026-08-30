import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import "./styles/index.css";
import { router } from "./app/router";
import { createAppQueryClient } from "./app/queryClient";
import { applyTheme, readTheme } from "./app/theme";
import { applyUserTheme } from "./features/theme/applyUserTheme";
import { readUserTheme } from "./features/theme/themeStorage";

const root = document.getElementById("root");
if (!root) throw new Error("Missing application root");
const queryClient = createAppQueryClient();
applyTheme(readTheme());
// Personalization layer (colour / font / text size) — a <style> we render from
// the stored structured theme. Applied after applyTheme so there is no flash.
applyUserTheme(readUserTheme());

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);
