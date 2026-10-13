import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Datos } from '../tipos';
import { informarError } from './informes';
import {
  EDAD_SOSPECHOSA_MS, ESPERA_CARGANDO_MS, ESPERA_REINTENTO_MS, ESPERA_REVALIDAR_MS, MAX_REVALIDACIONES,
  REFRESCO_MS, usarSondeoEvento,
} from './usarSondeoEvento';
import { ErrorDatos } from './validar';

// Lo que se manda al servidor se comprueba aparte (informes.test.ts): aquí solo si se llama.
vi.mock('./informes', () => ({ informarError: vi.fn() }));

const AHORA = new Date('2026-10-17T10:00:00Z').getTime();

function datos(extra: Partial<Datos> = {}): Datos {
  return {
    events: [{ id: '33588', label: null, name: 'Open Madrid', published: true }],
    fetchedAt: new Date(AHORA).toISOString(),
    stale: false, staleSince: null, mats: [], matches: [], athletes: [],
    ...extra,
  };
}

/** Una respuesta de fetch mínima: lo que usa el hook (status, ok, headers.get, json). */
function respuesta(status: number, cuerpo: unknown = {}, etag?: string) {
  return {
    status,
    ok: status >= 200 && status < 300,
    headers: { get: (n: string) => (n.toLowerCase() === 'etag' ? etag ?? null : null) },
    json: async () => cuerpo,
  };
}

let oculto = false;
const fetchSimulado = vi.fn();

function ponerOculto(valor: boolean) {
  oculto = valor;
  document.dispatchEvent(new Event('visibilitychange'));
}

async function pasar(ms: number) {
  await act(async () => { await vi.advanceTimersByTimeAsync(ms); });
}

function montar(opciones: { ids?: string | null; modoEstatico?: boolean } = {}) {
  return renderHook(() => usarSondeoEvento({
    ids: opciones.ids === undefined ? '33588' : opciones.ids,
    modoEstatico: opciones.modoEstatico ?? false,
  }));
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(AHORA);
  oculto = false;
  Object.defineProperty(document, 'hidden', { configurable: true, get: () => oculto });
  fetchSimulado.mockReset();
  vi.mocked(informarError).mockClear();
  vi.stubGlobal('fetch', fetchSimulado);
});

describe('usarSondeoEvento', () => {
  it('empieza cargando y pide los datos del evento a la dirección relativa de la API', async () => {
    fetchSimulado.mockResolvedValue(respuesta(200, datos(), '"v1"'));
    const { result } = montar();
    expect(result.current.situacion).toEqual({ tipo: 'cargando' });
    expect(result.current.datos).toBeNull();

    await pasar(0);
    expect(fetchSimulado).toHaveBeenCalledWith('api/events/33588/data', expect.objectContaining({ cache: 'no-store' }));
    expect(result.current.situacion).toEqual({ tipo: 'ok' });
    expect(result.current.datos?.events[0]?.name).toBe('Open Madrid');
  });

  it('202: el servidor está leyendo el evento; se reintenta a los 3 s y llegan los datos', async () => {
    fetchSimulado
      .mockResolvedValueOnce(respuesta(202, { events: [{ id: '33588', title: 'Open Madrid 2026' }] }))
      .mockResolvedValueOnce(respuesta(200, datos(), '"v1"'));
    const { result } = montar();

    await pasar(0);
    expect(result.current.situacion).toEqual({ tipo: 'leyendo', titulo: 'Open Madrid 2026' });
    expect(result.current.datos).toBeNull();

    await pasar(ESPERA_CARGANDO_MS - 1);
    expect(fetchSimulado).toHaveBeenCalledTimes(1);
    await pasar(1);
    expect(fetchSimulado).toHaveBeenCalledTimes(2);
    expect(result.current.situacion).toEqual({ tipo: 'ok' });
    expect(result.current.datos).not.toBeNull();
  });

  it('refresca cada 30 s mandando el ETag, y un 304 conserva los datos sin tocarlos', async () => {
    fetchSimulado
      .mockResolvedValueOnce(respuesta(200, datos(), '"abc"'))
      .mockResolvedValueOnce(respuesta(304));
    const { result } = montar();
    await pasar(0);
    const primeros = result.current.datos;

    await pasar(REFRESCO_MS);
    expect(fetchSimulado).toHaveBeenCalledTimes(2);
    expect(fetchSimulado.mock.calls[1]?.[1].headers).toEqual({ 'If-None-Match': '"abc"' });
    expect(result.current.datos).toBe(primeros);
    expect(result.current.situacion).toEqual({ tipo: 'ok' });
  });

  it('404: el evento no existe y se deja de preguntar', async () => {
    fetchSimulado.mockResolvedValue(respuesta(404, { error: 'Ese evento no existe en Smoothcomp' }));
    const { result } = montar();
    await pasar(0);
    expect(result.current.situacion).toEqual({ tipo: 'inexistente', mensaje: 'Ese evento no existe en Smoothcomp' });

    await pasar(10 * 60_000);
    expect(fetchSimulado).toHaveBeenCalledTimes(1);
  });

  it('un error del servidor se cuenta y se reintenta a los 10 s', async () => {
    fetchSimulado
      .mockResolvedValueOnce(respuesta(502, { error: 'Smoothcomp no responde' }))
      .mockResolvedValueOnce(respuesta(200, datos(), '"v1"'));
    const { result } = montar();
    await pasar(0);
    expect(result.current.situacion).toEqual({ tipo: 'error', mensaje: 'No se pudo leer el evento (Smoothcomp no responde)' });

    await pasar(ESPERA_REINTENTO_MS);
    expect(result.current.situacion).toEqual({ tipo: 'ok' });
  });

  it('sin red es otro mensaje, y también se reintenta', async () => {
    fetchSimulado.mockRejectedValueOnce(new Error('Failed to fetch')).mockResolvedValueOnce(respuesta(200, datos()));
    const { result } = montar();
    await pasar(0);
    expect(result.current.situacion).toEqual({ tipo: 'error', mensaje: 'Sin conexión con los datos (Failed to fetch)' });
    await pasar(ESPERA_REINTENTO_MS);
    expect(result.current.situacion).toEqual({ tipo: 'ok' });
    expect(informarError).not.toHaveBeenCalled();     // la red y el servidor no son fallos de la web
  });

  it('un 200 que no es JSON (una página HTML) no se hace pasar por falta de conexión', async () => {
    const html = { ...respuesta(200), json: async () => { throw new SyntaxError("Unexpected token '<'"); } };
    fetchSimulado.mockResolvedValueOnce(html).mockResolvedValueOnce(respuesta(200, datos(), '"v1"'));
    const { result } = montar();
    await pasar(0);
    expect(result.current.situacion).toEqual({
      tipo: 'error', mensaje: 'Respuesta inesperada del servidor (la respuesta no es JSON)',
    });
    expect(result.current.datos).toBeNull();
    expect(informarError).toHaveBeenCalledWith('datos', expect.any(ErrorDatos));

    await pasar(ESPERA_REINTENTO_MS);                 // se reintenta, como cualquier error
    expect(result.current.situacion).toEqual({ tipo: 'ok' });
    expect(result.current.datos).not.toBeNull();
  });

  it('unos datos con otra forma no llegan a pintarse: se cuentan como contrato roto', async () => {
    fetchSimulado.mockResolvedValueOnce(respuesta(200, { events: [], fetchedAt: new Date(AHORA).toISOString() }));
    const { result } = montar();
    await pasar(0);
    expect(result.current.datos).toBeNull();
    expect(result.current.situacion).toEqual({
      tipo: 'error',
      mensaje: 'Respuesta inesperada del servidor (la respuesta no tiene la forma esperada: falta la lista «matches»)',
    });
    expect(informarError).toHaveBeenCalledTimes(1);
  });

  it('unos datos malos no tiran los buenos de antes: siguen en pantalla, con su edad', async () => {
    fetchSimulado
      .mockResolvedValueOnce(respuesta(200, datos(), '"v1"'))
      .mockResolvedValueOnce(respuesta(200, { ...datos(), fetchedAt: 'ayer' }, '"v2"'));
    const { result } = montar();
    await pasar(0);
    const buenos = result.current.datos;
    expect(buenos).not.toBeNull();

    await pasar(REFRESCO_MS);
    expect(result.current.situacion.tipo).toBe('error');
    expect(result.current.datos).toBe(buenos);
  });

  it('modo estático: un 404 de data.json es «aún no publicado» y se sigue esperando', async () => {
    fetchSimulado
      .mockResolvedValueOnce(respuesta(404, {}))
      .mockResolvedValueOnce(respuesta(404, {}))
      .mockResolvedValueOnce(respuesta(200, datos(), '"v1"'));
    const { result } = montar({ ids: null, modoEstatico: true });
    await pasar(0);
    expect(result.current.situacion).toEqual({ tipo: 'error', mensaje: 'Aún no hay datos publicados' });

    await pasar(ESPERA_REINTENTO_MS);
    expect(fetchSimulado).toHaveBeenCalledTimes(2);
    expect(result.current.situacion.tipo).toBe('error');

    await pasar(ESPERA_REINTENTO_MS);                 // el scraper publica por fin
    expect(result.current.situacion).toEqual({ tipo: 'ok' });
    expect(result.current.datos).not.toBeNull();
  });

  it('datos más viejos que un ciclo: vuelve a preguntar enseguida, como mucho 3 veces, y luego a su ritmo', async () => {
    const viejos = datos({ fetchedAt: new Date(AHORA - EDAD_SOSPECHOSA_MS - 60_000).toISOString() });
    fetchSimulado.mockResolvedValue(respuesta(200, viejos, '"v1"'));
    montar();
    await pasar(0);
    expect(fetchSimulado).toHaveBeenCalledTimes(1);

    await pasar(ESPERA_REVALIDAR_MS * MAX_REVALIDACIONES);
    expect(fetchSimulado).toHaveBeenCalledTimes(1 + MAX_REVALIDACIONES);

    // La cuarta lectura ya no se revalida: espera el ciclo normal.
    await pasar(REFRESCO_MS - 1);
    expect(fetchSimulado).toHaveBeenCalledTimes(1 + MAX_REVALIDACIONES);
    await pasar(1);
    expect(fetchSimulado).toHaveBeenCalledTimes(2 + MAX_REVALIDACIONES);
  });

  it('con la pestaña oculta no sondea; al volver a verse pregunta ya', async () => {
    fetchSimulado.mockResolvedValue(respuesta(200, datos(), '"v1"'));
    montar();
    await pasar(0);
    expect(fetchSimulado).toHaveBeenCalledTimes(1);

    ponerOculto(true);
    await pasar(REFRESCO_MS * 3);
    expect(fetchSimulado).toHaveBeenCalledTimes(1);

    await act(async () => { ponerOculto(false); });
    await pasar(0);
    expect(fetchSimulado).toHaveBeenCalledTimes(2);
  });

  it('recargar olvida el ETag y pregunta ya', async () => {
    fetchSimulado.mockResolvedValue(respuesta(200, datos(), '"abc"'));
    const { result } = montar();
    await pasar(0);

    await act(async () => { result.current.recargar(); });
    await pasar(0);
    expect(fetchSimulado).toHaveBeenCalledTimes(2);
    expect(fetchSimulado.mock.calls[1]?.[1].headers).toEqual({});
  });

  it('al desmontar deja de preguntar y una respuesta que llega tarde no pinta nada', async () => {
    let resolver!: (r: ReturnType<typeof respuesta>) => void;
    fetchSimulado.mockReturnValueOnce(new Promise((r) => { resolver = r; }));
    const { result, unmount } = montar();
    await pasar(0);
    unmount();

    await act(async () => { resolver(respuesta(200, datos(), '"v1"')); });
    await pasar(REFRESCO_MS * 2);
    expect(result.current.datos).toBeNull();
    expect(fetchSimulado).toHaveBeenCalledTimes(1);
  });

  it('cambiar de evento empieza de cero', async () => {
    fetchSimulado.mockResolvedValue(respuesta(200, datos(), '"v1"'));
    const { result, rerender } = renderHook(
      ({ ids }) => usarSondeoEvento({ ids, modoEstatico: false }), { initialProps: { ids: '1535' } });
    await pasar(0);
    expect(result.current.datos).not.toBeNull();

    fetchSimulado.mockReturnValue(new Promise(() => {}));
    rerender({ ids: '1526' });
    expect(result.current.datos).toBeNull();
    expect(result.current.situacion).toEqual({ tipo: 'cargando' });
    expect(fetchSimulado).toHaveBeenLastCalledWith('api/events/1526/data', expect.anything());
  });

  it('modo estático: lee data.json y no revalida por datos viejos', async () => {
    const viejos = datos({ fetchedAt: new Date(AHORA - 60 * 60_000).toISOString() });
    fetchSimulado.mockResolvedValue(respuesta(200, viejos));
    montar({ ids: null, modoEstatico: true });
    await pasar(0);
    expect(fetchSimulado).toHaveBeenCalledWith('data.json', expect.anything());

    await pasar(REFRESCO_MS - 1);
    expect(fetchSimulado).toHaveBeenCalledTimes(1);
    await pasar(1);
    expect(fetchSimulado).toHaveBeenCalledTimes(2);
  });

  it('el «hace X» se actualiza solo cada 10 s', async () => {
    fetchSimulado.mockResolvedValue(respuesta(200, datos(), '"v1"'));
    const { result } = montar();
    await pasar(0);
    const antes = result.current.ahora;
    await pasar(10_000);
    expect(result.current.ahora).toBeGreaterThanOrEqual(antes + 10_000);
  });
});
