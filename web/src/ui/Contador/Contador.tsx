import type { HTMLAttributes } from 'react';
import { clases } from '../clases';

export type ContadorProps = HTMLAttributes<HTMLSpanElement>;

/** Burbuja redonda con un número (cuántos atletas sigues en la pestaña «Mis atletas»). */
export function Contador({ className, ...resto }: ContadorProps) {
  return <span {...resto} className={clases('fc-contador', className)} />;
}
