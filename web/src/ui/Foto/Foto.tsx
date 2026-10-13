import { clases } from '../clases';

export interface FotoProps {
  /** Dirección de la foto del atleta. Sin ella se pinta un círculo vacío del mismo tamaño. */
  src?: string | null;
  className?: string;
}

/** Foto redonda de 44 px de un atleta; vacía si no hay foto, para que las tarjetas no bailen. */
export function Foto({ src, className }: FotoProps) {
  if (!src) return <span className={clases('fc-foto', className)} />;
  return <img className={clases('fc-foto', className)} src={src} alt="" loading="lazy" />;
}
