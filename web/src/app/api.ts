/* Todo lo que la web pregunta al servidor. Las direcciones son relativas a propósito
   (`api/config`, no `/api/config`): la web funciona igual si cuelga de una subcarpeta. */
import type { ConfigWeb, GrupoPanel } from '../tipos';
import { borrarLocal, leerLocal } from './util';

export class ErrorApi extends Error {
  estado: number;

  constructor(estado: number, mensaje: string) {
    super(mensaje);
    this.estado = estado;
  }
}

// Las respuestas de error de la API traen {error: "..."}; esto lo saca si está.
export async function mensajeDeError(resp: Response): Promise<string> {
  try {
    const cuerpo = await resp.json();
    if (cuerpo && cuerpo.error) return String(cuerpo.error);
  } catch { /* no era JSON */ }
  return `HTTP ${resp.status}`;
}

/* ---------- Direcciones ---------- */
export const urlDatos = (modoEstatico: boolean, ids: string | null): string =>
  (modoEstatico ? 'data.json' : `api/events/${ids}/data`);

export const urlGrupo = (modoEstatico: boolean, ids: string | null): string =>
  (modoEstatico ? '/api/grupo' : `api/events/${ids}/grupo`);

/* ---------- Clave de administrador ---------- */
// Con ADMIN_TOKEN en el servidor, la clave guardada en este dispositivo desbloquea
// "Seguir para todos" sin estar delante del equipo. Viaja en una cabecera, nunca en la URL.
export const CLAVE_ADMIN = 'sbjj:admin';

export const claveAdmin = (): string => leerLocal<string>(CLAVE_ADMIN, '');

export const cabecerasAdmin = (): Record<string, string> => {
  const clave = claveAdmin();
  return clave ? { 'X-Admin-Token': clave } : {};
};

// true si el servidor la acepta, false si la rechaza, null si no se pudo saber (sin red).
export async function comprobarAdmin(clave: string): Promise<boolean | null> {
  try {
    const resp = await fetch('api/admin', { cache: 'no-store', headers: { 'X-Admin-Token': clave } });
    if (resp.ok) return true;
    if (resp.status === 403) return false;
  } catch { /* sin red */ }
  return null;
}

/* ---------- Lista del grupo ---------- */
export type CuerpoGrupo =
  | { accion: 'añadir'; name: string; club?: string; id?: string }
  | { accion: 'quitar'; name: string; id: string };

// Lo que devuelve el servidor tras cada cambio manda sobre los datos, que pueden tardar
// un poco en enterarse.
export async function enviarGrupo(url: string, cuerpo: CuerpoGrupo): Promise<GrupoPanel> {
  const resp = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...cabecerasAdmin() },
    body: JSON.stringify(cuerpo),
  });
  if (!resp.ok) throw new Error(await mensajeDeError(resp));
  return resp.json();
}

export async function leerGrupo(url: string): Promise<GrupoPanel | null> {
  try {
    const resp = await fetch(url, { cache: 'no-store' });
    return resp.ok ? await resp.json() : null;
  } catch {
    return null;   // sin panel: se usa la lista de los datos
  }
}

/* ---------- Arranque ---------- */
export const ES_LOCAL = ['localhost', '127.0.0.1'].includes(location.hostname);

export interface Arranque {
  marca: ConfigWeb;
  /** Sin servidor: la web se sirve como ficheros estáticos y hay un solo evento (data.json). */
  modoEstatico: boolean;
  /** Puede cambiar la lista del grupo: el equipo del servidor, o una clave de administrador válida. */
  esPanel: boolean;
}

const MARCA_POR_DEFECTO: ConfigWeb = { teamName: 'FC Team', logo: 'img/logo.png' };
const ESPERA_MAX_ARRANQUE_MS = 10000;

function esperar(ms: number, señal?: AbortSignal): Promise<void> {
  return new Promise((resolver, rechazar) => {
    señal?.throwIfAborted();
    const temporizador = setTimeout(resolver, ms);
    señal?.addEventListener('abort', () => { clearTimeout(temporizador); rechazar(señal.reason); }, { once: true });
  });
}

/* Pregunta al servidor quién es. `null` si no hay servidor: la web se sirve como ficheros
   estáticos (GitHub Pages, el panel antiguo) y ahí `api/config` es un 404, o una página que
   no es JSON. Pero un servidor que existe y ahora no contesta bien (se está desplegando, un
   5xx, sin red un momento) no es «sin servidor»: caer al modo estático dejaría la web rota
   hasta recargar. Se insiste, cada vez más despacio, hasta que conteste. */
async function leerConfig(alReintentar?: (intento: number) => void, señal?: AbortSignal): Promise<ConfigWeb | null> {
  for (let intento = 1; ; intento += 1) {
    señal?.throwIfAborted();
    try {
      const resp = await fetch('api/config', { cache: 'no-store' });
      if (resp.ok) {
        try { return await resp.json(); } catch { return null; }
      }
      if (resp.status < 500 && resp.status !== 429) return null;   // 404, 403…: aquí no hay API
    } catch { /* sin red, o el servidor aún no escucha */ }
    alReintentar?.(intento);
    await esperar(Math.min(1000 * 2 ** (intento - 1), ESPERA_MAX_ARRANQUE_MS), señal);
  }
}

export interface OpcionesArranque {
  /** Cada vez que el servidor no contesta bien y se va a volver a probar, con el número de intento. */
  alReintentar?: (intento: number) => void;
  /** Para dejar de insistir (la web se cerró). `arrancar` rechaza con el motivo del aborto. */
  señal?: AbortSignal;
}

export async function arrancar({ alReintentar, señal }: OpcionesArranque = {}): Promise<Arranque> {
  const config = await leerConfig(alReintentar, señal);
  const modoEstatico = config === null;     // sin servidor: un solo evento, leído de data.json
  const marca = { ...MARCA_POR_DEFECTO, ...(config ?? {}) };

  // En el equipo del servidor el panel ya está abierto: no hace falta clave.
  let esPanel = ES_LOCAL;
  if (!modoEstatico && marca.admin && !ES_LOCAL && claveAdmin()) {
    const valida = await comprobarAdmin(claveAdmin());
    if (valida === false) borrarLocal(CLAVE_ADMIN);           // cambiada en el servidor
    esPanel = valida !== false;                               // sin red, se fía de la guardada
  }
  return { marca, modoEstatico, esPanel };
}
