import { defineConfig } from 'vite';

export default defineConfig({
  root: '.',
  build: {
    chunkSizeWarningLimit: 900,
  },
  server: {
    host: '127.0.0.1',
    port: 5174,
  },
  test: {
    environment: 'node',
  },
});
