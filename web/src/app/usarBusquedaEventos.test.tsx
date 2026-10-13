import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { EventoBuscado } from '../tipos';
import { ESPERA_ESCRITURA_MS, usarBusquedaEventos } from './usarBusquedaEventos';

const evento = (id: string, extra: Partial<EventoBuscado> = {}): EventoBuscado => ({
  id, title: `Evento ${id}`, url: null, startdate: null, enddate: null, city: null, country: null, ...extra,
});

function respuesta(events: EventoBuscado[], extra: { hasMore?: boolean; stale?: boolean } = {}) {
  return { ok: true, status: 200, json: async () => ({ events, page: 1, hasMore: false, stale: false, ...extra }) };
}

const fetchSimulado = vi.fn();
const paramsDe = (llamada: number) =>
  new URLSearchParams(String(fetchSimulado.mock.calls[llamada]?.[0]).split('?')[1]);

async function pasar(ms: number) {
  await act(async () => { await vi.advanceTimersByTimeAsync(ms); });
}

beforeEach(() => {
  vi.useFakeTimers();
  fetchSimulado.mockReset();
  vi.stubGlobal('fetch', fetchSimulado);
});

describe('usarBusquedaEventos', () => {
  it('mostrar lanza la primera búsqueda: próximos y con la zona encendida', async () => {
    fetchSimulado.mockResolvedValue(respuesta([evento('1')]));
    const { result } = renderHook(() => usarBusquedaEventos('Madrid, España'));
    expect(result.current.estado).toMatchObject({ zona: 'Madrid, España', zonaActiva: true, cuando: 'upcoming' });

    await act(async () => { result.current.mostrar(); });
    await pasar(0);
    expect(fetchSimulado.mock.calls[0]?.[0]).toMatch(/^api\/events\/search\?/);
    expect(Object.fromEntries(paramsDe(0))).toEqual({ q: '', when: 'upcoming', page: '1', zona: '1' });
    expect(result.current.estado.eventos.map((e) => e.id)).toEqual(['1']);
    expect(result.current.estado.cargando).toBe(false);
  });

  it('sin zona configurada no hay chip ni parámetro zona', async () => {
    fetchSimulado.mockResolvedValue(respuesta([]));
    const { result } = renderHook(() => usarBusquedaEventos(null));
    expect(result.current.estado).toMatchObject({ zona: null, zonaActiva: false });
    await act(async () => { result.current.mostrar(); });
    await pasar(0);
    expect(paramsDe(0).has('zona')).toBe(false);
  });

  it('mostrar por segunda vez no repite la búsqueda si ya hay resultados', async () => {
    fetchSimulado.mockResolvedValue(respuesta([evento('1')]));
    const { result } = renderHook(() => usarBusquedaEventos(null));
    await act(async () => { result.current.mostrar(); });
    await pasar(0);
    await act(async () => { result.current.mostrar(); });
    await pasar(0);
    expect(fetchSimulado).toHaveBeenCalledTimes(1);
  });

  it('escribir espera 350 ms a que se pare, y solo busca una vez', async () => {
    fetchSimulado.mockResolvedValue(respuesta([]));
    const { result } = renderHook(() => usarBusquedaEventos(null));
    await act(async () => { result.current.escribir('mad'); });
    await pasar(ESPERA_ESCRITURA_MS - 100);
    await act(async () => { result.current.escribir('madrid '); });
    await pasar(ESPERA_ESCRITURA_MS - 1);
    expect(fetchSimulado).not.toHaveBeenCalled();
    await pasar(1);
    expect(fetchSimulado).toHaveBeenCalledTimes(1);
    expect(paramsDe(0).get('q')).toBe('madrid');
    expect(result.current.estado.texto).toBe('madrid ');
  });

  it('descarta la respuesta de una búsqueda que ya no es la última', async () => {
    let resolverPrimera!: (r: ReturnType<typeof respuesta>) => void;
    fetchSimulado
      .mockReturnValueOnce(new Promise((r) => { resolverPrimera = r; }))
      .mockResolvedValueOnce(respuesta([evento('2')]));
    const { result } = renderHook(() => usarBusquedaEventos(null));

    await act(async () => { result.current.escribir('uno'); result.current.enviar(); });
    await act(async () => { result.current.escribir('dos'); result.current.enviar(); });
    await pasar(0);
    expect(result.current.estado.eventos.map((e) => e.id)).toEqual(['2']);

    await act(async () => { resolverPrimera(respuesta([evento('1')])); });
    await pasar(0);
    expect(result.current.estado.eventos.map((e) => e.id)).toEqual(['2']);
    expect(result.current.estado.cargando).toBe(false);
  });

  it('cargar más añade la página siguiente sin repetir eventos', async () => {
    fetchSimulado
      .mockResolvedValueOnce(respuesta([evento('1'), evento('2')], { hasMore: true }))
      .mockResolvedValueOnce(respuesta([evento('2'), evento('3')]));
    const { result } = renderHook(() => usarBusquedaEventos(null));
    await act(async () => { result.current.mostrar(); });
    await pasar(0);
    expect(result.current.estado.hayMas).toBe(true);

    await act(async () => { result.current.cargarMas(); });
    await pasar(0);
    expect(paramsDe(1).get('page')).toBe('2');
    expect(result.current.estado.eventos.map((e) => e.id)).toEqual(['1', '2', '3']);
    expect(result.current.estado.hayMas).toBe(false);
  });

  it('si falla cargar más, la página no avanza y reintentar vuelve a pedir esa misma', async () => {
    fetchSimulado
      .mockResolvedValueOnce(respuesta([evento('1')], { hasMore: true }))
      .mockResolvedValueOnce({ ok: false, status: 502, json: async () => ({ error: 'Smoothcomp no responde' }) })
      .mockResolvedValueOnce(respuesta([evento('9')]));
    const { result } = renderHook(() => usarBusquedaEventos(null));
    await act(async () => { result.current.mostrar(); });
    await pasar(0);
    await act(async () => { result.current.cargarMas(); });
    await pasar(0);
    expect(result.current.estado.error).toBe('Smoothcomp no responde');
    expect(result.current.estado.pagina).toBe(1);

    await act(async () => { result.current.reintentar(); });
    await pasar(0);
    expect(paramsDe(2).get('page')).toBe('2');
    expect(result.current.estado.error).toBeNull();
  });

  it('quitar la zona busca en todo el mundo; cambiar de filtro reinicia la lista', async () => {
    fetchSimulado.mockResolvedValue(respuesta([evento('1')]));
    const { result } = renderHook(() => usarBusquedaEventos('Madrid, España'));
    await act(async () => { result.current.mostrar(); });
    await pasar(0);

    await act(async () => { result.current.cambiarZona(false); });
    await pasar(0);
    expect(paramsDe(1).has('zona')).toBe(false);
    expect(result.current.estado.zonaActiva).toBe(false);

    await act(async () => { result.current.cambiarCuando('past'); });
    await pasar(0);
    expect(paramsDe(2).get('when')).toBe('past');
    expect(paramsDe(2).get('page')).toBe('1');
  });

  it('no se puede encender una zona que no existe', async () => {
    fetchSimulado.mockResolvedValue(respuesta([]));
    const { result } = renderHook(() => usarBusquedaEventos(null));
    await act(async () => { result.current.cambiarZona(true); });
    await pasar(0);
    expect(result.current.estado.zonaActiva).toBe(false);
  });

  it('anota si Smoothcomp no respondió y se enseñan resultados guardados', async () => {
    fetchSimulado.mockResolvedValue(respuesta([evento('1')], { stale: true }));
    const { result } = renderHook(() => usarBusquedaEventos(null));
    await act(async () => { result.current.mostrar(); });
    await pasar(0);
    expect(result.current.estado.vieja).toBe(true);
  });
});
