// Antes de compilar la librería: vacía dist/ para que no queden .d.ts de componentes borrados.
import { rmSync } from 'node:fs';

rmSync(new URL('../dist', import.meta.url), { recursive: true, force: true });
