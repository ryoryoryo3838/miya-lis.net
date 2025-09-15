import { defineConfig } from 'vite'
import { nodeResolve } from '@rollup/plugin-node-resolve'
import tailwindcss from '@tailwindcss/vite'
import string from "vite-plugin-string"

export default defineConfig({
  root: ".",
  plugins: [
    nodeResolve(),
    tailwindcss(),
    string({
      include: ["**/*.html"],
    }),
  ],
  server: {
    watch: {
      ignored: ['**/_opam']
    }
  },
});
