import { useCallback, useState } from 'react';
import { guardarLocal, leerLocal } from './util';

// La clave no incluye el evento: el id de atleta es nombre + club, así que quien
// sigues vale en cualquier evento en el que aparezca.
export const CLAVE_SEGUIDOS = 'sbjj:seguidos';

/** Los atletas que sigue este navegador (se guardan aquí, no en el servidor). */
export function usarSeguidos(): { seguidos: ReadonlySet<string>; alternar: (id: string) => void } {
  const [seguidos, setSeguidos] = useState<ReadonlySet<string>>(
    () => new Set(leerLocal<string[]>(CLAVE_SEGUIDOS, [])));

  const alternar = useCallback((id: string) => {
    setSeguidos((actual) => {
      const nuevo = new Set(actual);
      if (nuevo.has(id)) nuevo.delete(id); else nuevo.add(id);
      guardarLocal(CLAVE_SEGUIDOS, [...nuevo]);
      return nuevo;
    });
  }, []);

  return { seguidos, alternar };
}
