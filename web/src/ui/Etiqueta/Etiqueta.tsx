import type { HTMLAttributes } from 'react';
import { clases } from '../clases';

export type TonoEtiqueta = 'neutro' | 'vivo' | 'ganado' | 'perdido' | 'grupo' | 'evento';

export interface EtiquetaProps extends HTMLAttributes<HTMLSpanElement> {
  /** Tono: neutro (por defecto), vivo, ganado, perdido, grupo o evento. Cada uno se explica en la descripción del componente. */
  tono?: TonoEtiqueta;
}

/**
 * Etiqueta pequeña en línea para el estado de un combate, el día o el evento al que pertenece.
 * El texto debe decir lo mismo que el color: el color solo no basta.
 *
 * Tonos:
 * - `neutro`: dato sin más («Pendiente», «Finalizado», un día).
 * - `vivo`: rojo sólido; algo que está pasando ahora («EN CURSO», «Hoy»).
 * - `ganado`: verde sólido; el atleta ganó el combate.
 * - `perdido`: contorno rojo; el atleta perdió.
 * - `grupo`: contorno verde; el atleta está en la lista del grupo.
 * - `evento`: contorno con el color del equipo; distingue Gi de No-Gi en un mismo fin de semana.
 */
export function Etiqueta({ tono = 'neutro', className, ...resto }: EtiquetaProps) {
  return <span {...resto} className={clases('fc-etiqueta', `fc-etiqueta--${tono}`, className)} />;
}
