// Antes de `vite build`: borra solo los assets con hash de la compilación anterior.
// ../site no se puede vaciar entero (vite.config.ts): ahí vive también el data.json
// del modo estático, que genera el scraper y no es de la web.
import { rmSync } from 'node:fs';

rmSync(new URL('../../site/assets', import.meta.url), { recursive: true, force: true });
