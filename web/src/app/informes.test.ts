import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { informarError, iniciarInformes, MAX_INFORMES, olvidarInformes, URL_INFORMES } from './informes';
import { BUILD } from './version';

const fetchSimulado = vi.fn();

/** El cuerpo JSON del informe número `n` (el primero por defecto). */
const informe = (n = 0) => JSON.parse(fetchSimulado.mock.calls[n]![1].body);

beforeEach(() => {
  olvidarInformes();
  fetchSimulado.mockReset();
  fetchSimulado.mockResolvedValue({ status: 204 });
  vi.stubGlobal('fetch', fetchSimulado);
  history.replaceState(null, '', '/');
  location.hash = '#/evento/33588';
});

afterEach(() => {
  history.replaceState(null, '', '/');
});

describe('informarError', () => {
  it('manda a la dirección relativa de la API el tipo, el mensaje, la pila, dónde y qué versión', () => {
    const error = new TypeError('x es undefined');
    informarError('js', error);

    expect(fetchSimulado).toHaveBeenCalledTimes(1);
    const [url, init] = fetchSimulado.mock.calls[0]!;
    expect(url).toBe(URL_INFORMES);
    expect(url).toBe('api/client-error');     // relativa: la web puede colgar de una subcarpeta
    expect(init).toMatchObject({ method: 'POST', keepalive: true, headers: { 'Content-Type': 'application/json' } });
    expect(informe()).toMatchObject({
      tipo: 'js', mensaje: 'TypeError: x es undefined', build: BUILD, ruta: '/#/evento/33588',
    });
    expect(informe().pila).toContain('TypeError');
    expect(informe().ua).toEqual(expect.any(String));
  });

  it('la ruta no lleva la query: puede llevar lo que se ha buscado', () => {
    history.replaceState(null, '', '/?q=Ana+Perez#/evento/1');
    informarError('js', new Error('x'));
    expect(informe().ruta).toBe('/#/evento/1');
    expect(JSON.stringify(informe())).not.toContain('Ana');
  });

  it('en un fallo de render, la pila de componentes va antes que la de JavaScript', () => {
    informarError('render', new Error('boom'), '\n    at Tarjeta (app.js:1:1)\n    at Evento (app.js:2:2)');
    const pila: string = informe().pila;
    expect(pila.startsWith('at Tarjeta')).toBe(true);
    expect(pila.indexOf('at Evento')).toBeLessThan(pila.indexOf('Error: boom'));
  });

  it('lo que no es un Error también se cuenta', () => {
    informarError('promesa', 'un texto suelto');
    expect(informe()).toMatchObject({ tipo: 'promesa', mensaje: 'un texto suelto', pila: '' });
  });

  it('recorta lo muy largo antes de mandarlo', () => {
    const error = new Error('m'.repeat(1000));
    error.stack = 'p'.repeat(5000);
    informarError('js', error);
    expect(informe().mensaje.length).toBe(300);
    expect(informe().pila.length).toBe(1500);
  });

  it('el mismo error no se manda dos veces', () => {
    informarError('js', new Error('igual'));
    informarError('js', new Error('igual'));
    expect(fetchSimulado).toHaveBeenCalledTimes(1);
    informarError('datos', new Error('igual'));      // otro tipo: otro informe
    expect(fetchSimulado).toHaveBeenCalledTimes(2);
  });

  it(`como mucho ${MAX_INFORMES} por carga de página: un error en bucle no se convierte en cientos de peticiones`, () => {
    for (let i = 0; i < MAX_INFORMES + 10; i += 1) informarError('js', new Error(`distinto ${i}`));
    expect(fetchSimulado).toHaveBeenCalledTimes(MAX_INFORMES);
  });

  it('ignora el ruido del navegador y de las extensiones', () => {
    informarError('js', new Error('ResizeObserver loop completed with undelivered notifications.'));
    informarError('js', 'Script error.');
    expect(fetchSimulado).not.toHaveBeenCalled();
  });

  it('nunca lanza, falle como falle el envío', async () => {
    fetchSimulado.mockRejectedValue(new Error('sin red'));
    expect(() => informarError('js', new Error('a'))).not.toThrow();
    fetchSimulado.mockImplementation(() => { throw new Error('síncrono'); });
    expect(() => informarError('js', new Error('b'))).not.toThrow();
    vi.stubGlobal('fetch', undefined);
    expect(() => informarError('js', new Error('c'))).not.toThrow();
    await Promise.resolve();      // si el rechazo quedara sin atender, Vitest lo marcaría como error
  });
});

describe('iniciarInformes', () => {
  it('recoge los errores que nadie atrapa y los rechazos de promesas', () => {
    const desenganchar = iniciarInformes();
    window.dispatchEvent(new ErrorEvent('error', { error: new RangeError('fuera de rango'), message: 'fuera de rango' }));
    expect(informe(0)).toMatchObject({ tipo: 'js', mensaje: 'RangeError: fuera de rango' });

    window.dispatchEvent(Object.assign(new Event('unhandledrejection'), { reason: new Error('promesa rota') }));
    expect(informe(1)).toMatchObject({ tipo: 'promesa', mensaje: 'Error: promesa rota' });
    desenganchar();
  });

  it('si el evento no trae el error, usa su mensaje', () => {
    const desenganchar = iniciarInformes();
    window.dispatchEvent(new ErrorEvent('error', { message: 'algo pasó' }));
    expect(informe()).toMatchObject({ tipo: 'js', mensaje: 'algo pasó' });
    desenganchar();
  });

  it('al desengancharlo deja de recoger', () => {
    const desenganchar = iniciarInformes();
    desenganchar();
    window.dispatchEvent(new ErrorEvent('error', { message: 'ya no' }));
    window.dispatchEvent(Object.assign(new Event('unhandledrejection'), { reason: 'ya no' }));
    expect(fetchSimulado).not.toHaveBeenCalled();
  });
});
