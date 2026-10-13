import { Etiqueta } from '../Etiqueta/Etiqueta';
import { Foto } from '../Foto/Foto';
import { CabeceraTarjeta, Tarjeta } from '../Tarjeta/Tarjeta';
import { TextoTenue } from '../TextoTenue/TextoTenue';

export interface TarjetaSinCombatesProps {
  nombre: string;
  club?: string | null;
}

/**
 * Atleta apuntado al grupo que aún no tiene combates en el schedule. Antes de que se publique
 * es lo normal, y así todos ven ya quién va.
 */
export function TarjetaSinCombates({ nombre, club }: TarjetaSinCombatesProps) {
  return (
    <Tarjeta>
      <CabeceraTarjeta
        izquierda={<Foto />}
        titulo={nombre}
        detalle={<><Etiqueta tono="grupo">grupo</Etiqueta>{' '}{club || '—'}</>}
      />
      <TextoTenue>Sin combates en el schedule todavía.</TextoTenue>
    </Tarjeta>
  );
}
