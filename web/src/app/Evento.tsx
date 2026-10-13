/* Tablero de un evento: «Mis atletas», «Buscar» y «Tatamis», más la ficha de cada atleta.
 *
 * Es un contenedor: pide los datos (usarSondeoEvento), guarda lo que es de este navegador
 * (a quién sigues) y traduce todo a componentes de src/ui. Se monta con `key={ids}`, así que
 * abrir otro evento empieza de cero, como al abrir la web.
 */
import { Fragment, useEffect, useMemo, useReducer, useRef, useState, type ReactNode } from 'react';
import type { Atleta, Combate, Datos, EntradaGrupo, GrupoPanel } from '../tipos';
import {
  AvisoSinSchedule, Aviso, Cabecera, CampoBusqueda, EnlaceInterno, FormAltaGrupo, LineaEstado,
  ListaGrupo, Llaves, Medalla, PanelDetalle, Pestanas, TarjetaAtleta, TarjetaProximo, TarjetaSinCombates,
  TarjetaTatami, TextoTenue, TituloSeccion, Vacio, FilaCombate,
  type EntradaListaGrupo,
} from '../ui';
import { enviarGrupo, leerGrupo, urlGrupo, type Arranque } from './api';
import {
  MEDALLA, combatesDe, filaDeAtleta, filaDeTatami, llavesDe, nombreEvento, resultadoDe, rivalDe,
  sinSchedule, textoEstado, urlDelEvento,
} from './selectores';
import { usarAviso } from './usarAviso';
import { usarSeguidos } from './usarSeguidos';
import { usarSondeoEvento } from './usarSondeoEvento';
import { LimiteError } from './LimiteError';
import { ResultadosBusqueda } from './ResultadosBusqueda';

type Vista = 'seguidos' | 'buscar' | 'tatamis';

// Lo pulsado en el panel tarda un ciclo en volver dentro de los datos. Hasta
// que vuelva se recuerda aquí; si no, el refresco de cada 30s lo desmarcaría y
// parecería que el botón no funciona.
const ESPERA_CONFIRMACION_MS = 3 * 60 * 1000;
interface Pendiente { alta: boolean; momento: number }

interface EventoProps {
  /** Ids del evento ("33588" o "1535,1526"); null en el modo estático, donde solo hay uno. */
  ids: string | null;
  arranque: Arranque;
  /** Fija el título de la pestaña del navegador. */
  alTitular: (nombre: string | null) => void;
}

export function Evento({ ids, arranque, alTitular }: EventoProps) {
  const { marca, modoEstatico, esPanel } = arranque;
  const { datos, situacion, ahora, recargar } = usarSondeoEvento({ ids, modoEstatico });
  const { seguidos, alternar: alternarSeguido } = usarSeguidos();
  const { aviso, avisar } = usarAviso();

  const [vista, setVista] = useState<Vista>('seguidos');
  const [consulta, setConsulta] = useState('');
  const [detalleId, setDetalleId] = useState<string | null>(null);
  const [grupoPanel, setGrupoPanel] = useState<GrupoPanel | null>(null);
  const [guardando, setGuardando] = useState<ReadonlySet<string>>(new Set());
  const pendientes = useRef(new Map<string, Pendiente>());
  const [, repintar] = useReducer((n: number) => n + 1, 0);
  const campoBusqueda = useRef<HTMLInputElement>(null);

  const porId = useMemo(
    () => new Map<string, Combate>((datos?.matches ?? []).map((m) => [m.id, m])), [datos]);

  /* ---------- Cabecera y título ---------- */
  const nombre = datos ? nombreEvento(datos)
    : (situacion.tipo === 'leyendo' ? situacion.titulo : null);
  useEffect(() => { alTitular(nombre); }, [nombre, alTitular]);
  useEffect(() => { window.scrollTo(0, 0); }, []);
  // Al pasar a «Buscar» el teclado debe estar listo para escribir.
  useEffect(() => { if (vista === 'buscar') campoBusqueda.current?.focus(); }, [vista]);

  /* ---------- Cada vez que llegan datos nuevos ---------- */
  useEffect(() => {
    if (!datos) return;

    // Deja de recordar lo pendiente en cuanto los datos lo confirman, y avisa si
    // pasa demasiado tiempo sin que llegue: marcar algo que nadie va a ver sería
    // peor que decir que no se ha publicado.
    for (const [id, pendiente] of [...pendientes.current]) {
      const atleta = datos.athletes.find((a) => a.id === id);
      if (atleta && !!atleta.inGroup === pendiente.alta) {
        pendientes.current.delete(id);
      } else if (Date.now() - pendiente.momento > ESPERA_CONFIRMACION_MS) {
        pendientes.current.delete(id);
        avisar(modoEstatico
          ? 'El cambio no se ha publicado. ¿Está corriendo el scraper?'
          : 'El cambio no ha llegado a los datos. Recarga la página.', true);
      }
    }
  }, [datos, modoEstatico, avisar]);

  /* ---------- Lista del grupo (solo desde el panel) ---------- */
  useEffect(() => {
    if (!esPanel) return undefined;
    let vigente = true;
    void leerGrupo(urlGrupo(modoEstatico, ids)).then((g) => { if (g && vigente) setGrupoPanel(g); });
    return () => { vigente = false; };
  }, [esPanel, modoEstatico, ids]);

  // Lo que devuelve el servidor tras cada cambio manda sobre los datos, que pueden tardar
  // un poco en enterarse.
  const grupoActual = (): EntradaGrupo[] =>
    ((esPanel && grupoPanel) ? grupoPanel.atletas : (datos?.group?.athletes ?? []));

  const enGrupo = (a: Atleta): boolean => {
    const pendiente = pendientes.current.get(a.id);
    return pendiente ? pendiente.alta : !!a.inGroup;
  };
  const esMio = (a: Atleta): boolean => enGrupo(a) || seguidos.has(a.id);

  // El atleta de los datos que corresponde a una entrada del grupo. Mismo
  // criterio que el servidor: id exacto, o solo el nombre si se apuntó sin club.
  const atletaDeEntrada = (entrada: EntradaGrupo): Atleta | undefined => {
    const id = entrada.id || '';
    const soloNombre = id.endsWith('|') ? id.slice(0, -1) : null;
    return datos?.athletes.find((a) =>
      a.id === id || (soloNombre !== null && a.id.split('|')[0] === soloNombre));
  };

  const AVISO_GRUPO_ALTA = modoEstatico
    ? 'En un par de minutos lo verá todo el grupo.'
    : 'Ya lo ve todo el grupo.';
  const mensajeFallo = (e: unknown) =>
    `No se pudo guardar (${e instanceof Error ? e.message : String(e)}). ¿Está el panel arrancado?`;

  async function altaManual({ nombre: n, club }: { nombre: string; club: string }) {
    try {
      setGrupoPanel(await enviarGrupo(urlGrupo(modoEstatico, ids), { name: n, club, accion: 'añadir' }));
      avisar(`${n} añadido. ${AVISO_GRUPO_ALTA}`);
    } catch (e) {
      avisar(mensajeFallo(e), true);
      throw e;
    }
  }

  async function quitarDelGrupo(id: string) {
    const entrada = grupoActual().find((e) => e.id === id);
    const n = entrada?.name ?? '';
    try {
      setGrupoPanel(await enviarGrupo(urlGrupo(modoEstatico, ids), { id, name: n, accion: 'quitar' }));
      // Si antes se marcó «Seguir para todos», esa marca pendiente seguiría diciendo que está
      // en el grupo hasta que caducara (y entonces avisaría de un fallo que no existe).
      const atleta = entrada && atletaDeEntrada(entrada);
      if (atleta) {
        pendientes.current.set(atleta.id, { alta: false, momento: Date.now() });
        repintar();
      }
      avisar(`${n} quitado de la lista del grupo.`);
    } catch (e) {
      avisar(mensajeFallo(e), true);
      throw e;
    }
  }

  async function marcarParaTodos(atleta: Atleta) {
    const accion = enGrupo(atleta) ? 'quitar' : 'añadir';
    setGuardando((s) => new Set(s).add(atleta.id));
    try {
      setGrupoPanel(await enviarGrupo(
        urlGrupo(modoEstatico, ids), { id: atleta.id, name: atleta.name, accion }));
      // Se recuerda hasta que los datos lo confirmen, para que el refresco
      // periódico no lo desmarque a los pocos segundos.
      pendientes.current.set(atleta.id, { alta: accion === 'añadir', momento: Date.now() });
      avisar(accion === 'añadir' ? `Añadido. ${AVISO_GRUPO_ALTA}` : 'Quitado de la lista del grupo.');
    } catch (e) {
      avisar(mensajeFallo(e), true);
    } finally {
      setGuardando((s) => { const n = new Set(s); n.delete(atleta.id); return n; });
      repintar();
    }
  }

  /* ---------- Piezas ---------- */
  const inexistente = situacion.tipo === 'inexistente';
  const avisoSinSchedule = datos && sinSchedule(datos) ? <AvisoSinSchedule /> : null;

  const tarjetaAtleta = (a: Atleta, conCombates: boolean): ReactNode => (
    <TarjetaAtleta
      key={a.id}
      id={a.id}
      nombre={a.name}
      club={a.club}
      categoria={a.categories?.[0]}
      foto={a.image}
      medalla={a.bestMedal ? MEDALLA[a.bestMedal] : null}
      delGrupo={enGrupo(a)}
      siguiendo={seguidos.has(a.id)}
      onSeguir={() => alternarSeguido(a.id)}
      onAbrir={() => setDetalleId(a.id)}
      combates={conCombates ? combatesDe(a, porId).map((c) => filaDeAtleta(c, a.id)) : undefined}
      llaves={conCombates ? llavesDe(a) : undefined}
      paraTodos={esPanel ? {
        activo: enGrupo(a),
        guardando: guardando.has(a.id),
        onAlternar: () => { void marcarParaTodos(a); },
      } : undefined}
    />
  );

  // Mientras no hay datos: qué decir en el lugar de las listas.
  const cuerpoVacio = (): ReactNode => {
    switch (situacion.tipo) {
      case 'cargando':
        return <Vacio>Cargando…</Vacio>;
      case 'leyendo':
        return (
          <Vacio>
            Leyendo el schedule de Smoothcomp…<br />
            <TextoTenue como="span">Los eventos grandes tardan un poco la primera vez.</TextoTenue>
          </Vacio>
        );
      case 'inexistente':
        return (
          <Vacio>
            {situacion.mensaje}<br />
            <EnlaceInterno href="#/">‹ Volver a los eventos</EnlaceInterno>
          </Vacio>
        );
      case 'error':
        return (
          <Vacio>
            {situacion.mensaje}<br />
            <TextoTenue como="span">Se reintenta solo.</TextoTenue>
          </Vacio>
        );
      default:
        return null;
    }
  };

  /* ---------- Vistas ---------- */
  function vistaSeguidos(d: Datos): ReactNode {
    const mios = d.athletes.filter(esMio);
    const sinCombates = grupoActual().filter((e) => !atletaDeEntrada(e));

    // En el panel la lista del grupo se gestiona aparte, con su botón de quitar.
    const gestion = esPanel ? listaGrupoPanel() : null;
    const esperando = esPanel ? [] : sinCombates.map((e) =>
      <TarjetaSinCombates key={e.id} nombre={e.name} club={e.club} />);

    if (!mios.length) {
      return (
        <>
          {gestion}
          {avisoSinSchedule}
          {esperando.length > 0
            ? <><TituloSeccion>Mis atletas</TituloSeccion>{esperando}</>
            : (avisoSinSchedule ? null : (
              <Vacio>
                Todavía no hay atletas en la lista.<br />
                Usa <strong>Buscar</strong> para añadir a quien quieras seguir.
              </Vacio>
            ))}
        </>
      );
    }

    // Lo primero que quiere ver alguien en el pabellón: qué toca ahora y qué viene.
    const proximos: Array<{ atleta: Atleta; combate: Combate }> = [];
    for (const a of mios) {
      for (const c of combatesDe(a, porId)) {
        if (c.state !== 'finished') proximos.push({ atleta: a, combate: c });
      }
    }
    proximos.sort((x, y) =>
      (x.combate.estimatedStart || '').localeCompare(y.combate.estimatedStart || ''));

    return (
      <>
        {gestion}
        {avisoSinSchedule}
        {proximos.length > 0 && (
          <>
            <TituloSeccion>Próximos combates</TituloSeccion>
            {proximos.slice(0, 8).map(({ atleta, combate }) => {
              const fila = filaDeAtleta(combate, atleta.id);
              return (
                <TarjetaProximo
                  key={`${atleta.id}|${combate.id}`}
                  hora={fila.hora}
                  nombre={atleta.name}
                  rival={rivalDe(combate, atleta.id)?.name || 'Por determinar'}
                  dia={fila.dia}
                  evento={fila.evento}
                  tatami={combate.mat || ''}
                  resultado={resultadoDe(combate, atleta.id)}
                />
              );
            })}
          </>
        )}
        <TituloSeccion>Mis atletas</TituloSeccion>
        {mios.map((a) => tarjetaAtleta(a, true))}
        {esperando}
      </>
    );
  }

  function listaGrupoPanel(): ReactNode {
    const entradas: EntradaListaGrupo[] = grupoActual().map((e) => {
      const casa = atletaDeEntrada(e);
      return {
        id: e.id,
        nombre: e.name,
        club: e.club || casa?.club || 'sin club',
        sinCombates: !casa,
      };
    });
    return <ListaGrupo entradas={entradas} onQuitar={quitarDelGrupo} />;
  }

  function vistaBuscar(d: Datos): ReactNode {
    return (
      <LimiteError mensaje="No se pudo mostrar la búsqueda. Prueba con otro texto o recarga la página." reinicio={consulta}>
        <ResultadosBusqueda
          datos={d}
          consulta={consulta}
          aviso={avisoSinSchedule}
          tarjeta={(a) => tarjetaAtleta(a, false)}
        />
      </LimiteError>
    );
  }

  function vistaTatamis(d: Datos): ReactNode {
    // Se agrupa por NOMBRE de tatami, no por evento: en un pabellón hay unos
    // pocos tatamis físicos y los bloques (Gi/No-Gi × sábado/domingo) los
    // reutilizan con ids distintos. Quien está delante del Mat 3 quiere ver qué
    // toca ahí, sea del evento que sea.
    const porMat = new Map<string, Combate[]>();
    for (const m of d.mats) {
      const clave = m.name ?? '';
      if (!porMat.has(clave)) porMat.set(clave, []);
    }
    for (const c of d.matches) {
      porMat.get(c.mat ?? '')?.push(c);
    }
    const streams = new Map((d.streams ?? []).map((s) => [s.mat, s.url]));

    const nombres = [...porMat.keys()].sort();
    if (!nombres.length) return avisoSinSchedule || <Vacio>Todavía no hay tatamis publicados.</Vacio>;

    return nombres.map((n) => {
      const combates = (porMat.get(n) ?? [])
        .sort((a, b) => (a.estimatedStart || '').localeCompare(b.estimatedStart || ''));
      const enCurso = combates.filter((c) => c.state === 'running');
      const siguientes = combates.filter((c) => c.state !== 'finished' && c.state !== 'running');
      return (
        <TarjetaTatami
          key={n}
          nombre={n}
          resumen={`${combates.length} combates · ${enCurso.length} en curso`}
          combates={[...enCurso, ...siguientes].slice(0, 5).map(filaDeTatami)}
          transmision={streams.get(n)}
        />
      );
    });
  }

  /* ---------- Ficha de atleta ---------- */
  function contenidoDetalle(atleta: Atleta, d: Datos): ReactNode {
    // Si compite en varios eventos conviene que se vea: sus combates salen
    // mezclados en una sola lista ordenada por hora.
    const enEventos = (atleta.events || [])
      .map((id) => d.events.find((e) => e.id === id)?.label || id);
    const combates = combatesDe(atleta, porId);
    return (
      <>
        <TextoTenue>{atleta.club || '—'}{atleta.country ? ` · ${atleta.country}` : ''}</TextoTenue>
        {enEventos.length > 1 && <TextoTenue>Compite en: {enEventos.join(' y ')}</TextoTenue>}
        {atleta.medals.length > 0 && (
          <TextoTenue>
            {atleta.medals.map((m, i) => (
              <Fragment key={`${m.bracketId}|${m.medal}`}>
                {i > 0 && <br />}
                <Medalla tipo={MEDALLA[m.medal]} /> {m.category || ''}
              </Fragment>
            ))}
          </TextoTenue>
        )}
        <Llaves llaves={llavesDe(atleta, { conCategoria: true })} />
        <TituloSeccion nivel={3}>Combates</TituloSeccion>
        {combates.length
          ? combates.map((c) => <FilaCombate key={c.id} {...filaDeAtleta(c, atleta.id)} />)
          : <TextoTenue>Sin combates.</TextoTenue>}
      </>
    );
  }

  /* ---------- Pintado ---------- */
  const estado = textoEstado({ datos, situacion, ahora, esPanel, modoEstatico });
  const contadorSeguidos = datos
    ? datos.athletes.filter(esMio).length + grupoActual().filter((e) => !atletaDeEntrada(e)).length
    : 0;
  const atletaDetalle = detalleId && datos ? datos.athletes.find((a) => a.id === detalleId) : undefined;


  return (
    <>
      <Cabecera
        titulo={nombre || marca.teamName}
        logo={marca.logo}
        onVolver={modoEstatico ? undefined : () => { location.hash = '#/'; }}
        enlaceEvento={urlDelEvento(datos)}
        onRecargar={recargar}
      >
        <LineaEstado id="estado" vieja={estado.vieja}>{estado.texto}</LineaEstado>
      </Cabecera>

      {!inexistente && (
        <Pestanas
          activa={vista}
          onCambiar={(id) => setVista(id as Vista)}
          pestanas={[
            { id: 'seguidos', etiqueta: 'Mis atletas', contador: contadorSeguidos },
            { id: 'buscar', etiqueta: 'Buscar' },
            { id: 'tatamis', etiqueta: 'Tatamis' },
          ]}
        />
      )}

      {aviso && <Aviso tono={aviso.error ? 'error' : 'ok'}>{aviso.texto}</Aviso>}

      <main>
        <section id="vista-seguidos" hidden={vista !== 'seguidos'}>
          {/* Fuera de la lista: el repintado de cada refresco no debe borrar lo que se está escribiendo. */}
          {esPanel && !inexistente && <FormAltaGrupo onEnviar={altaManual} />}
          <div id="lista-seguidos">
            {vista === 'seguidos' && (datos ? vistaSeguidos(datos) : cuerpoVacio())}
          </div>
        </section>

        <section id="vista-buscar" hidden={vista !== 'buscar'}>
          <CampoBusqueda
            ref={campoBusqueda}
            id="busqueda"
            placeholder="Nombre, club o categoría…"
            aria-label="Buscar atleta"
            value={consulta}
            onChange={(ev) => setConsulta(ev.target.value)}
          />
          <div id="resultados">
            {vista === 'buscar' && (datos ? vistaBuscar(datos) : cuerpoVacio())}
          </div>
        </section>

        <section id="vista-tatamis" hidden={vista !== 'tatamis'}>
          {vista === 'tatamis' && (datos ? vistaTatamis(datos) : cuerpoVacio())}
        </section>
      </main>

      <PanelDetalle
        abierto={!!atletaDetalle}
        titulo={atletaDetalle?.name ?? ''}
        onCerrar={() => setDetalleId(null)}
      >
        {atletaDetalle && datos && contenidoDetalle(atletaDetalle, datos)}
      </PanelDetalle>
    </>
  );
}
