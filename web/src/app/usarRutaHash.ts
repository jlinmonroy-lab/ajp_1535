import { useSyncExternalStore } from 'react';

/** Los ids de evento de una ruta `#/evento/33588` (o `#/evento/1535,1526`), o null si es el inicio. */
export function idsDeHash(hash: string): string | null {
  return hash.match(/^#\/evento\/([\d,]+)$/)?.[1] ?? null;
}

function suscribir(avisar: () => void): () => void {
  window.addEventListener('hashchange', avisar);
  return () => window.removeEventListener('hashchange', avisar);
}

/** Dos pantallas según la URL: `#/` (buscador de eventos) y `#/evento/ID` (tablero). Devuelve los ids o null. */
export function usarRutaHash(): string | null {
  return idsDeHash(useSyncExternalStore(suscribir, () => location.hash));
}
