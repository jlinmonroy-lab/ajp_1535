/* Frontend del seguimiento de un evento de Smoothcomp.
 *
 * Sin dependencias ni build. Dos pantallas, según la URL:
 *   #/                 buscador de eventos (buscador.js)
 *   #/evento/33588     tablero de ese evento (este fichero)
 * Descarga /api/events/<ids>/data, lo guarda en memoria y pinta. El polling usa
 * ETag, así que un ciclo sin cambios no descarga nada.
 *
 * Si no hay servidor (la web servida como ficheros estáticos, p. ej. en GitHub
 * Pages) cae al modo de siempre: un único evento y un data.json publicado.
 */
'use strict';

const REFRESCO_MS = 30000;
const ESPERA_CARGANDO_MS = 3000;     // mientras el servidor lee un evento por primera vez
const ESPERA_REINTENTO_MS = 10000;   // tras un error del servidor o de Smoothcomp
// El servidor contesta con lo que tiene y refresca detrás. Si lo recibido es más
// viejo que un ciclo de refresco (75 s) con margen, quien abre un evento que
// nadie miraba vería datos viejos hasta el siguiente sondeo: se vuelve a
// preguntar enseguida, unas pocas veces.
const EDAD_SOSPECHOSA_MS = 100 * 1000;
const ESPERA_REVALIDAR_MS = 5000;
const MAX_REVALIDACIONES = 3;
// La clave no incluye el evento: el id de atleta es nombre + club, así que quien
// sigues vale en cualquier evento en el que aparezca.
const CLAVE_SEGUIDOS = 'sbjj:seguidos';

// El botón "Seguir para todos" escribe la lista del grupo en el servidor, y eso
// solo se permite desde el equipo donde corre. En la web pública ni se enseña:
// sería una opción que nadie podría usar.
const ESdPANEL = ['localhost', '127.0.0.1'].includes(location.hostname);

// Lo pulsado en el panel tarda un ciclo en volver dentro de los datos. Hasta
// que vuelva se recuerda aquí; si no, el refresco de cada 30s lo desmarcaría y
// parecería que el botón no funciona.
const pendientesGrupo = new Map();   // athleteId -> { alta, momento }
const ESPERA_CONFIRMACION_MS = 3 * 60 * 1000;
const MEDALLAS = { gold: '🥇', silver: '🥈', bronze: '🥉' };

let marca = { teamName: 'FC Team', logo: 'img/logo.png' };
let modoEstatico = false;   // sin servidor: se lee data.json y hay un solo evento
let eventoIds = null;       // evento abierto ("33588" o "1535,1526"); null en el inicio
let generacion = 0;         // cada apertura/cierre/recarga la sube e invalida lo que estuviera en vuelo
let temporizadorCarga = null;
let temporizadorEstado = null;
let recordado = false;      // ¿ya está este evento en "Recientes"?
let revalidaciones = 0;     // sondeos rápidos seguidos por datos viejos

let datos = null;
let etag = null;
let porId = new Map();      // id de combate -> combate
let vista = 'seguidos';

/* ---------- Seguidos (locales a este navegador) ---------- */
function leerSeguidos() {
  return new Set(leerLocal(CLAVE_SEGUIDOS, []));
}
function guardarSeguidos(conjunto) {
  guardarLocal(CLAVE_SEGUIDOS, [...conjunto]);
}
let seguidos = leerSeguidos();

/* ---------- Utilidades ---------- */
function hora(iso) {
  if (!iso) return '--:--';
  const d = new Date(iso);
  return isNaN(d) ? '--:--'
    : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

/* ---------- Jornadas ----------
   Hubo un selector Sábado/Domingo, pero no aportaba: las fichas enseñan todos
   los combates del atleta de todas formas, así que las dos jornadas se veían
   casi iguales. Ahora se muestra todo junto y cada combate dice su día. */
function diaCorto(iso) {
  const d = new Date(`${iso}T12:00:00`);
  return isNaN(d) ? '' : d.toLocaleDateString([], { weekday: 'short', day: 'numeric' });
}

function hace(iso) {
  const s = Math.max(0, (Date.now() - new Date(iso)) / 1000);
  if (s < 60) return `hace ${Math.floor(s)}s`;
  if (s < 3600) return `hace ${Math.floor(s / 60)} min`;
  return `hace ${Math.floor(s / 3600)} h`;
}

/* ---------- Direcciones ---------- */
// Relativas a propósito: la web funciona igual si cuelga de una subcarpeta.
const urlDatos = () => (modoEstatico ? 'data.json' : `api/events/${eventoIds}/data`);
const urlGrupo = () => (modoEstatico ? '/api/grupo' : `api/events/${eventoIds}/grupo`);

class ErrorApi extends Error {
  constructor(estado, mensaje) {
    super(mensaje);
    this.estado = estado;
  }
}

/* ---------- Cabecera ---------- */
function ponerTitulo(nombre) {
  $('#titulo').textContent = nombre || marca.teamName;
  document.title = nombre ? `${nombre} · ${marca.teamName}` : `Eventos · ${marca.teamName}`;
}

function nombreEvento() {
  return datos.events.map((e) => e.name || `Evento ${e.id}`).join(' + ');
}

function encabezadoEvento() {
  ponerTitulo(nombreEvento());
  // Un solo evento: enlace a su página en Smoothcomp.
  const enlace = $('#enlace-smoothcomp');
  const e = datos.events.length === 1 ? datos.events[0] : null;
  const candidata = e && (e.url || (e.baseUrl ? `${e.baseUrl}/es/event/${e.id}` : null));
  const url = /^https:\/\//i.test(candidata || '') ? candidata : null;   // nunca javascript:
  enlace.classList.toggle('oculta', !url);
  if (url) enlace.href = url;
}

function sinSchedule() {
  return !!datos && datos.events.length > 0 && datos.events.every((e) => e.published === false);
}

function avisoSinSchedule() {
  if (!sinSchedule()) return '';
  return `
    <div class="tarjeta aviso-evento">
      <strong>El schedule aún no está publicado.</strong><br>
      <span class="sub">El organizador todavía no ha publicado los cuadros ni los horarios,
      así que no hay atletas ni combates que enseñar. Esta pantalla lo vuelve a comprobar sola.</span>
    </div>`;
}

/* ---------- Carga ---------- */
// Cuenta de lo que pasa en cada ciclo: devuelve cuánto esperar hasta el siguiente,
// o null si no hay nada más que esperar (evento inexistente, o ya se cambió de pantalla).
async function cargar() {
  const miGeneracion = generacion;
  const cuerpoVacio = (html) => {
    if (datos) return;
    $('#lista-seguidos').innerHTML = html;
    $('#resultados').innerHTML = html;
    $('#vista-tatamis').innerHTML = html;
  };

  try {
    const cabeceras = etag ? { 'If-None-Match': etag } : {};
    const resp = await fetch(urlDatos(), { cache: 'no-store', headers: cabeceras });
    if (miGeneracion !== generacion) return null;

    if (resp.status === 304) { pintarEstado(); return esperaTrasDatos(); }

    if (resp.status === 202) {
      // El servidor está leyendo el evento de Smoothcomp por primera vez.
      const info = await resp.json();
      if (miGeneracion !== generacion) return null;
      const conocido = (info.events || []).find((e) => e.title);
      if (conocido && !datos) ponerTitulo(conocido.title);
      $('#estado').textContent = 'Leyendo el schedule de Smoothcomp… puede tardar hasta un minuto';
      $('#estado').classList.remove('vieja');
      cuerpoVacio('<p class="vacio">Leyendo el schedule de Smoothcomp…<br>' +
        '<span class="sub">Los eventos grandes tardan un poco la primera vez.</span></p>');
      return ESPERA_CARGANDO_MS;
    }

    if (!resp.ok) throw new ErrorApi(resp.status, await mensajeDeError(resp));

    etag = resp.headers.get('ETag');
    const nuevos = await resp.json();
    if (miGeneracion !== generacion) return null;
    datos = nuevos;
    porId = new Map(datos.matches.map((m) => [m.id, m]));
    revisarPendientes();
    encabezadoEvento();
    if (!recordado && !modoEstatico) {
      recordado = true;
      const e = datos.events[0] || {};
      Inicio.recordar({ ...e, id: eventoIds, title: nombreEvento() });
    }
    pintar();
    return esperaTrasDatos();
  } catch (e) {
    if (miGeneracion !== generacion) return null;
    const estado = $('#estado');
    estado.classList.add('vieja');

    if (e instanceof ErrorApi && e.estado === 404) {
      document.body.dataset.evento = 'inexistente';
      estado.textContent = 'Ese evento no existe';
      cuerpoVacio(`<p class="vacio">${escapar(e.message)}<br>
        <a href="#/" class="llave">‹ Volver a los eventos</a></p>`);
      return null;
    }
    estado.textContent = e instanceof ErrorApi
      ? `No se pudo leer el evento (${e.message})`
      : `Sin conexión con los datos (${e.message})`;
    cuerpoVacio(`<p class="vacio">${escapar(estado.textContent)}<br>
      <span class="sub">Se reintenta solo.</span></p>`);
    return ESPERA_REINTENTO_MS;
  }
}

// Cuánto esperar tras recibir datos válidos.
function esperaTrasDatos() {
  const viejos = !modoEstatico && datos && !datos.stale
    && Date.now() - new Date(datos.fetchedAt) > EDAD_SOSPECHOSA_MS;
  if (viejos && revalidaciones < MAX_REVALIDACIONES) {
    revalidaciones += 1;
    return ESPERA_REVALIDAR_MS;
  }
  revalidaciones = 0;
  return REFRESCO_MS;
}

async function ciclo() {
  const miGeneracion = generacion;
  const espera = await cargar();
  if (espera == null || miGeneracion !== generacion) return;
  temporizadorCarga = setTimeout(ciclo, espera);
}

function reiniciarCiclo() {
  generacion += 1;
  clearTimeout(temporizadorCarga);
  etag = null;
  ciclo();
}

// Tres ciclos del servidor. Pasado eso, o se ha parado o ha dejado de refrescar.
const LIMITE_SIN_REFRESCO_MS = 4 * 60 * 1000;

function pintarEstado() {
  if (!datos) return;
  const estado = $('#estado');
  const total = `${datos.matches.length} combates · ${datos.athletes.length} atletas`;
  const antiguedad = Date.now() - new Date(datos.fetchedAt);

  if (sinSchedule()) {
    estado.textContent = 'Schedule sin publicar · se vuelve a comprobar solo';
    estado.classList.remove('vieja');
  } else if (datos.stale) {
    // El servidor vive pero Smoothcomp le falla: él mismo lo marcó.
    estado.textContent = `⚠ Datos sin actualizar desde ${hora(datos.staleSince)} · ${total}`;
    estado.classList.add('vieja');
  } else if (antiguedad > LIMITE_SIN_REFRESCO_MS) {
    // Nadie está generando datos. Es distinto de `stale`, que lo pone el propio
    // servidor: aquí puede que ni esté corriendo, y callarse haría creer que todo
    // va bien mientras la web enseña una foto vieja.
    estado.textContent = `⚠ Sin actualizarse desde ${hace(datos.fetchedAt)}`
      + (ESdPANEL && modoEstatico ? ' — ¿está corriendo el scraper?' : '') + ` · ${total}`;
    estado.classList.add('vieja');
  } else {
    estado.textContent = `Actualizado ${hace(datos.fetchedAt)} · ${total}`;
    estado.classList.remove('vieja');
  }
}

/* ---------- Combates ---------- */
function combatesDe(atleta) {
  return atleta.matchIds.map((id) => porId.get(id)).filter(Boolean);
}

// Se compara por athleteId, no por inscripción: la misma persona tiene un
// event_registration_id distinto en cada uno de los eventos en los que compite.
function rivalDe(combate, athleteId) {
  return combate.sides.find((s) => s.athleteId !== athleteId) || null;
}

function etiquetaEvento(combate) {
  return combate.eventLabel
    ? `<span class="etiqueta evento">${escapar(combate.eventLabel)}</span>` : '';
}

function etiquetaResultado(combate, athleteId) {
  if (combate.state === 'running') return '<span class="etiqueta vivo">EN CURSO</span>';
  if (combate.state !== 'finished') return '<span class="etiqueta">Pendiente</span>';

  const yo = combate.sides.find((s) => s.athleteId === athleteId);
  if (!yo) return '<span class="etiqueta">Terminado</span>';
  const clase = yo.isWinner ? 'ganado' : 'perdido';
  const texto = yo.isWinner ? 'Ganó' : 'Perdió';
  const modo = combate.wonBy ? ` · ${combate.wonBy}` : '';
  return `<span class="etiqueta ${clase}">${texto}${escapar(modo)}</span>`;
}

function filaCombate(combate, athleteId) {
  const rival = rivalDe(combate, athleteId);
  const nombreRival = rival ? rival.name : 'Por determinar';
  const ronda = combate.round ? `${escapar(combate.round)} · ` : '';
  const cuando = combate.day
    ? `<span class="etiqueta">${escapar(diaCorto(combate.day))}</span> ` : '';
  return `
    <div class="combate">
      <span class="hora">${hora(combate.estimatedStart)}</span>
      <span class="detalle-combate">
        <span class="rival">vs ${escapar(nombreRival)}</span><br>
        <span class="sub">${cuando}${etiquetaEvento(combate)} ${ronda}${escapar(combate.mat || '')}</span>
      </span>
      ${etiquetaResultado(combate, athleteId)}
    </div>`;
}

/* ---------- Vistas ---------- */
function tarjetaAtleta(atleta, { conCombates = false } = {}) {
  const sigue = seguidos.has(atleta.id);
  const medalla = atleta.bestMedal
    ? `<span class="medalla" data-m="${atleta.bestMedal}">${MEDALLAS[atleta.bestMedal]}</span>` : '';
  // Explica por qué está en la lista alguien a quien no has seguido tú.
  const delGrupo = enGrupo(atleta) ? '<span class="etiqueta grupo">grupo</span> ' : '';
  const foto = atleta.image
    ? `<img class="foto" src="${escapar(atleta.image)}" alt="" loading="lazy">`
    : '<span class="foto"></span>';

  let combates = '';
  if (conCombates) {
    const lista = combatesDe(atleta);
    combates = lista.length
      ? lista.map((c) => filaCombate(c, atleta.id)).join('')
      : '<p class="sub">Sin combates en el schedule todavía.</p>';
  }

  const llaves = conCombates ? enlacesLlave(atleta) : '';

  return `
    <article class="tarjeta">
      <div class="tarjeta-cabecera">
        ${foto}
        <span class="crece" data-atleta="${escapar(atleta.id)}">
          <span class="nombre">${escapar(atleta.name)} ${medalla}</span><br>
          <span class="sub">${delGrupo}${escapar(atleta.club || '—')} · ${escapar(atleta.categories[0] || '')}</span>
        </span>
        <button class="seguir ${sigue ? 'activo' : ''}"
                data-seguir="${escapar(atleta.id)}">${sigue ? 'Siguiendo' : 'Seguir'}</button>
      </div>
      ${ESdPANEL ? `<button class="todos ${enGrupo(atleta) ? 'activo' : ''}"
            data-todos="${escapar(atleta.id)}" data-nombre="${escapar(atleta.name)}">
            ${enGrupo(atleta) ? '✓ Lo ve todo el grupo' : 'Seguir para todos'}</button>` : ''}
      ${combates}
      ${llaves}
    </article>`;
}

function enGrupo(atleta) {
  const pendiente = pendientesGrupo.get(atleta.id);
  return pendiente ? pendiente.alta : !!atleta.inGroup;
}

function esMio(atleta) {
  return enGrupo(atleta) || seguidos.has(atleta.id);
}

// Deja de recordar lo pendiente en cuanto los datos lo confirman, y avisa si
// pasa demasiado tiempo sin que llegue: marcar algo que nadie va a ver sería
// peor que decir que no se ha publicado.
function revisarPendientes() {
  for (const [id, pendiente] of [...pendientesGrupo]) {
    const atleta = datos.athletes.find((a) => a.id === id);
    if (atleta && !!atleta.inGroup === pendiente.alta) {
      pendientesGrupo.delete(id);
    } else if (Date.now() - pendiente.momento > ESPERA_CONFIRMACION_MS) {
      pendientesGrupo.delete(id);
      avisar(modoEstatico
        ? 'El cambio no se ha publicado. ¿Está corriendo el scraper?'
        : 'El cambio no ha llegado a los datos. Recarga la página.', true);
    }
  }
}

// Enlace a la llave en Smoothcomp. Con más de un cuadro (Gi y No-Gi) se
// distingue por categoría, que si no no se sabe cuál es cuál.
function enlacesLlave(atleta, { conCategoria = false } = {}) {
  const cuadros = atleta.brackets || [];
  if (!cuadros.length) return '';
  return `<div class="llaves">` + cuadros.map((b) => {
    const etiqueta = (conCategoria || cuadros.length > 1) && b.category
      ? `${b.eventLabel ? escapar(b.eventLabel) + ' · ' : ''}${escapar(b.category)}`
      : 'Ver llave';
    return `<a class="llave" href="${escapar(b.url)}" target="_blank" rel="noopener"
              title="Ver la llave en Smoothcomp">⤢ ${etiqueta}</a>`;
  }).join('') + `</div>`;
}

function pintarSeguidos() {
  const caja = $('#lista-seguidos');
  const mios = datos.athletes.filter(esMio);
  const sinCombates = grupoActual().filter((e) => !atletaDeEntrada(e));
  $('#contador-seguidos').textContent = (mios.length + sinCombates.length) || '';

  // En el panel la lista del grupo se gestiona aparte, con su botón de quitar.
  const gestion = ESdPANEL ? listaGrupoPanel() : '';
  const esperando = ESdPANEL ? '' : sinCombates.map(tarjetaSinCombates).join('');
  const aviso = avisoSinSchedule();

  if (!mios.length) {
    caja.innerHTML = gestion + aviso + (esperando
      ? '<h2 class="seccion-titulo">Mis atletas</h2>' + esperando
      : (aviso ? '' : `<p class="vacio">Todavía no hay atletas en la lista.<br>
      Usa <strong>Buscar</strong> para añadir a quien quieras seguir.</p>`));
    return;
  }

  // Lo primero que quiere ver alguien en el pabellón: qué toca ahora y qué viene.
  const proximos = [];
  for (const a of mios) {
    for (const c of combatesDe(a)) {
      if (c.state !== 'finished') proximos.push({ atleta: a, combate: c });
    }
  }
  proximos.sort((x, y) => (x.combate.estimatedStart || '').localeCompare(y.combate.estimatedStart || ''));

  let html = aviso;
  if (proximos.length) {
    html += '<h2 class="seccion-titulo">Próximos combates</h2>';
    html += proximos.slice(0, 8).map(({ atleta, combate }) => `
      <article class="tarjeta">
        <div class="tarjeta-cabecera proximo">
          <span class="hora">${hora(combate.estimatedStart)}</span>
          <span class="crece">
            <span class="nombre">${escapar(atleta.name)}</span><br>
            <span class="sub">vs ${escapar((rivalDe(combate, atleta.id) || {}).name || 'Por determinar')}
              · ${combate.day ? escapar(diaCorto(combate.day)) + ' ' : ''}${etiquetaEvento(combate)} ${escapar(combate.mat || '')}</span>
          </span>
          ${etiquetaResultado(combate, atleta.id)}
        </div>
      </article>`).join('');
  }

  html += '<h2 class="seccion-titulo">Mis atletas</h2>';
  html += mios.map((a) => tarjetaAtleta(a, { conCombates: true })).join('') + esperando;
  caja.innerHTML = gestion + html;
}

function pintarBusqueda() {
  const consulta = normalizar($('#busqueda').value.trim());
  const caja = $('#resultados');

  if (consulta.length < 2) {
    caja.innerHTML = avisoSinSchedule() || '<p class="vacio">Escribe al menos dos letras.</p>';
    return;
  }

  const encontrados = datos.athletes.filter((a) =>
    normalizar(a.name).includes(consulta) ||
    normalizar(a.club).includes(consulta) ||
    a.categories.some((c) => normalizar(c).includes(consulta)));

  caja.innerHTML = encontrados.length
    ? `<p class="sub">${encontrados.length} resultado(s)</p>` +
      encontrados.slice(0, 60).map((a) => tarjetaAtleta(a)).join('')
    : (avisoSinSchedule() || '<p class="vacio">Ningún atleta coincide.</p>');
}

function pintarTatamis() {
  const caja = $('#vista-tatamis');
  // Se agrupa por NOMBRE de tatami, no por evento: en un pabellón hay unos
  // pocos tatamis físicos y los bloques (Gi/No-Gi × sábado/domingo) los
  // reutilizan con ids distintos. Quien está delante del Mat 3 quiere ver qué
  // toca ahí, sea del evento que sea.
  const porMat = new Map();
  for (const m of datos.mats) {
    if (!porMat.has(m.name)) porMat.set(m.name, []);
  }
  for (const c of datos.matches) {
    if (porMat.has(c.mat)) porMat.get(c.mat).push(c);
  }

  const streams = new Map((datos.streams || []).map((s) => [s.mat, s.url]));

  const tarjeta = (nombre) => {
    const combates = (porMat.get(nombre) || [])
      .sort((a, b) => (a.estimatedStart || '').localeCompare(b.estimatedStart || ''));
    const enCurso = combates.filter((c) => c.state === 'running');
    const siguientes = combates.filter((c) => c.state !== 'finished' && c.state !== 'running');
    const mostrar = [...enCurso, ...siguientes].slice(0, 5);
    const url = streams.get(nombre);

    return `
      <article class="tarjeta">
        <div class="tarjeta-cabecera">
          <span class="crece">
            <span class="nombre">${escapar(nombre)}</span><br>
            <span class="sub">${combates.length} combates · ${enCurso.length} en curso</span>
          </span>
        </div>
        ${mostrar.length
          ? mostrar.map((c) => `
            <div class="combate">
              <span class="hora">${hora(c.estimatedStart)}</span>
              <span class="detalle-combate">
                <span class="rival">${escapar(c.sides.map((s) => s.name).join(' vs ') || 'Por determinar')}</span><br>
                <span class="sub">${c.day ? escapar(diaCorto(c.day)) + ' ' : ''}${etiquetaEvento(c)} ${escapar(c.category.raw || '')}</span>
              </span>
              ${c.state === 'running' ? '<span class="etiqueta vivo">EN CURSO</span>' : ''}
            </div>`).join('')
          : '<p class="sub">Sin combates pendientes.</p>'}
        ${url ? `<a class="enlace-stream" href="${escapar(url)}" target="_blank" rel="noopener">Ver retransmisión ↗</a>` : ''}
      </article>`;
  };

  const nombres = [...porMat.keys()].sort();
  caja.innerHTML = (nombres.length
    ? nombres.map(tarjeta).join('')
    : (avisoSinSchedule() || '<p class="vacio">Todavía no hay tatamis publicados.</p>'));
}

function pintar() {
  if (!datos) return;
  pintarEstado();
  if (vista === 'seguidos') pintarSeguidos();
  else if (vista === 'buscar') pintarBusqueda();
  else pintarTatamis();
}

/* ---------- Lista del grupo (solo desde el panel) ---------- */

// Lo que devuelve el servidor tras cada cambio; manda sobre los datos, que
// pueden tardar un poco en enterarse.
let grupoPanel = null;

function grupoActual() {
  return (ESdPANEL && grupoPanel) ? grupoPanel.atletas : ((datos.group || {}).athletes || []);
}

// El atleta de los datos que corresponde a una entrada del grupo. Mismo
// criterio que el servidor: id exacto, o solo el nombre si se apuntó sin club.
function atletaDeEntrada(entrada) {
  const id = entrada.id || '';
  const soloNombre = id.endsWith('|') ? id.slice(0, -1) : null;
  return datos.athletes.find((a) =>
    a.id === id || (soloNombre !== null && a.id.split('|')[0] === soloNombre));
}

// Apuntado al grupo pero aún sin combates: antes de que se publique el schedule
// es lo normal, y así todos ven ya quién va.
function tarjetaSinCombates(entrada) {
  return `
    <article class="tarjeta">
      <div class="tarjeta-cabecera">
        <span class="foto"></span>
        <span class="crece">
          <span class="nombre">${escapar(entrada.name)}</span><br>
          <span class="sub"><span class="etiqueta grupo">grupo</span> ${escapar(entrada.club || '—')}</span>
        </span>
      </div>
      <p class="sub">Sin combates en el schedule todavía.</p>
    </article>`;
}

function listaGrupoPanel() {
  const lista = grupoActual();
  const filas = lista.map((e) => {
    const casa = atletaDeEntrada(e);
    return `
      <div class="combate">
        <span class="detalle-combate">
          <span class="nombre">${escapar(e.name)}</span><br>
          <span class="sub">${escapar(e.club || (casa && casa.club) || 'sin club')}
            ${casa ? '' : ' · <span class="etiqueta">sin combates todavía</span>'}</span>
        </span>
        <button class="seguir" data-quitar="${escapar(e.id)}"
                data-nombre="${escapar(e.name)}">Quitar</button>
      </div>`;
  }).join('');
  return `<h2 class="seccion-titulo">Lista del grupo (${lista.length})</h2>
    <article class="tarjeta">${filas || '<p class="sub">Nadie todavía.</p>'}</article>`;
}

async function enviarGrupo(cuerpo) {
  const resp = await fetch(urlGrupo(), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(cuerpo),
  });
  if (!resp.ok) throw new Error(await mensajeDeError(resp));
  grupoPanel = await resp.json();
  return grupoPanel;
}

const AVISO_GRUPO_ALTA = () => (modoEstatico
  ? 'En un par de minutos lo verá todo el grupo.'
  : 'Ya lo ve todo el grupo.');

async function altaManual(ev) {
  ev.preventDefault();
  const form = ev.target;
  const name = form.nombre.value.trim();
  const club = form.club.value.trim();
  if (!name) return;
  form.querySelector('button').disabled = true;
  try {
    await enviarGrupo({ name, club, accion: 'añadir' });
    form.reset();
    pintar();
    avisar(`${name} añadido. ${AVISO_GRUPO_ALTA()}`);
  } catch (e) {
    avisar(`No se pudo guardar (${e.message}). ¿Está el panel arrancado?`, true);
  } finally {
    form.querySelector('button').disabled = false;
    form.nombre.focus();
  }
}

async function quitarDelGrupo(boton) {
  boton.disabled = true;
  try {
    await enviarGrupo({ id: boton.dataset.quitar, name: boton.dataset.nombre, accion: 'quitar' });
    pintar();
    avisar(`${boton.dataset.nombre} quitado de la lista del grupo.`);
  } catch (e) {
    boton.disabled = false;
    avisar(`No se pudo guardar (${e.message}). ¿Está el panel arrancado?`, true);
  }
}

async function marcarParaTodos(boton) {
  const id = boton.dataset.todos;
  const atleta = datos.athletes.find((a) => a.id === id);
  const accion = (atleta && enGrupo(atleta)) ? 'quitar' : 'añadir';

  boton.disabled = true;
  boton.textContent = 'Guardando…';
  try {
    await enviarGrupo({ id, name: boton.dataset.nombre, accion });

    // Se recuerda hasta que los datos lo confirmen, para que el refresco
    // periódico no lo desmarque a los pocos segundos.
    pendientesGrupo.set(id, { alta: accion === 'añadir', momento: Date.now() });
    pintar();
    avisar(accion === 'añadir'
      ? `Añadido. ${AVISO_GRUPO_ALTA()}`
      : 'Quitado de la lista del grupo.');
  } catch (e) {
    boton.disabled = false;
    avisar(`No se pudo guardar (${e.message}). ¿Está el panel arrancado?`, true);
  }
}

function avisar(texto, error = false) {
  const caja = $('#aviso');
  caja.textContent = texto;
  caja.className = `aviso ${error ? 'error' : ''}`;
  clearTimeout(avisar._t);
  avisar._t = setTimeout(() => { caja.className = 'aviso oculta'; }, 5000);
}

/* ---------- Detalle de atleta ---------- */
function abrirDetalle(athleteId) {
  const atleta = datos.athletes.find((a) => a.id === athleteId);
  if (!atleta) return;

  $('#detalle-nombre').textContent = atleta.name;
  const medallas = atleta.medals.length
    ? `<p class="sub">${atleta.medals.map((m) =>
        `${MEDALLAS[m.medal]} ${escapar(m.category || '')}`).join('<br>')}</p>`
    : '';
  // Si compite en varios eventos conviene que se vea: sus combates salen
  // mezclados en una sola lista ordenada por hora.
  const enEventos = (atleta.events || [])
    .map((id) => (datos.events.find((e) => e.id === id) || {}).label || id);
  const eventos = enEventos.length > 1
    ? `<p class="sub">Compite en: ${escapar(enEventos.join(' y '))}</p>` : '';
  $('#detalle-cuerpo').innerHTML = `
    <p class="sub">${escapar(atleta.club || '—')}${atleta.country ? ' · ' + escapar(atleta.country) : ''}</p>
    ${eventos}
    ${medallas}
    ${enlacesLlave(atleta, { conCategoria: true })}
    <h3 class="seccion-titulo">Combates</h3>
    ${combatesDe(atleta).map((c) => filaCombate(c, atleta.id)).join('') || '<p class="sub">Sin combates.</p>'}`;
  $('#detalle').classList.remove('oculta');
}

/* ---------- Abrir y cerrar un evento ---------- */
function seleccionarVista(nombre) {
  vista = nombre;
  document.querySelectorAll('.pestana').forEach((b) => {
    const activa = b.dataset.vista === nombre;
    b.classList.toggle('activa', activa);
    b.setAttribute('aria-selected', String(activa));
  });
  document.querySelectorAll('.vista').forEach((v) => v.classList.add('oculta'));
  $(`#vista-${nombre}`).classList.remove('oculta');
}

function abrirEvento(ids) {
  cerrarEvento();
  eventoIds = ids;
  document.body.dataset.modo = 'evento';
  delete document.body.dataset.evento;
  seleccionarVista('seguidos');
  $('#busqueda').value = '';
  $('#estado').textContent = 'Cargando…';
  $('#estado').classList.remove('vieja');
  $('#lista-seguidos').innerHTML = '<p class="vacio">Cargando…</p>';
  $('#resultados').innerHTML = '';
  $('#vista-tatamis').innerHTML = '';
  ponerTitulo(null);
  window.scrollTo(0, 0);

  const miGeneracion = generacion;
  if (ESdPANEL) {
    $('#alta-grupo').classList.remove('oculta');
    fetch(urlGrupo(), { cache: 'no-store' }).then((r) => (r.ok ? r.json() : null))
      .then((g) => { if (g && miGeneracion === generacion) { grupoPanel = g; pintar(); } })
      .catch(() => { /* sin panel: se usa la lista de los datos */ });
  }

  temporizadorEstado = setInterval(pintarEstado, 10000);   // el "hace X" envejece solo
  ciclo();
}

function cerrarEvento() {
  generacion += 1;
  clearTimeout(temporizadorCarga);
  clearInterval(temporizadorEstado);
  eventoIds = null;
  datos = null;
  etag = null;
  porId = new Map();
  grupoPanel = null;
  recordado = false;
  revalidaciones = 0;
  pendientesGrupo.clear();
  $('#detalle').classList.add('oculta');
  $('#enlace-smoothcomp').classList.add('oculta');
}

/* ---------- Enrutado ---------- */
function enrutar() {
  const m = location.hash.match(/^#\/evento\/([\d,]+)$/);
  if (m) {
    if (m[1] !== eventoIds) abrirEvento(m[1]);
    return;
  }
  cerrarEvento();
  document.body.dataset.modo = 'inicio';
  ponerTitulo(null);
  Inicio.mostrar();
}

/* ---------- Eventos ---------- */
document.querySelectorAll('.pestana').forEach((boton) => {
  boton.addEventListener('click', () => {
    seleccionarVista(boton.dataset.vista);
    pintar();
    if (vista === 'buscar') $('#busqueda').focus();
  });
});

// Delegación: las tarjetas se repintan enteras en cada ciclo, así que no sirve
// enganchar escuchadores a cada botón.
document.addEventListener('click', (ev) => {
  const paraTodos = ev.target.closest('[data-todos]');
  if (paraTodos) return marcarParaTodos(paraTodos);
  const quitar = ev.target.closest('[data-quitar]');
  if (quitar) return quitarDelGrupo(quitar);

  const seguir = ev.target.closest('[data-seguir]');
  if (seguir) {
    const id = seguir.dataset.seguir;
    if (seguidos.has(id)) seguidos.delete(id); else seguidos.add(id);
    guardarSeguidos(seguidos);
    pintar();
    return;
  }
  const abrir = ev.target.closest('[data-atleta]');
  if (abrir) abrirDetalle(abrir.dataset.atleta);
});

$('#cerrar-detalle').addEventListener('click', () => $('#detalle').classList.add('oculta'));
$('#detalle').addEventListener('click', (ev) => {
  if (ev.target.id === 'detalle') $('#detalle').classList.add('oculta');
});
$('#busqueda').addEventListener('input', pintarBusqueda);
$('#recargar').addEventListener('click', reiniciarCiclo);
$('#volver').addEventListener('click', () => { location.hash = '#/'; });

if (ESdPANEL) {
  $('#alta-grupo').addEventListener('submit', altaManual);
}

/* ---------- Arranque ---------- */
async function arrancar() {
  try {
    const resp = await fetch('api/config', { cache: 'no-store' });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    marca = { ...marca, ...(await resp.json()) };
    const logo = document.querySelector('.logo');
    if (logo && marca.logo && !logo.src.endsWith(marca.logo)) logo.src = marca.logo;
  } catch {
    modoEstatico = true;     // sin servidor: un solo evento, leído de data.json
  }

  if (modoEstatico) {
    document.body.dataset.modo = 'evento';
    $('#volver').classList.add('oculta');
    abrirEvento(null);
    return;
  }

  window.addEventListener('hashchange', enrutar);
  enrutar();
}

arrancar();
