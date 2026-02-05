import { defineConfig } from 'vite';

export default defineConfig({
  // .wgsl files are imported as raw strings via the ?raw suffix.
  // Vite handles this natively — no plugin needed.
  server: {
    port: 5173,
  },
});
