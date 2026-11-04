import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    include: ["test/**/*.test.{js,jsx}"],
    setupFiles: ["./test/setup.js"],
    env: { VITE_API_URL: "http://api.test" },
    restoreMocks: true,
    unstubGlobals: true,
  },
});
