import { useState } from 'react';
import { Boton } from '../Boton/Boton';
import { Etiqueta } from '../Etiqueta/Etiqueta';
import { Tarjeta } from '../Tarjeta/Tarjeta';
import { TextoTenue } from '../TextoTenue/TextoTenue';
import { TituloSeccion } from '../TituloSeccion/TituloSeccion';

export interface EntradaListaGrupo {
  id: string;
  nombre: string;
  /** Ya resuelto para enseñar: el club apuntado, el que tiene en el schedule, o «sin club». */
  club: string;
  /** Apuntado pero sin combates en el schedule todavía. */
  sinCombates: boolean;
}

export interface ListaGrupoProps {
  entradas: EntradaListaGrupo[];
  /** Pulsar «Quitar». El botón queda bloqueado hasta que termina; si se rechaza, se desbloquea. */
  onQuitar: (id: string) => Promise<void> | void;
}

/** Lista de gestión del grupo (solo en el panel): quién está apuntado, con un botón para quitarlo. */
export function ListaGrupo({ entradas, onQuitar }: ListaGrupoProps) {
  const [quitando, setQuitando] = useState<ReadonlySet<string>>(new Set());

  async function quitar(id: string) {
    setQuitando((s) => new Set(s).add(id));
    try {
      await onQuitar(id);
    } catch {
      /* quien lo pasa ya avisó del error */
    } finally {
      setQuitando((s) => { const n = new Set(s); n.delete(id); return n; });
    }
  }

  return (
    <>
      <TituloSeccion>Lista del grupo ({entradas.length})</TituloSeccion>
      <Tarjeta>
        {entradas.length ? entradas.map((e) => (
          <div className="fc-combate" key={e.id}>
            <span className="fc-combate-detalle">
              <span className="fc-nombre">{e.nombre}</span>
              <br />
              <span className="fc-sub">
                {e.club}
                {e.sinCombates && <>{' · '}<Etiqueta>sin combates todavía</Etiqueta></>}
              </span>
            </span>
            <Boton data-quitar={e.id} disabled={quitando.has(e.id)} onClick={() => quitar(e.id)}>
              Quitar
            </Boton>
          </div>
        )) : <TextoTenue>Nadie todavía.</TextoTenue>}
      </Tarjeta>
    </>
  );
}
