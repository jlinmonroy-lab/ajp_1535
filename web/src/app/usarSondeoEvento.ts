/* Descarga los datos de un evento y los mantiene al día.
 *
 * Es el ciclo de siempre, con las mismas esperas: pregunta al servidor con el ETag (un ciclo
 * sin cambios no descarga nada), reintenta si falla, y no gasta datos con la pestaña oculta.
 * Si no hay servidor (la web servida como ficheros estáticos, p. ej. en GitHub Pages), lee
 * `data.json`: un único evento.
 *
 * La máquina de estados vive en el cierre del efecto, no en el estado de React: una respuesta
 * que llega tarde de un evento ya cerrado no puede pintar nada (el contador `generacion`).
 */
import { useEffect, useRef, useState } from 'react';
import type { Datos } from '../tipos';
import { ErrorApi, mensajeDeError, urlDatos } from './api';
import { informarError } from './informes';
import { ErrorDatos, problemaConDatos } from './validar';

export const REFRESCO_MS = 30000;
export const ESPERA_CARGANDO_MS = 3000;     // mientras el servidor lee un evento por primera vez
export const ESPERA_REINTENTO_MS = 10000;   // tras un error del servidor o de Smoothcomp
// El servidor contesta con lo que tiene y refresca detrás. Si lo recibido es más
// viejo que un ciclo de refresco (75 s) con margen, quien abre un evento que
// nadie miraba vería datos viejos hasta el siguiente sondeo: se vuelve a
// preguntar enseguida, unas pocas veces.
export const EDAD_SOSPECHOSA_MS = 100 * 1000;
export const ESPERA_REVALIDAR_MS = 5000;
export const MAX_REVALIDACIONES = 3;
// El "hace X" envejece solo; oculta no hay nada que repintar.
export const TIC_ESTADO_MS = 10000;

/** Qué pasó en el último ciclo. Los datos (si ya los hay) se conservan aparte. */
export type Situacion =
  | { tipo: 'cargando' }
  /** El servidor está leyendo el evento de Smoothcomp por primera vez. `titulo` si ya lo sabe. */
  | { tipo: 'leyendo'; titulo: string | null }
  | { tipo: 'ok' }
  | { tipo: 'inexistente'; mensaje: string }
  /** No se pudo leer; se reintenta solo. `mensaje` ya viene redactado para enseñarlo. */
  | { tipo: 'error'; mensaje: string };

export interface OpcionesSondeo {
  /** Ids del evento ("33588" o "1535,1526"). Null en el modo estático. */
  ids: string | null;
  modoEstatico: boolean;
}

// Qué decir de un ciclo que falló. Tres casos con remedios distintos: el servidor contesta
// con un error, contesta algo que no se puede pintar, o no contesta.
function textoDeError(e: unknown, modoEstatico: boolean): string {
  const mensaje = e instanceof Error ? e.message : String(e);
  if (e instanceof ErrorDatos) return `Respuesta inesperada del servidor (${mensaje})`;
  // Sin servidor, un 404 de data.json es «el scraper aún no ha publicado», no «no existe».
  if (e instanceof ErrorApi && e.estado === 404 && modoEstatico) return 'Aún no hay datos publicados';
  if (e instanceof ErrorApi) return `No se pudo leer el evento (${mensaje})`;
  return `Sin conexión con los datos (${mensaje})`;
}

export interface Sondeo {
  datos: Datos | null;
  situacion: Situacion;
  /** Se actualiza con cada ciclo y cada 10 s: lo que hace envejecer el «hace X». */
  ahora: number;
  /** Botón de actualizar: olvida el ETag y pregunta ya. */
  recargar: () => void;
}

export function usarSondeoEvento({ ids, modoEstatico }: OpcionesSondeo): Sondeo {
  const [datos, setDatos] = useState<Datos | null>(null);
  const [situacion, setSituacion] = useState<Situacion>({ tipo: 'cargando' });
  const [ahora, setAhora] = useState(() => Date.now());
  const reiniciarRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    setDatos(null);
    setSituacion({ tipo: 'cargando' });
    setAhora(Date.now());

    let generacion = 0;           // cada recarga/cierre la sube e invalida lo que estuviera en vuelo
    let etag: string | null = null;
    let temporizador: ReturnType<typeof setTimeout> | undefined;
    let sondeoPendiente = false;  // tocaba sondear pero la pestaña estaba oculta
    let revalidaciones = 0;       // sondeos rápidos seguidos por datos viejos
    let ultimos: Datos | null = null;
    const url = urlDatos(modoEstatico, ids);

    // Cuánto esperar tras recibir datos válidos.
    function esperaTrasDatos(): number {
      const viejos = !modoEstatico && ultimos && !ultimos.stale
        && Date.now() - new Date(ultimos.fetchedAt).getTime() > EDAD_SOSPECHOSA_MS;
      if (viejos && revalidaciones < MAX_REVALIDACIONES) {
        revalidaciones += 1;
        return ESPERA_REVALIDAR_MS;
      }
      revalidaciones = 0;
      return REFRESCO_MS;
    }

    // Cuenta de lo que pasa en cada ciclo: devuelve cuánto esperar hasta el siguiente,
    // o null si no hay nada más que esperar (evento inexistente, o ya se cambió de pantalla).
    async function cargar(): Promise<number | null> {
      const miGeneracion = generacion;
      try {
        const cabeceras: Record<string, string> = etag ? { 'If-None-Match': etag } : {};
        const resp = await fetch(url, { cache: 'no-store', headers: cabeceras });
        if (miGeneracion !== generacion) return null;

        if (resp.status === 304) {
          setSituacion({ tipo: 'ok' });
          setAhora(Date.now());
          return esperaTrasDatos();
        }

        if (resp.status === 202) {
          const info = await resp.json();
          if (miGeneracion !== generacion) return null;
          const conocido = (info.events || []).find((e: { title?: string }) => e.title);
          setSituacion({ tipo: 'leyendo', titulo: conocido ? conocido.title : null });
          return ESPERA_CARGANDO_MS;
        }

        if (!resp.ok) throw new ErrorApi(resp.status, await mensajeDeError(resp));

        const nuevaEtag = resp.headers.get('ETag');
        let crudos: unknown;
        try {
          crudos = await resp.json();
        } catch {
          // Un 200 que no es JSON: un portal cautivo, o un alojamiento que contesta su página para todo.
          throw new ErrorDatos('la respuesta no es JSON');
        }
        if (miGeneracion !== generacion) return null;
        const problema = problemaConDatos(crudos);
        if (problema) throw new ErrorDatos(`la respuesta no tiene la forma esperada: ${problema}`);
        const nuevos = crudos as Datos;
        etag = nuevaEtag;
        ultimos = nuevos;
        setDatos(nuevos);
        setSituacion({ tipo: 'ok' });
        setAhora(Date.now());
        return esperaTrasDatos();
      } catch (e) {
        if (miGeneracion !== generacion) return null;
        if (e instanceof ErrorApi && e.estado === 404 && !modoEstatico) {
          setSituacion({ tipo: 'inexistente', mensaje: e.message });
          return null;
        }
        // Que el servidor mande algo que la web no entiende es un fallo nuestro (de contrato
        // entre las dos mitades), no de la red: se cuenta al servidor para enterarse.
        if (e instanceof ErrorDatos) informarError('datos', e);
        setSituacion({ tipo: 'error', mensaje: textoDeError(e, modoEstatico) });
        return ESPERA_REINTENTO_MS;
      }
    }

    async function ciclo() {
      const miGeneracion = generacion;
      const espera = await cargar();
      if (espera == null || miGeneracion !== generacion) return;
      temporizador = setTimeout(sondear, espera);
    }

    // Toca volver a preguntar. Un móvil en el bolsillo no necesita datos nuevos, y con
    // datos móviles cada sondeo cuesta: con la pestaña oculta no se sondea, y al volver
    // a verse se pregunta enseguida (ver `visibilitychange`).
    function sondear() {
      if (document.hidden) {
        sondeoPendiente = true;
        return;
      }
      sondeoPendiente = false;
      void ciclo();
    }

    function reiniciar() {
      generacion += 1;
      clearTimeout(temporizador);
      sondeoPendiente = false;
      etag = null;
      void ciclo();
    }

    // Al volver a ver la pestaña: si se dejó de sondear mientras estaba oculta, se pregunta
    // ya (con el ETag, así que si no hay cambios no se descarga nada), y el "hace X" se pone al día.
    function alCambiarVisibilidad() {
      if (document.hidden) return;
      if (sondeoPendiente) {
        sondeoPendiente = false;
        clearTimeout(temporizador);
        void ciclo();
      }
      setAhora(Date.now());
    }

    document.addEventListener('visibilitychange', alCambiarVisibilidad);
    const tic = setInterval(() => { if (!document.hidden) setAhora(Date.now()); }, TIC_ESTADO_MS);
    reiniciarRef.current = reiniciar;
    void ciclo();

    return () => {
      generacion += 1;
      clearTimeout(temporizador);
      clearInterval(tic);
      document.removeEventListener('visibilitychange', alCambiarVisibilidad);
      reiniciarRef.current = null;
    };
  }, [ids, modoEstatico]);

  return { datos, situacion, ahora, recargar: () => reiniciarRef.current?.() };
}
