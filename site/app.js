/* Frontend de AJP en directo.
 *
 * Sin dependencias ni build: descarga data.json, lo guarda en memoria y pinta.
 * El polling usa ETag, así que un ciclo sin cambios no descarga nada.
 */
'use strict';

const REFRESCO_MS = 30000;
const CLAVE_SEGUIDOS = 'ajp:seguidos';
const CANAL_AJP = 'https://youtube.com/channel/UC7m2_Wx33tfrMYYVMVqIOzg/videos';

// El botón "Seguir para todos" escribe en la configuración del scraper, y eso
// solo puede hacerse desde el portátil donde corre. En la web pública ni se
// enseña: sería una opción que nadie podría usar.
const ESdPANEL = ['localhost', '127.0.0.1'].includes(location.hostname);

// Lo pulsado en el panel tarda un ciclo en volver dentro del data.json. Hasta
// que vuelva se recuerda aquí; si no, el refresco de cada 30s lo desmarcaría y
// parecería que el botón no funciona.
const pendientesGrupo = new Map();   // athleteId -> { alta, momento }
const ESPERA_CONFIRMACION_MS = 3 * 60 * 1000;
const MEDALLAS = { gold: '🥇', silver: '🥈', bronze: '🥉' };

let datos = null;
let etag = null;
let porId = new Map();      // id de combate -> combate
let vista = 'seguidos';

/* ---------- Almacenamiento local ----------
   Puede fallar (modo privado, cookies bloqueadas) y la app debe seguir
   funcionando sin ello, así que todo acceso va envuelto. */
function leerSeguidos() {
  try {
    return new Set(JSON.parse(localStorage.getItem(CLAVE_SEGUIDOS)) || []);
  } catch {
    return new Set();
  }
}
function guardarSeguidos(conjunto) {
  try {
    localStorage.setItem(CLAVE_SEGUIDOS, JSON.stringify([...conjunto]));
  } catch { /* sin persistencia, pero la sesión sigue */ }
}
let seguidos = leerSeguidos();

/* ---------- Utilidades ---------- */
const $ = (sel) => document.querySelector(sel);

// Buscar "muñoz" debe encontrar "Muñoz", y "jose" debe encontrar "José".
const normalizar = (texto) => (texto || '')
  .toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');

function escapar(texto) {
  const d = document.createElement('div');
  d.textContent = texto == null ? '' : String(texto);
  return d.innerHTML;
}

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

/* ---------- Carga ---------- */
async function cargar() {
  try {
    const cabeceras = etag ? { 'If-None-Match': etag } : {};
    const resp = await fetch('data.json', { cache: 'no-store', headers: cabeceras });

    if (resp.status === 304) { pintarEstado(); return; }
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

    etag = resp.headers.get('ETag');
    datos = await resp.json();
    porId = new Map(datos.matches.map((m) => [m.id, m]));
    revisarPendientes();

    const eventos = datos.events || [];
    if (eventos.length) {
      const etiquetas = eventos.map((e) => e.label || e.id).join(' + ');
      $('#nombre-evento').textContent = eventos.length === 1
        ? (eventos[0].name || etiquetas)
        : `AJP Madrid · ${etiquetas}`;
      document.title = $('#nombre-evento').textContent;
    }
    pintar();
  } catch (e) {
    const estado = $('#estado');
    estado.textContent = `Sin conexión con los datos (${e.message})`;
    estado.classList.add('vieja');
  }
}

// Tres ciclos del scraper. Pasado eso, o se ha parado o ha dejado de publicar.
const LIMITE_SIN_REFRESCO_MS = 4 * 60 * 1000;

function pintarEstado() {
  if (!datos) return;
  const estado = $('#estado');
  const total = `${datos.matches.length} combates · ${datos.athletes.length} atletas`;
  const antiguedad = Date.now() - new Date(datos.fetchedAt);

  if (datos.stale) {
    // El scraper vive pero el origen le falla: él mismo lo marcó.
    estado.textContent = `⚠ Datos sin actualizar desde ${hora(datos.staleSince)} · ${total}`;
    estado.classList.add('vieja');
  } else if (antiguedad > LIMITE_SIN_REFRESCO_MS) {
    // Nadie está generando datos. Es distinto de `stale`, que lo pone el propio
    // scraper: aquí puede que ni esté corriendo, y callarse haría creer que todo
    // va bien mientras la web enseña una foto vieja.
    estado.textContent = `⚠ Sin actualizarse desde ${hace(datos.fetchedAt)}`
      + (ESdPANEL ? ' — ¿está corriendo el scraper?' : '') + ` · ${total}`;
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
// event_registration_id distinto en cada uno de los dos eventos.
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

// Deja de recordar lo pendiente en cuanto el data.json publicado lo confirma, y
// avisa si pasa demasiado tiempo sin que llegue: marcar algo que nadie va a ver
// sería peor que decir que no se ha publicado.
function revisarPendientes() {
  for (const [id, pendiente] of [...pendientesGrupo]) {
    const atleta = datos.athletes.find((a) => a.id === id);
    if (atleta && !!atleta.inGroup === pendiente.alta) {
      pendientesGrupo.delete(id);
    } else if (Date.now() - pendiente.momento > ESPERA_CONFIRMACION_MS) {
      pendientesGrupo.delete(id);
      avisar('El cambio no se ha publicado. ¿Está corriendo el scraper?', true);
    }
  }
}

// Enlace a la llave en ajptour.com. Con más de un cuadro (Gi y No-Gi) se
// distingue por categoría, que si no no se sabe cuál es cuál.
function enlacesLlave(atleta, { conCategoria = false } = {}) {
  const cuadros = atleta.brackets || [];
  if (!cuadros.length) return '';
  return `<div class="llaves">` + cuadros.map((b) => {
    const etiqueta = (conCategoria || cuadros.length > 1) && b.category
      ? `${b.eventLabel ? escapar(b.eventLabel) + ' · ' : ''}${escapar(b.category)}`
      : 'Ver llave';
    return `<a class="llave" href="${escapar(b.url)}" target="_blank" rel="noopener"
              title="Ver la llave en ajptour.com">⤢ ${etiqueta}</a>`;
  }).join('') + `</div>`;
}

function pintarSeguidos() {
  const caja = $('#vista-seguidos');
  const mios = datos.athletes.filter(esMio);
  $('#contador-seguidos').textContent = mios.length || '';

  if (!mios.length) {
    caja.innerHTML = `<p class="vacio">Todavía no hay atletas en la lista.<br>
      Usa <strong>Buscar</strong> para añadir a quien quieras seguir.</p>`;
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

  let html = '';
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
  html += mios.map((a) => tarjetaAtleta(a, { conCombates: true })).join('');
  caja.innerHTML = html;
}

function pintarBusqueda() {
  const consulta = normalizar($('#busqueda').value.trim());
  const caja = $('#resultados');

  if (consulta.length < 2) {
    caja.innerHTML = '<p class="vacio">Escribe al menos dos letras.</p>';
    return;
  }

  const encontrados = datos.athletes.filter((a) =>
    normalizar(a.name).includes(consulta) ||
    normalizar(a.club).includes(consulta) ||
    a.categories.some((c) => normalizar(c).includes(consulta)));

  caja.innerHTML = encontrados.length
    ? `<p class="sub">${encontrados.length} resultado(s)</p>` +
      encontrados.slice(0, 60).map((a) => tarjetaAtleta(a)).join('')
    : '<p class="vacio">Ningún atleta coincide.</p>';
}

function pintarTatamis() {
  const caja = $('#vista-tatamis');
  // Se agrupa por NOMBRE de tatami, no por evento: en el pabellón hay seis
  // tatamis físicos y los cuatro bloques (Gi/No-Gi × sábado/domingo) los
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
    : '<p class="vacio">Todavía no hay tatamis publicados.</p>')
    + `<p class="sub" style="text-align:center;margin-top:1rem">
         <a class="enlace-stream" href="${CANAL_AJP}" target="_blank" rel="noopener">
           Canal de YouTube de AJP ↗</a></p>`;
}

function pintar() {
  if (!datos) return;
  pintarEstado();
  if (vista === 'seguidos') pintarSeguidos();
  else if (vista === 'buscar') pintarBusqueda();
  else pintarTatamis();
}

/* ---------- Lista del grupo (solo desde el panel) ---------- */
async function marcarParaTodos(boton) {
  const id = boton.dataset.todos;
  const atleta = datos.athletes.find((a) => a.id === id);
  const accion = (atleta && enGrupo(atleta)) ? 'quitar' : 'añadir';

  boton.disabled = true;
  boton.textContent = 'Guardando…';
  try {
    const resp = await fetch('/api/grupo', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id, name: boton.dataset.nombre, accion }),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

    // Se recuerda hasta que el data.json publicado lo confirme, para que el
    // refresco periódico no lo desmarque a los pocos segundos.
    pendientesGrupo.set(id, { alta: accion === 'añadir', momento: Date.now() });
    pintar();
    avisar(accion === 'añadir'
      ? 'Añadido. En un par de minutos lo verá todo el grupo.'
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
  // Si compite en los dos eventos conviene que se vea: sus combates de Gi y
  // No-Gi aparecen mezclados en una sola lista ordenada por hora.
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

/* ---------- Eventos ---------- */
document.querySelectorAll('.pestana').forEach((boton) => {
  boton.addEventListener('click', () => {
    document.querySelectorAll('.pestana').forEach((b) => {
      b.classList.remove('activa');
      b.setAttribute('aria-selected', 'false');
    });
    boton.classList.add('activa');
    boton.setAttribute('aria-selected', 'true');
    vista = boton.dataset.vista;
    document.querySelectorAll('.vista').forEach((v) => v.classList.add('oculta'));
    $(`#vista-${vista}`).classList.remove('oculta');
    pintar();
    if (vista === 'buscar') $('#busqueda').focus();
  });
});

// Delegación: las tarjetas se repintan enteras en cada ciclo, así que no sirve
// enganchar escuchadores a cada botón.
document.addEventListener('click', (ev) => {
  const paraTodos = ev.target.closest('[data-todos]');
  if (paraTodos) return marcarParaTodos(paraTodos);

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
$('#recargar').addEventListener('click', () => { etag = null; cargar(); });

/* ---------- Arranque ---------- */
cargar();
setInterval(cargar, REFRESCO_MS);
// El "hace X" envejece aunque no lleguen datos nuevos.
setInterval(pintarEstado, 10000);
