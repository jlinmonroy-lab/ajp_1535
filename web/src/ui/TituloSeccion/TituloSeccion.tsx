import type { HTMLAttributes } from 'react';
import { clases } from '../clases';

export interface TituloSeccionProps extends HTMLAttributes<HTMLHeadingElement> {
  /** Nivel del encabezado HTML (2 por defecto; 3 dentro de un panel que ya tiene su `h2`). */
  nivel?: 2 | 3;
}

/** Encabezado pequeño en mayúsculas que separa bloques de tarjetas («Próximo combate» o «Próximos combates», «Resultados»). */
export function TituloSeccion({ nivel = 2, className, ...resto }: TituloSeccionProps) {
  const Etiqueta = nivel === 3 ? 'h3' : 'h2';
  return <Etiqueta {...resto} className={clases('fc-titulo-seccion', className)} />;
}
