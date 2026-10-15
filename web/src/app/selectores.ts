/* De los datos de la API a lo que pintan los componentes de src/ui. Aquí vive todo el
   formateo (horas, días, «hace X», textos de estado); la librería solo recibe strings. */
import type { Atleta, Combate, Datos, MedallaDato } from '../tipos';
import type { FilaCombateProps, Llave, ResultadoCombate, TipoMedalla } from '../ui';
import type { Situacion } from './usarSondeoEvento';

export const MEDALLA: Record<MedallaDato, TipoMedalla> = { gold: 'oro', silver: 'plata', bronze: 'bronce' };

// Tres ciclos del servidor. Pasado eso, o se ha parado o ha dejado de refrescar.
export const LIMITE_SIN_REFRESCO_MS = 4 * 60 * 1000;

/* ---------- Fechas y horas ---------- */
export function hora(iso: string | null | undefined): string {
  if (!iso) return '--:--';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '--:--'
    : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

/* ---------- Jornadas ----------
   Hubo un selector Sábado/Domingo, pero no aportaba: las fichas enseñan todos
   los combates del atleta de todas formas, así que las dos jornadas se veían
   casi iguales. Ahora se muestra todo junto y cada combate dice su día. */
export function diaCorto(iso: string): string {
  const d = new Date(`${iso}T12:00:00`);
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString([], { weekday: 'short', day: 'numeric' });
}

export function hace(iso: string, ahora: number): string {
  const s = Math.max(0, (ahora - new Date(iso).getTime()) / 1000);
  if (s < 60) return `hace ${Math.floor(s)}s`;
  if (s < 3600) return `hace ${Math.floor(s / 60)} min`;
  return `hace ${Math.floor(s / 3600)} h`;
}

/* ---------- Evento ---------- */
export function nombreEvento(datos: Datos): string {
  return datos.events.map((e) => e.name || `Evento ${e.id}`).join(' + ');
}

// Un solo evento: enlace a su página en Smoothcomp. La librería solo pinta los https://.
export function urlDelEvento(datos: Datos | null): string | undefined {
  const e = datos && datos.events.length === 1 ? datos.events[0] : null;
  if (!e) return undefined;
  return e.url || (e.baseUrl ? `${e.baseUrl}/es/event/${e.id}` : undefined);
}

export function sinSchedule(datos: Datos | null): boolean {
  return !!datos && datos.events.length > 0 && datos.events.every((e) => e.published === false);
}

/* ---------- Línea de estado ---------- */
export interface EntradaEstado {
  datos: Datos | null;
  situacion: Situacion;
  ahora: number;
  esPanel: boolean;
  modoEstatico: boolean;
}

export function textoEstado({ datos, situacion, ahora, esPanel, modoEstatico }: EntradaEstado):
  { texto: string; vieja: boolean } {
  switch (situacion.tipo) {
    case 'leyendo':
      return { texto: 'Leyendo el schedule de Smoothcomp… puede tardar hasta un minuto', vieja: false };
    case 'inexistente':
      return { texto: 'Ese evento no existe', vieja: true };
    case 'error':
      // Los datos de antes siguen en pantalla: sin su edad parecerían frescos.
      return {
        texto: situacion.mensaje + (datos ? ` · últimos datos ${hace(datos.fetchedAt, ahora)}` : ''),
        vieja: true,
      };
    case 'cargando':
      return { texto: 'Cargando…', vieja: false };
    case 'ok':
      break;
  }
  if (!datos) return { texto: 'Cargando…', vieja: false };

  const total = `${datos.matches.length} combates · ${datos.athletes.length} atletas`;
  const antiguedad = ahora - new Date(datos.fetchedAt).getTime();

  if (sinSchedule(datos)) {
    return { texto: 'Schedule sin publicar · se vuelve a comprobar solo', vieja: false };
  }
  if (datos.stale) {
    // El servidor vive pero Smoothcomp le falla: él mismo lo marcó.
    return { texto: `⚠ Datos sin actualizar desde ${hora(datos.staleSince)} · ${total}`, vieja: true };
  }
  if (antiguedad > LIMITE_SIN_REFRESCO_MS) {
    // Nadie está generando datos. Es distinto de `stale`, que lo pone el propio
    // servidor: aquí puede que ni esté corriendo, y callarse haría creer que todo
    // va bien mientras la web enseña una foto vieja.
    return {
      texto: `⚠ Sin actualizarse desde ${hace(datos.fetchedAt, ahora)}`
        + (esPanel && modoEstatico ? ' — ¿está corriendo el scraper?' : '') + ` · ${total}`,
      vieja: true,
    };
  }
  return { texto: `Actualizado ${hace(datos.fetchedAt, ahora)} · ${total}`, vieja: false };
}

/* ---------- Combates ---------- */
export function combatesDe(atleta: Atleta, porId: ReadonlyMap<string, Combate>): Combate[] {
  return atleta.matchIds.map((id) => porId.get(id)).filter((c): c is Combate => !!c);
}

// Un segundo atleta entra en «Próximo combate» si le toca como mucho una hora después del primero.
export const VENTANA_PROXIMOS_MS = 60 * 60 * 1000;

export interface Proximo { atleta: Atleta; combate: Combate }

/**
 * Qué enseñar en «Próximo combate»: el pendiente que toca antes y, si otro atleta tiene el suyo a
 * una hora o menos de ese, también ese. Entre 0 y 2. Los combates sin hora quedan detrás de todos
 * y nunca valen como segundo; un combate entre dos atletas seguidos cuenta una sola vez.
 */
export function proximosCombates(atletas: readonly Atleta[], porId: ReadonlyMap<string, Combate>): Proximo[] {
  // `inicio` es Infinity cuando no hay hora (o no se entiende): así quedan al final al ordenar.
  const pendientes: Array<Proximo & { inicio: number }> = [];
  const vistos = new Set<string>();
  for (const atleta of atletas) {
    for (const combate of combatesDe(atleta, porId)) {
      if (combate.state === 'finished' || vistos.has(combate.id)) continue;
      vistos.add(combate.id);
      const inicio = combate.estimatedStart ? Date.parse(combate.estimatedStart) : NaN;
      pendientes.push({ atleta, combate, inicio: Number.isNaN(inicio) ? Infinity : inicio });
    }
  }
  // No se resta (Infinity - Infinity daría NaN): se comparan. El orden es estable.
  pendientes.sort((x, y) => (x.inicio === y.inicio ? 0 : x.inicio < y.inicio ? -1 : 1));

  const primero = pendientes[0];
  if (!primero) return [];
  if (primero.inicio === Infinity) return [primero];
  const segundo = pendientes.find((p) =>
    p.atleta.id !== primero.atleta.id && p.inicio - primero.inicio <= VENTANA_PROXIMOS_MS);
  return segundo ? [primero, segundo] : [primero];
}

// Se compara por athleteId, no por inscripción: la misma persona tiene un
// event_registration_id distinto en cada uno de los eventos en los que compite.
export function rivalDe(combate: Combate, athleteId: string) {
  return combate.sides.find((s) => s.athleteId !== athleteId) ?? null;
}

export function resultadoDe(combate: Combate, athleteId: string): ResultadoCombate {
  if (combate.state === 'running') return { texto: 'EN CURSO', tono: 'vivo' };
  if (combate.state !== 'finished') return { texto: 'Pendiente' };

  const yo = combate.sides.find((s) => s.athleteId === athleteId);
  if (!yo) return { texto: 'Terminado' };
  const modo = combate.wonBy ? ` · ${combate.wonBy}` : '';
  return yo.isWinner
    ? { texto: `Ganó${modo}`, tono: 'ganado' }
    : { texto: `Perdió${modo}`, tono: 'perdido' };
}

/** Un combate visto desde un atleta: contra quién, y cómo va. */
export function filaDeAtleta(combate: Combate, athleteId: string): FilaCombateProps {
  const rival = rivalDe(combate, athleteId);
  return {
    id: combate.id,
    hora: hora(combate.estimatedStart),
    titulo: `vs ${rival ? (rival.name ?? '') : 'Por determinar'}`,
    dia: combate.day ? diaCorto(combate.day) : undefined,
    evento: combate.eventLabel || undefined,
    detalle: `${combate.round ? `${combate.round} · ` : ''}${combate.mat || ''}`,
    resultado: resultadoDe(combate, athleteId),
  };
}

/** Un combate visto desde un tatami: quiénes pelean. */
export function filaDeTatami(combate: Combate): FilaCombateProps {
  return {
    id: combate.id,
    hora: hora(combate.estimatedStart),
    titulo: combate.sides.map((s) => s.name).join(' vs ') || 'Por determinar',
    dia: combate.day ? diaCorto(combate.day) : undefined,
    evento: combate.eventLabel || undefined,
    detalle: combate.category.raw || '',
    resultado: combate.state === 'running' ? { texto: 'EN CURSO', tono: 'vivo' } : undefined,
  };
}

// Enlace a la llave en Smoothcomp. Con más de un cuadro (Gi y No-Gi) se
// distingue por categoría, que si no no se sabe cuál es cuál.
export function llavesDe(atleta: Atleta, { conCategoria = false } = {}): Llave[] {
  const cuadros = atleta.brackets || [];
  return cuadros.map((b) => ({
    url: b.url,
    texto: (conCategoria || cuadros.length > 1) && b.category
      ? `${b.eventLabel ? `${b.eventLabel} · ` : ''}${b.category}`
      : 'Ver llave',
  }));
}
