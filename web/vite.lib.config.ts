import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// La librería de componentes (src/ui) como paquete: dist/index.es.js + dist/style.css,
// más los .d.ts que escribe `tsc -p tsconfig.lib.json` (ver `npm run build:lib`).
// Es lo que consume /design-sync; la web (vite.config.ts) importa src/ui directamente.
export default defineConfig({
  plugins: [react()],
  // El logo, robots.txt y .nojekyll son de la web, no de la librería.
  publicDir: false,
  build: {
    outDir: 'dist',
    emptyOutDir: false,      // scripts/limpiar-lib.mjs ya lo vació, y los .d.ts llegan después
    cssCodeSplit: false,     // un solo style.css con los tokens y todos los componentes
    lib: {
      entry: 'src/ui/index.ts',
      formats: ['es'],
      fileName: () => 'index.es.js',
      cssFileName: 'style',
    },
    rolldownOptions: {
      // React lo pone quien use la librería (peerDependency).
      external: ['react', 'react-dom', 'react/jsx-runtime'],
    },
  },
});
