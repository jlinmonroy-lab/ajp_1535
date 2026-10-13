import type { AnchorHTMLAttributes } from 'react';
import { clases } from '../clases';
import { esUrlSegura } from '../urlSegura';

export interface EnlaceExternoProps extends Omit<AnchorHTMLAttributes<HTMLAnchorElement>, 'target' | 'rel'> {
  /** Solo `https://`; con cualquier otra dirección no se pinta nada. */
  href: string;
  /** llave: píldora con contorno para saltar a un cuadro; transmision: texto con el color del equipo. */
  variante?: 'llave' | 'transmision';
}

/** Enlace que sale de la aplicación (Smoothcomp, una retransmisión): se abre en otra pestaña. */
export function EnlaceExterno({ href, variante = 'llave', className, ...resto }: EnlaceExternoProps) {
  if (!esUrlSegura(href)) return null;
  return (
    <a
      {...resto}
      className={clases(variante === 'llave' ? 'fc-enlace-llave' : 'fc-enlace-transmision', className)}
      href={href}
      target="_blank"
      rel="noopener"
    />
  );
}
