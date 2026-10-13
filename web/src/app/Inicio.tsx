/* Pantalla de inicio: buscar un evento de Smoothcomp y abrirlo (#/evento/ID). */
import { useEffect, type ReactNode } from 'react';
import type { EventoBuscado } from '../tipos';
import {
  AccesoAdmin, Boton, CampoBusqueda, ChipZona, Filtros, TarjetaEvento, TextoTenue, TituloSeccion, Vacio,
} from '../ui';
import type { Busqueda, Cuando } from './usarBusquedaEventos';
import { hoy, idDeEvento, rangoFechas } from './util';

const TITULO_RESULTADOS: Record<Cuando, string> = {
  upcoming: 'Próximos eventos', past: 'Eventos pasados', all: 'Eventos',
};

const OPCIONES_CUANDO = [
  { id: 'upcoming', etiqueta: 'Próximos' },
  { id: 'past', etiqueta: 'Pasados' },
  { id: 'all', etiqueta: 'Todos' },
];

function chipDelEvento(e: Pick<EventoBuscado, 'startdate' | 'enddate'> & { ended?: boolean }) {
  const hoyIso = hoy();
  const fin = e.enddate || e.startdate;
  if (e.ended || (fin && fin < hoyIso)) return { texto: 'Finalizado' };
  if (e.startdate && e.startdate <= hoyIso) {
    // Las ligas y circuitos duran meses: "Hoy" solo si de verdad empieza hoy.
    return { texto: e.startdate === hoyIso ? 'Hoy' : 'En curso', tono: 'vivo' as const };
  }
  return undefined;
}

function TarjetaDeEvento({ e }: { e: EventoBuscado }) {
  const lugar = [e.city, e.country].filter(Boolean).join(', ');
  const detalle = [rangoFechas(e.startdate, e.enddate), lugar].filter(Boolean).join(' · ');
  return (
    <TarjetaEvento
      href={`#/evento/${e.id}`}
      titulo={e.title}
      detalle={detalle || 'Sin fecha'}
      etiqueta={chipDelEvento(e)}
    />
  );
}

interface InicioProps {
  busqueda: Busqueda;
  /** Hay clave de administrador en el servidor y esto no es su propio equipo: se ofrece entrar con ella. */
  mostrarAdmin: boolean;
  esPanel: boolean;
  onEntrarAdmin: (clave: string) => Promise<boolean | null>;
  onSalirAdmin: () => void;
}

export function Inicio({ busqueda, mostrarAdmin, esPanel, onEntrarAdmin, onSalirAdmin }: InicioProps) {
  const { estado: est } = busqueda;
  const { mostrar } = busqueda;

  // Cada vez que se vuelve a esta pantalla: la primera vez lanza la búsqueda.
  useEffect(() => { mostrar(); }, []);

  const id = idDeEvento(est.q);
  const lugar = est.zonaActiva ? ` en ${est.zona}` : '';
  const hayResultados = est.eventos.length > 0;

  // Con la zona encendida, lo que no sale puede estar fuera de ella: se ofrece salir.
  const salir: ReactNode = est.zonaActiva
    ? <><br /><Boton onClick={() => busqueda.cambiarZona(false)}>Buscar en todo el mundo</Boton></>
    : null;

  let cuerpo: ReactNode = null;
  if (est.error) {
    cuerpo = (
      <Vacio error>
        {est.error}<br />
        <Boton onClick={busqueda.reintentar}>Reintentar</Boton>
      </Vacio>
    );
  } else if (est.cargando && !hayResultados) {
    cuerpo = <Vacio>Buscando…</Vacio>;
  } else if (!est.cargando && !hayResultados && !id) {
    cuerpo = est.q
      ? (
        <Vacio>
          Ningún evento{lugar} coincide con «{est.q}».
          {est.cuando === 'upcoming' && <><br />Prueba también en <strong>Pasados</strong>.</>}
          {salir}
        </Vacio>
      )
      : <Vacio>No hay {est.cuando === 'upcoming' ? 'próximos ' : ''}eventos{lugar}.{salir}</Vacio>;
  }

  return (
    <section id="pantalla-inicio">
      <form
        id="form-eventos"
        role="search"
        autoComplete="off"
        onSubmit={(ev) => {
          ev.preventDefault();
          busqueda.enviar();
          (document.activeElement as HTMLElement | null)?.blur();   // en el móvil, esconde el teclado
        }}
      >
        <CampoBusqueda
          id="busqueda-eventos"
          maxLength={80}
          placeholder="Nombre, ciudad u organizador…"
          aria-label="Buscar evento en Smoothcomp"
          value={est.texto}
          onChange={(ev) => busqueda.escribir(ev.target.value)}
        />
      </form>
      <TextoTenue className="app-nota-busqueda">
        También puedes pegar el enlace o el número de un evento.
      </TextoTenue>
      <Filtros
        etiqueta="Cuándo"
        opciones={OPCIONES_CUANDO}
        valor={est.cuando}
        onCambiar={(c) => busqueda.cambiarCuando(c as Cuando)}
      />
      <div className="app-zona-fila">
        {est.zona && (
          <ChipZona nombre={est.zona} activo={est.zonaActiva} onAlternar={() => busqueda.cambiarZona(!est.zonaActiva)} />
        )}
      </div>

      <div id="resultados-eventos" aria-live="polite">
        {id && (
          <TarjetaEvento
            variante="abrirId"
            href={`#/evento/${id}`}
            titulo={`Abrir el evento n.º ${id.replace(/,/g, ', ')}`}
            detalle="Directamente, sin buscar"
            etiqueta={{ texto: 'Abrir' }}
          />
        )}
        {hayResultados && (
          <>
            <TituloSeccion>{est.q ? 'Resultados' : TITULO_RESULTADOS[est.cuando]}{lugar}</TituloSeccion>
            {est.vieja && <TextoTenue>Smoothcomp no responde ahora: se muestran resultados guardados.</TextoTenue>}
            {est.eventos.map((e) => <TarjetaDeEvento key={e.id} e={e} />)}
          </>
        )}
        {cuerpo}
      </div>

      {est.hayMas && hayResultados && !est.error && (
        <Boton variante="bloque" disabled={est.cargando} onClick={busqueda.cargarMas}>
          {est.cargando ? 'Cargando…' : 'Cargar más'}
        </Boton>
      )}

      {mostrarAdmin && (
        <AccesoAdmin sesionIniciada={esPanel} onEntrar={onEntrarAdmin} onSalir={onSalirAdmin} />
      )}
    </section>
  );
}
