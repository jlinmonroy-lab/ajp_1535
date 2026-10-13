import { Etiqueta, type TonoEtiqueta } from '../Etiqueta/Etiqueta';

export interface ResultadoCombate {
  texto: string;
  tono?: TonoEtiqueta;
}

export interface FilaCombateProps {
  /** Identificador estable del combate; solo sirve de `key` cuando se pintan varias filas. */
  id?: string;
  /** Hora estimada ya formateada («17:30»), o «--:--» si no se sabe. */
  hora: string;
  /** Rival («vs Ana Pérez») o los dos contendientes («Ana Pérez vs Luis Gómez»). */
  titulo: string;
  /** Día corto («sáb 17»). */
  dia?: string;
  /** Si el día va en una `Etiqueta` (por defecto) o como texto corrido. */
  diaComo?: 'etiqueta' | 'texto';
  /** Gi o No-Gi, cuando el seguimiento junta dos eventos. */
  evento?: string;
  /** Resto de la segunda línea: «Semifinal · Tatami 3», o la categoría. */
  detalle?: string;
  /** Estado a la derecha: «EN CURSO», «Ganó · puntos»… */
  resultado?: ResultadoCombate;
}

/** Una línea de combate: hora a la izquierda, rival y detalles en medio, resultado a la derecha. Se apila dentro de una `Tarjeta`. */
export function FilaCombate({
  hora, titulo, dia, diaComo = 'etiqueta', evento, detalle, resultado,
}: FilaCombateProps) {
  return (
    <div className="fc-combate">
      <span className="fc-hora">{hora}</span>
      <span className="fc-combate-detalle">
        <span className="fc-rival">{titulo}</span>
        <br />
        <span className="fc-sub">
          {dia && (diaComo === 'etiqueta' ? <><Etiqueta>{dia}</Etiqueta>{' '}</> : <>{dia}{' '}</>)}
          {evento && <Etiqueta tono="evento">{evento}</Etiqueta>}
          {' '}
          {detalle}
        </span>
      </span>
      {resultado && <Etiqueta tono={resultado.tono}>{resultado.texto}</Etiqueta>}
    </div>
  );
}
