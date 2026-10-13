import type { AnchorHTMLAttributes } from 'react';
import { clases } from '../clases';

export interface EnlaceInternoProps extends AnchorHTMLAttributes<HTMLAnchorElement> {
  /** Destino dentro de la web (`#/` es el inicio, `#/evento/33588` un evento). */
  href?: string;
  /** Texto emergente. */
  title?: string;
}

/** Enlace con forma de píldora que lleva a otra pantalla de la propia web («‹ Volver a los eventos»). Para salir de la web, `EnlaceExterno`. */
export function EnlaceInterno({ className, ...resto }: EnlaceInternoProps) {
  return <a {...resto} className={clases('fc-enlace-llave', className)} />;
}
