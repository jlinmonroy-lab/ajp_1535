import { EnlaceExterno } from '../EnlaceExterno/EnlaceExterno';
import { FilaCombate, type FilaCombateProps } from '../FilaCombate/FilaCombate';
import { CabeceraTarjeta, Tarjeta } from '../Tarjeta/Tarjeta';
import { TextoTenue } from '../TextoTenue/TextoTenue';

export interface TarjetaTatamiProps {
  /** Nombre del tatami («Mat 3»). */
  nombre: string;
  /** Resumen bajo el nombre («12 combates · 1 en curso»). */
  resumen: string;
  /** Lo que está en curso y lo que viene, en orden; unos pocos. */
  combates: FilaCombateProps[];
  /** Retransmisión del tatami (`https://…`). */
  transmision?: string;
}

/** Qué pasa en un tatami: su nombre, el resumen, los combates en curso y siguientes, y un enlace a la retransmisión si hay. */
export function TarjetaTatami({ nombre, resumen, combates, transmision }: TarjetaTatamiProps) {
  return (
    <Tarjeta>
      <CabeceraTarjeta titulo={nombre} detalle={resumen} />
      {combates.length
        ? combates.map((c, i) => <FilaCombate key={c.id ?? i} diaComo="texto" {...c} />)
        : <TextoTenue>Sin combates pendientes.</TextoTenue>}
      {transmision && <EnlaceExterno href={transmision} variante="transmision">Ver retransmisión ↗</EnlaceExterno>}
    </Tarjeta>
  );
}
