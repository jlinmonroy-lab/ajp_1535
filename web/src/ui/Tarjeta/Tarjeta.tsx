import type { HTMLAttributes, ReactNode } from 'react';
import { clases } from '../clases';

export interface TarjetaProps extends HTMLAttributes<HTMLElement> {
  /** `acento` perfila la tarjeta con el color del equipo; `oro`, con el dorado de los avisos. */
  borde?: 'normal' | 'acento' | 'oro';
}

/** Superficie elevada que agrupa un atleta, un tatami o un evento. Es un `article`; dentro va una `CabeceraTarjeta` y, debajo, lo que haga falta. */
export function Tarjeta({ borde = 'normal', className, ...resto }: TarjetaProps) {
  return (
    <article
      {...resto}
      className={clases('fc-tarjeta', borde !== 'normal' && `fc-tarjeta--${borde}`, className)}
    />
  );
}

export interface CabeceraTarjetaProps extends Omit<HTMLAttributes<HTMLSpanElement>, 'title'> {
  /** Lo que va a la izquierda: una `Foto`, una hora… */
  izquierda?: ReactNode;
  /** Línea principal, en negrita. */
  titulo: ReactNode;
  /** Segunda línea, en gris. */
  detalle?: ReactNode;
  /** Lo que va a la derecha: un botón de seguir, una `Etiqueta`… */
  derecha?: ReactNode;
  /** Deja que el detalle ocupe varias líneas en vez de recortarlo con «…» (no cortar el tatami en «Próximos»). */
  detalleEnVarias?: boolean;
}

/**
 * Fila superior de una `Tarjeta`: elemento a la izquierda, título con detalle en el centro (que
 * se estira y se recorta) y un elemento a la derecha. Los demás atributos (`onClick`, `data-*`)
 * van al bloque central.
 */
export function CabeceraTarjeta({
  izquierda, titulo, detalle, derecha, detalleEnVarias = false, className, ...resto
}: CabeceraTarjetaProps) {
  return (
    <div className={clases('fc-tarjeta-cabecera', detalleEnVarias && 'fc-tarjeta-cabecera--varias', className)}>
      {izquierda}
      <span {...resto} className="fc-crece">
        <span className="fc-nombre">{titulo}</span>
        {detalle !== undefined && (
          <>
            <br />
            <span className="fc-sub">{detalle}</span>
          </>
        )}
      </span>
      {derecha}
    </div>
  );
}
