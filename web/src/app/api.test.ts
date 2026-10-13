import { beforeEach, describe, expect, it, vi } from 'vitest';
import { arrancar } from './api';

/** Una respuesta de fetch mínima. Sin `cuerpo`, `json()` falla como con una página HTML. */
function respuesta(status: number, cuerpo?: unknown) {
  return {
    status,
    ok: status >= 200 && status < 300,
    json: async () => {
      if (cuerpo === undefined) throw new SyntaxError('Unexpected token < in JSON');
      return cuerpo;
    },
  };
}

const fetchSimulado = vi.fn();

beforeEach(() => {
  vi.useFakeTimers();
  fetchSimulado.mockReset();
  vi.stubGlobal('fetch', fetchSimulado);
});

describe('arrancar: ¿hay servidor?', () => {
  it('si contesta, usa su marca y no es el modo estático', async () => {
    fetchSimulado.mockResolvedValue(respuesta(200, { teamName: 'Mi Club', logo: 'mi.png', version: 'abc1234' }));
    const arranque = await arrancar();
    expect(arranque.modoEstatico).toBe(false);
    expect(arranque.marca).toMatchObject({ teamName: 'Mi Club', logo: 'mi.png', version: 'abc1234' });
    expect(fetchSimulado).toHaveBeenCalledWith('api/config', { cache: 'no-store' });
  });

  it.each([404, 403, 405])('un %i es un alojamiento de ficheros sin API: modo estático, sin insistir', async (estado) => {
    fetchSimulado.mockResolvedValue(respuesta(estado, {}));
    const alReintentar = vi.fn();
    const arranque = await arrancar({ alReintentar });
    expect(arranque.modoEstatico).toBe(true);
    expect(arranque.marca).toMatchObject({ teamName: 'FC Team', logo: 'img/logo.png' });
    expect(fetchSimulado).toHaveBeenCalledTimes(1);
    expect(alReintentar).not.toHaveBeenCalled();
  });

  it('un 200 que no es JSON (un alojamiento que contesta su página para todo) también es estático', async () => {
    fetchSimulado.mockResolvedValue(respuesta(200));
    expect((await arrancar()).modoEstatico).toBe(true);
    expect(fetchSimulado).toHaveBeenCalledTimes(1);
  });
});

describe('arrancar: el servidor existe pero ahora no contesta bien', () => {
  it.each([500, 502, 503, 429])('con un %i insiste hasta que conteste, en vez de caer al modo estático', async (estado) => {
    fetchSimulado
      .mockResolvedValueOnce(respuesta(estado, { error: 'desplegando' }))
      .mockResolvedValueOnce(respuesta(200, { teamName: 'Mi Club', logo: 'mi.png' }));
    const alReintentar = vi.fn();
    const promesa = arrancar({ alReintentar });

    await vi.advanceTimersByTimeAsync(0);
    expect(alReintentar).toHaveBeenCalledWith(1);
    expect(fetchSimulado).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(1000);
    const arranque = await promesa;
    expect(arranque.modoEstatico).toBe(false);
    expect(arranque.marca.teamName).toBe('Mi Club');
  });

  it('sin red tampoco es «sin servidor»', async () => {
    fetchSimulado
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce(respuesta(200, { teamName: 'Mi Club', logo: 'mi.png' }));
    const promesa = arrancar();
    await vi.advanceTimersByTimeAsync(1000);
    expect((await promesa).modoEstatico).toBe(false);
  });

  it('cada intento espera más (1, 2, 4, 8 s) hasta un tope de 10 s', async () => {
    fetchSimulado.mockRejectedValue(new TypeError('Failed to fetch'));
    const control = new AbortController();
    const promesa = arrancar({ señal: control.signal });
    const rechazada = expect(promesa).rejects.toBeDefined();

    const llamadasTras = async (ms: number) => {
      await vi.advanceTimersByTimeAsync(ms);
      return fetchSimulado.mock.calls.length;
    };
    expect(await llamadasTras(0)).toBe(1);
    expect(await llamadasTras(999)).toBe(1);
    expect(await llamadasTras(1)).toBe(2);          // t = 1 s
    expect(await llamadasTras(2000)).toBe(3);       // t = 3 s
    expect(await llamadasTras(4000)).toBe(4);       // t = 7 s
    expect(await llamadasTras(8000)).toBe(5);       // t = 15 s
    expect(await llamadasTras(9999)).toBe(5);
    expect(await llamadasTras(1)).toBe(6);          // t = 25 s: ya no pasa de 10 s entre intentos
    expect(await llamadasTras(10000)).toBe(7);

    control.abort();
    await rechazada;
  });

  it('cerrar la web (abortar) deja de insistir', async () => {
    fetchSimulado.mockRejectedValue(new TypeError('Failed to fetch'));
    const control = new AbortController();
    const promesa = arrancar({ señal: control.signal });
    const rechazada = expect(promesa).rejects.toBeDefined();
    await vi.advanceTimersByTimeAsync(0);
    expect(fetchSimulado).toHaveBeenCalledTimes(1);

    control.abort();
    await rechazada;
    await vi.advanceTimersByTimeAsync(60_000);
    expect(fetchSimulado).toHaveBeenCalledTimes(1);
    expect(vi.getTimerCount()).toBe(0);               // ni un temporizador huérfano
  });
});
