import { fileURLToPath } from 'node:url';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

// La web compilada va a ../site, que es lo que sirve el servidor de Python y lo que
// copia el Dockerfile. No es una carpeta de Vite: ver scripts/limpiar-sitio.mjs.
const sitio = fileURLToPath(new URL('../site', import.meta.url));

export default defineConfig({
  plugins: [react()],
  // Relativa a propósito: la web funciona igual si cuelga de una subcarpeta
  // (GitHub Pages). Por lo mismo, las URL de la API en src/app son relativas.
  base: './',
  // El commit con el que se compila (el Dockerfile lo recibe como GIT_SHA): sale en los
  // informes de error y en la pantalla de fallo. Ver src/app/version.ts.
  define: { __BUILD__: JSON.stringify(process.env.GIT_SHA || 'dev') },
  build: {
    outDir: sitio,
    // Vaciar ../site se llevaría el data.json del modo estático, que genera el scraper.
    // Lo único con nombre cambiante son los assets con hash, y los borra el `prebuild`.
    emptyOutDir: false,
  },
  server: {
    // `npm run dev` con el servidor de Python corriendo en el puerto por defecto.
    proxy: { '/api': 'http://127.0.0.1:8765' },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/pruebas/preparar.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
  },
});
