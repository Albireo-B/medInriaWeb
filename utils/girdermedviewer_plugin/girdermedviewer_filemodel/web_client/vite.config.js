import { resolve } from 'path';
import { defineConfig } from 'vite';

export default defineConfig({
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    lib: {
      entry: resolve(import.meta.dirname, 'src/main.js'),
      name: 'GirderPluginMedViewer',
      formats: ['umd'],
      fileName: () => 'girdermedviewer_plugin.umd.cjs'
    },
    rollupOptions: {
      external: [
        '@girder/core'
      ],
      output: {
        globals: {
          '@girder/core':  'girder'
        }
      }
    }
  }
});