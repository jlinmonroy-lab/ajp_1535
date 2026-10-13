import type { HTMLAttributes } from 'react';
import { clases } from '../clases';

export interface AvisoProps extends HTMLAttributes<HTMLDivElement> {
  /** `ok` (borde verde) confirma algo; `error` (rojo) dice que no se pudo. */
  tono?: 'ok' | 'error';
}

/** Mensaje breve bajo la barra de pestañas: confirma una acción o explica por qué falló. Quien lo pinta decide cuándo quitarlo. */
export function Aviso({ tono = 'ok', className, ...resto }: AvisoProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      {...resto}
      className={clases('fc-aviso', tono === 'error' && 'fc-aviso--error', className)}
    />
  );
}
