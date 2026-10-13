import type { HTMLAttributes } from 'react';
import { clases } from '../clases';

export interface TextoTenueProps extends HTMLAttributes<HTMLElement> {
  /** Elemento HTML: `p` (por defecto, con sus márgenes) o `span` para ir dentro de una línea. */
  como?: 'p' | 'span';
}

/** Texto secundario, pequeño y gris: clubes, fechas, notas. */
export function TextoTenue({ como = 'p', className, ...resto }: TextoTenueProps) {
  const Elemento = como;
  return <Elemento {...resto} className={clases('fc-sub', className)} />;
}
