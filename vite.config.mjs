import { defineConfig } from 'vite'
import { nodeResolve } from '@rollup/plugin-node-resolve'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  root: ".",
  plugins: [
    nodeResolve(),
    tailwindcss(),
  ],
  server: {
    watch: {
      ignored: ['**/_opam']
    }
  },
});
