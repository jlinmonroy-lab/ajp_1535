/* Cuenta al servidor lo que le falla al usuario en su navegador.
 *
 * Sin esto, un fallo en el móvil de alguien (una pantalla en blanco, unos datos que no se
 * pueden pintar) no deja rastro en ningún sitio: el servidor ve peticiones normales. Los
 * informes van a `POST api/client-error`, que los pone en su registro; sin servidor (la web
 * como ficheros estáticos) la petición falla y no pasa nada.
 *
 * Nada de aquí puede lanzar: se usa dentro de los manejadores de errores, y un fallo del
 * informador dentro de uno sería un bucle.
 */
import { BUILD } from './version';

export type TipoInforme = 'render' | 'js' | 'promesa' | 'datos';

export const URL_INFORMES = 'api/client-error';
/** Por carga de página: un error en bucle no debe convertirse en cientos de peticiones. */
export const MAX_INFORMES = 5;

// Avisos del navegador y de extensiones, sin nada que arreglar aquí.
const RUIDO = /^(ResizeObserver loop|Script error\.?$)/;

const enviados = new Set<string>();

/** Para las pruebas: empezar de cero. */
export function olvidarInformes(): void {
  enviados.clear();
}

export function informarError(tipo: TipoInforme, error: unknown, contexto?: string): void {
  try {
    const err = error instanceof Error ? error : null;
    const mensaje = err ? `${err.name}: ${err.message}` : String(error);
    if (RUIDO.test(err ? err.message : mensaje)) return;

    const clave = `${tipo}|${mensaje}`;
    if (enviados.has(clave) || enviados.size >= MAX_INFORMES) return;
    enviados.add(clave);

    // El contexto (en `render`, la pila de componentes) va primero: dice más que la de React.
    const pila = [contexto?.trim(), err?.stack].filter(Boolean).join('\n');
    const cuerpo = JSON.stringify({
      tipo,
      mensaje: mensaje.slice(0, 300),
      pila: pila.slice(0, 1500),
      ruta: (location.pathname + location.hash).slice(0, 200),   // sin query: puede llevar lo buscado
      build: BUILD,
      ua: navigator.userAgent.slice(0, 150),
    });
    void Promise.resolve(fetch(URL_INFORMES, {
      method: 'POST',
      keepalive: true,                     // sobrevive a una recarga o a cerrar la pestaña
      headers: { 'Content-Type': 'application/json' },
      body: cuerpo,
    })).catch(() => { /* sin servidor, o sin red: no hay a quién contárselo */ });
  } catch { /* informar nunca debe romper nada */ }
}

/** Engancha los errores que nadie atrapa. Devuelve la función que los desengancha. */
export function iniciarInformes(destino: Window = window): () => void {
  const alError = (e: ErrorEvent) => informarError('js', e.error ?? e.message);
  const alRechazo = (e: PromiseRejectionEvent) => informarError('promesa', e.reason);
  destino.addEventListener('error', alError);
  destino.addEventListener('unhandledrejection', alRechazo);
  return () => {
    destino.removeEventListener('error', alError);
    destino.removeEventListener('unhandledrejection', alRechazo);
  };
}
