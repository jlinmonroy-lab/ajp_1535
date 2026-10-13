import type { HTMLAttributes } from 'react';
import { clases } from '../clases';

export interface LineaEstadoProps extends HTMLAttributes<HTMLParagraphElement> {
  /** Rojo y en negrita: los datos están viejos o no se pueden leer. */
  vieja?: boolean;
}

/** Línea pequeña bajo el título con la frescura de los datos («Actualizado hace 12s · 340 combates»). Se anuncia a lectores de pantalla. */
export function LineaEstado({ vieja = false, className, ...resto }: LineaEstadoProps) {
  return (
    <p
      role="status"
      aria-live="polite"
      {...resto}
      className={clases('fc-estado', vieja && 'fc-estado--vieja', className)}
    />
  );
}
