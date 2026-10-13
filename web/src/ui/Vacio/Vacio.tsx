import type { HTMLAttributes } from 'react';
import { clases } from '../clases';

export interface VacioProps extends HTMLAttributes<HTMLParagraphElement> {
  /** Pinta el mensaje en rojo: no es «no hay nada», es «algo ha fallado». */
  error?: boolean;
}

/** Mensaje centrado para una lista sin contenido, una carga en curso o un fallo; admite un botón debajo. */
export function Vacio({ error = false, className, ...resto }: VacioProps) {
  return <p {...resto} className={clases('fc-vacio', error && 'fc-vacio--error', className)} />;
}
