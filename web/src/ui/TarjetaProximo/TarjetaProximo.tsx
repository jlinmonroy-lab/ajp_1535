import { Etiqueta } from '../Etiqueta/Etiqueta';
import type { ResultadoCombate } from '../FilaCombate/FilaCombate';
import { CabeceraTarjeta, Tarjeta } from '../Tarjeta/Tarjeta';

export interface TarjetaProximoProps {
  /** Hora estimada ya formateada («17:30»). */
  hora: string;
  /** El atleta al que sigues. */
  nombre: string;
  /** Su rival, o «Por determinar». */
  rival: string;
  /** Día corto («sáb 17»). */
  dia?: string;
  /** Gi o No-Gi, cuando el seguimiento junta dos eventos. */
  evento?: string;
  /** Tatami donde le toca. */
  tatami?: string;
  /** «EN CURSO» o «Pendiente». */
  resultado?: ResultadoCombate;
}

/**
 * Qué toca ahora o a continuación para un atleta seguido: hora, quién, contra quién, día,
 * evento y tatami. La segunda línea envuelve en varias para no cortar el tatami.
 */
export function TarjetaProximo({ hora, nombre, rival, dia, evento, tatami, resultado }: TarjetaProximoProps) {
  return (
    <Tarjeta>
      <CabeceraTarjeta
        detalleEnVarias
        izquierda={<span className="fc-hora">{hora}</span>}
        titulo={nombre}
        detalle={
          <>
            vs {rival} · {dia ? `${dia} ` : ''}
            {evento && <Etiqueta tono="evento">{evento}</Etiqueta>}
            {' '}
            {tatami}
          </>
        }
        derecha={resultado && <Etiqueta tono={resultado.tono}>{resultado.texto}</Etiqueta>}
      />
    </Tarjeta>
  );
}
