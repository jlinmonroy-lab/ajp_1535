import { Boton } from '../Boton/Boton';
import { Etiqueta } from '../Etiqueta/Etiqueta';
import { FilaCombate, type FilaCombateProps } from '../FilaCombate/FilaCombate';
import { Foto } from '../Foto/Foto';
import { Llaves, type Llave } from '../Llaves/Llaves';
import { Medalla, type TipoMedalla } from '../Medalla/Medalla';
import { CabeceraTarjeta, Tarjeta } from '../Tarjeta/Tarjeta';
import { TextoTenue } from '../TextoTenue/TextoTenue';

export interface TarjetaAtletaParaTodos {
  /** El atleta ya está en la lista que ve todo el grupo. */
  activo: boolean;
  /** Hay un cambio en marcha: el botón se bloquea y dice «Guardando…». */
  guardando?: boolean;
  onAlternar: () => void;
}

export interface TarjetaAtletaProps {
  /** Identificador del atleta (nombre + club); sale como `data-atleta` y `data-seguir`. */
  id: string;
  nombre: string;
  club?: string | null;
  /** Una categoría («Men's GI / Brown / Master 1 / 62KG»). */
  categoria?: string;
  foto?: string | null;
  /** Mejor medalla conseguida hasta ahora. */
  medalla?: TipoMedalla | null;
  /** Explica por qué está en la lista alguien a quien no has seguido tú. */
  delGrupo?: boolean;
  /** Tú lo sigues: el botón dice «Siguiendo» y se rellena. */
  siguiendo: boolean;
  onSeguir: () => void;
  /** Al tocar el nombre (abre su ficha). */
  onAbrir?: () => void;
  /** Sus combates. Con la lista (aunque vacía) se pinta la sección; sin ella, solo la cabecera. */
  combates?: FilaCombateProps[];
  /** Enlaces a sus cuadros en Smoothcomp. */
  llaves?: Llave[];
  /** Solo en el panel del servidor: botón para que lo vea todo el grupo. */
  paraTodos?: TarjetaAtletaParaTodos;
}

/**
 * Ficha de un atleta: foto, nombre con su mejor medalla, club y categoría, y botón de seguir.
 * Con `combates` desglosa sus peleas hora a hora; con `llaves`, enlaza a sus cuadros.
 */
export function TarjetaAtleta({
  id, nombre, club, categoria, foto, medalla, delGrupo = false, siguiendo, onSeguir, onAbrir,
  combates, llaves, paraTodos,
}: TarjetaAtletaProps) {
  return (
    <Tarjeta>
      <CabeceraTarjeta
        izquierda={<Foto src={foto} />}
        titulo={<>{nombre}{medalla && <>{' '}<Medalla tipo={medalla} /></>}</>}
        detalle={
          <>
            {delGrupo && <><Etiqueta tono="grupo">grupo</Etiqueta>{' '}</>}
            {club || '—'} · {categoria || ''}
          </>
        }
        data-atleta={id}
        onClick={onAbrir}
        derecha={
          <Boton activo={siguiendo} data-seguir={id} onClick={onSeguir}>
            {siguiendo ? 'Siguiendo' : 'Seguir'}
          </Boton>
        }
      />
      {paraTodos && (
        <Boton
          variante="discontinuo"
          activo={paraTodos.activo}
          disabled={paraTodos.guardando}
          onClick={paraTodos.onAlternar}
        >
          {paraTodos.guardando
            ? 'Guardando…'
            : paraTodos.activo ? '✓ Lo ve todo el grupo' : 'Seguir para todos'}
        </Boton>
      )}
      {combates && (combates.length
        ? combates.map((c, i) => <FilaCombate key={c.id ?? i} {...c} />)
        : <TextoTenue>Sin combates en el schedule todavía.</TextoTenue>)}
      {llaves && <Llaves llaves={llaves} />}
    </Tarjeta>
  );
}
