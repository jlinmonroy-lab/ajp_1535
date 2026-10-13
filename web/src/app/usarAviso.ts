import { useCallback, useEffect, useRef, useState } from 'react';

export const DURACION_AVISO_MS = 5000;

export interface AvisoActual {
  texto: string;
  error: boolean;
}

/** Un mensaje breve que se quita solo a los 5 s. Un aviso nuevo sustituye al anterior. */
export function usarAviso(): { aviso: AvisoActual | null; avisar: (texto: string, error?: boolean) => void } {
  const [aviso, setAviso] = useState<AvisoActual | null>(null);
  const temporizador = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const avisar = useCallback((texto: string, error = false) => {
    setAviso({ texto, error });
    clearTimeout(temporizador.current);
    temporizador.current = setTimeout(() => setAviso(null), DURACION_AVISO_MS);
  }, []);

  useEffect(() => () => clearTimeout(temporizador.current), []);

  return { aviso, avisar };
}
