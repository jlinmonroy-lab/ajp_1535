import type { HTMLAttributes } from 'react';
import { clases } from '../clases';

export type TipoMedalla = 'oro' | 'plata' | 'bronce';

const EMOJI: Record<TipoMedalla, string> = { oro: '🥇', plata: '🥈', bronce: '🥉' };
const NOMBRE: Record<TipoMedalla, string> = { oro: 'Oro', plata: 'Plata', bronce: 'Bronce' };

export interface MedallaProps extends HTMLAttributes<HTMLSpanElement> {
  /** Qué medalla es. */
  tipo: TipoMedalla;
}

/** Medalla de oro, plata o bronce, en línea junto al nombre de un atleta. */
export function Medalla({ tipo, className, ...resto }: MedallaProps) {
  return (
    <span
      role="img"
      aria-label={NOMBRE[tipo]}
      {...resto}
      className={clases('fc-medalla', className)}
      data-m={tipo}
    >
      {EMOJI[tipo]}
    </span>
  );
}
