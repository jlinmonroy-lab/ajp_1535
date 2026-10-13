import { clases } from '../clases';
import { Etiqueta, type TonoEtiqueta } from '../Etiqueta/Etiqueta';

export interface TarjetaEventoProps {
  /** A dónde lleva la tarjeta (en la web, `#/evento/33588`). */
  href: string;
  titulo: string;
  /** Segunda línea: fechas y lugar. */
  detalle: string;
  /** Pastilla a la derecha («Finalizado», «Hoy», «Abrir»). */
  etiqueta?: { texto: string; tono?: TonoEtiqueta };
  /** `abrirId` perfila la tarjeta con el color del equipo: es el atajo «abrir este número directamente». */
  variante?: 'normal' | 'abrirId';
}

/** Tarjeta-enlace de un evento de Smoothcomp: título, fechas y lugar, y una pastilla de estado. Toda ella es el enlace. */
export function TarjetaEvento({ href, titulo, detalle, etiqueta, variante = 'normal' }: TarjetaEventoProps) {
  return (
    <a
      className={clases('fc-tarjeta', 'fc-tarjeta--evento', variante === 'abrirId' && 'fc-tarjeta--acento')}
      href={href}
    >
      <span className="fc-crece">
        <span className="fc-nombre">{titulo}</span>
        <span className="fc-sub">{detalle}</span>
      </span>
      {etiqueta && <Etiqueta tono={etiqueta.tono}>{etiqueta.texto}</Etiqueta>}
    </a>
  );
}
