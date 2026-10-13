/* Recorridos de punta a punta con el servidor simulado por un `fetch` falso. Además de lo que
   enseñan, vigilan que React no proteste (claves repetidas, estado cambiado en el render…):
   cualquier console.error hace fallar la prueba. */
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Atleta, Combate, Datos } from '../tipos';
import { App } from './App';

const lado = (athleteId: string, name: string) =>
  ({ athleteId, registrationId: athleteId, name, club: null, country: null, image: null, isWinner: false });

const atleta = (id: string, name: string, matchIds: string[], extra: Partial<Atleta> = {}): Atleta => ({
  id, name, club: 'Club A', country: 'ES', image: null, categories: ['Women GI / Blue / 60KG'],
  brackets: [{ id: '1-9', category: 'Women GI / Blue / 60KG', eventLabel: null, url: 'https://x.test/llave/1' }],
  matchIds, medals: [], bestMedal: null, events: ['1'], ...extra,
});

const combate = (id: string, a: [string, string], b: [string, string], extra: Partial<Combate> = {}): Combate => ({
  id, eventId: '1', eventLabel: null, bracketId: '1-9', bracketUrl: null, mat: 'Mat 1', round: 'Semifinal',
  category: { raw: 'Women GI / Blue / 60KG' }, estimatedStart: '2026-10-17T10:00:00', day: '2026-10-17',
  state: 'seeded', wonBy: null, sides: [lado(...a), lado(...b)], ...extra,
});

const DATOS: Datos = {
  events: [{ id: '1', label: null, name: 'Open de Prueba', published: true }],
  group: { athletes: [] },
  fetchedAt: new Date().toISOString(),
  stale: false, staleSince: null,
  mats: [{ key: '1:1', name: 'Mat 1' }],
  matches: [
    combate('1-1', ['ana', 'Ana Pérez'], ['eva', 'Eva Gómez'], { state: 'running' }),
    combate('1-2', ['ana', 'Ana Pérez'], ['luz', 'Luz Díaz']),
  ],
  athletes: [
    atleta('ana', 'Ana Pérez', ['1-1', '1-2'], { bestMedal: 'gold', medals: [{ bracketId: '1-9', eventId: '1', category: 'Women GI / Blue / 60KG', medal: 'gold' }] }),
    atleta('eva', 'Eva Gómez', ['1-1']),
    atleta('luz', 'Luz Díaz', ['1-2']),
  ],
};

const json = (status: number, cuerpo: unknown, cabeceras: Record<string, string> = {}) => ({
  status, ok: status >= 200 && status < 300,
  headers: { get: (n: string) => cabeceras[n] ?? cabeceras[n.toLowerCase()] ?? null },
  json: async () => cuerpo,
});

let servidor: Record<string, (init?: RequestInit) => ReturnType<typeof json>>;
let errores: ReturnType<typeof vi.spyOn>;

function configurar(config: object = { teamName: 'FC Team', logo: 'img/logo.png' }) {
  servidor = {
    'api/config': () => json(200, config),
    'api/events/1/data': () => json(200, DATOS, { ETag: '"v1"' }),
    'api/events/1/grupo': () => json(200, { atletas: [] }),
    'api/events/999/data': () => json(404, { error: 'Ese evento no existe en Smoothcomp' }),
    'api/events/search': () => json(200, {
      events: [{ id: '1', title: 'Open de Prueba', url: null, startdate: '2099-01-01', enddate: '2099-01-01', city: 'Madrid', country: 'ES' }],
      page: 1, hasMore: false, stale: false,
    }),
  };
}

beforeEach(() => {
  configurar();
  location.hash = '#/';
  window.scrollTo = vi.fn();
  errores = vi.spyOn(console, 'error').mockImplementation(() => {});
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    const ruta = url.split('?')[0]!;
    const respuesta = servidor[ruta];
    if (!respuesta) throw new Error(`fetch sin simular: ${url}`);
    return respuesta(init);
  }));
});

afterEach(() => {
  expect(errores.mock.calls.map((c: unknown[]) => String(c[0]).slice(0, 200))).toEqual([]);
  errores.mockRestore();
});

const entrarAlEvento = async () => {
  location.hash = '#/evento/1';
  render(<App />);
  await screen.findByText('Todavía no hay atletas en la lista.', { exact: false });
};

const configurarBusquedaOk = () => json(200, {
  events: [{ id: '1', title: 'Open de Prueba', url: null, startdate: '2099-01-01', enddate: null, city: null, country: null }],
  page: 1, hasMore: false, stale: false,
});

describe('inicio', () => {
  it('lista los próximos eventos, con el título y el chip de zona', async () => {
    configurar({ teamName: 'FC Team', logo: 'img/logo.png', zona: { nombre: 'Madrid, España' } });
    render(<App />);
    expect(await screen.findByText('Open de Prueba')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'FC Team' })).toBeInTheDocument();
    expect(screen.getByText('Próximos eventos en Madrid, España')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Madrid, España ✕/ })).toBeInTheDocument();
    expect(document.title).toBe('Eventos · FC Team');
    expect(screen.getByRole('link', { name: /Open de Prueba/ })).toHaveAttribute('href', '#/evento/1');
  });

  it('no muestra «Recientes», ni siquiera con eventos recordados de antes', async () => {
    localStorage.setItem('sbjj:recientes', JSON.stringify([
      { id: '7', title: 'Evento Recordado', startdate: '2099-02-02', enddate: null, city: null, country: null },
    ]));
    render(<App />);
    await screen.findByText('Open de Prueba');
    expect(screen.queryByText('Recientes')).not.toBeInTheDocument();
    expect(screen.queryByText('Evento Recordado')).not.toBeInTheDocument();
    localStorage.removeItem('sbjj:recientes');
  });

  it('pegar el número o el enlace de un evento ofrece abrirlo directamente', async () => {
    render(<App />);
    await screen.findByText('Open de Prueba');
    fireEvent.change(screen.getByLabelText('Buscar evento en Smoothcomp'), {
      target: { value: 'https://spainbjjtour.smoothcomp.com/es/event/33588' },
    });
    const abrir = await screen.findByRole('link', { name: /Abrir el evento n\.º 33588/ });
    expect(abrir).toHaveAttribute('href', '#/evento/33588');
  });

  it('si la búsqueda falla lo dice y deja reintentar', async () => {
    servidor['api/events/search'] = () => json(502, { error: 'Smoothcomp no responde' });
    render(<App />);
    expect(await screen.findByText('Smoothcomp no responde')).toBeInTheDocument();

    servidor['api/events/search'] = configurarBusquedaOk;
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }));
    expect(await screen.findByText('Open de Prueba')).toBeInTheDocument();
  });
});

describe('evento', () => {
  it('abre el tablero con el nombre del evento y el estado de los datos', async () => {
    await entrarAlEvento();
    expect(screen.getByRole('heading', { name: 'Open de Prueba' })).toBeInTheDocument();
    expect(document.title).toBe('Open de Prueba · FC Team');
    expect(document.getElementById('estado')).toHaveTextContent(/^Actualizado hace \d+s · 2 combates · 3 atletas$/);
  });

  it('buscar un atleta, seguirlo y verlo en «Mis atletas» con sus próximos combates', async () => {
    await entrarAlEvento();
    fireEvent.click(screen.getByRole('tab', { name: 'Buscar' }));
    expect(screen.getByText('Escribe al menos dos letras.')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Buscar atleta'), { target: { value: 'perez' } });
    const resultados = document.getElementById('resultados')!;
    expect(within(resultados).getByText('1 resultado(s)')).toBeInTheDocument();
    fireEvent.click(within(resultados).getByRole('button', { name: 'Seguir' }));

    expect(document.getElementById('contador-seguidos')).toHaveTextContent('1');
    expect(JSON.parse(localStorage.getItem('sbjj:seguidos')!)).toEqual(['ana']);

    fireEvent.click(screen.getByRole('tab', { name: /Mis atletas/ }));
    const lista = document.getElementById('lista-seguidos')!;
    expect(within(lista).getByText('Próximos combates')).toBeInTheDocument();
    expect(within(lista).getAllByText('Ana Pérez').length).toBeGreaterThanOrEqual(3);   // 2 próximos + ficha
    expect(within(lista).getAllByText('EN CURSO')).toHaveLength(2);     // la tarjeta de próximos y la ficha
    expect(within(lista).getByRole('button', { name: 'Siguiendo' })).toBeInTheDocument();
    expect(within(lista).getByRole('link', { name: /Ver llave/ })).toHaveAttribute('href', 'https://x.test/llave/1');
  });

  it('lo que se sigue persiste entre visitas', async () => {
    localStorage.setItem('sbjj:seguidos', JSON.stringify(['eva']));
    await act(async () => { location.hash = '#/evento/1'; render(<App />); });
    await screen.findByText('Mis atletas', { selector: 'h2' });
    expect(document.getElementById('contador-seguidos')).toHaveTextContent('1');
  });

  it('un atleta sin acentos se encuentra por su nombre con acentos, y por club o categoría', async () => {
    await entrarAlEvento();
    fireEvent.click(screen.getByRole('tab', { name: 'Buscar' }));
    const campo = screen.getByLabelText('Buscar atleta');
    for (const [texto, esperados] of [['gomez', 1], ['club a', 3], ['60kg', 3], ['zzz', 0]] as const) {
      fireEvent.change(campo, { target: { value: texto } });
      const r = document.getElementById('resultados')!;
      if (esperados) expect(within(r).getByText(`${esperados} resultado(s)`)).toBeInTheDocument();
      else expect(within(r).getByText('Ningún atleta coincide.')).toBeInTheDocument();
    }
  });

  it('una ficha sin categorías no impide ver el resto de la lista', async () => {
    const sinCategorias = { ...atleta('dan', 'Daniel Ruiz', []), categories: undefined } as unknown as Atleta;
    servidor['api/events/1/data'] = () => json(200, { ...DATOS, athletes: [...DATOS.athletes, sinCategorias] }, { ETag: '"v1"' });
    await entrarAlEvento();
    fireEvent.click(screen.getByRole('tab', { name: 'Buscar' }));
    fireEvent.change(screen.getByLabelText('Buscar atleta'), { target: { value: 'daniel' } });
    const resultados = document.getElementById('resultados')!;
    expect(within(resultados).getByText('1 resultado(s)')).toBeInTheDocument();
    expect(within(resultados).getByText('Daniel Ruiz')).toBeInTheDocument();
  });

  it('mientras llegan los datos, «Buscar» dice que está cargando en vez de quedarse en blanco', async () => {
    servidor['api/events/1/data'] = () => new Promise(() => {}) as never;
    location.hash = '#/evento/1';
    render(<App />);
    fireEvent.click(await screen.findByRole('tab', { name: 'Buscar' }));
    expect(within(document.getElementById('resultados')!).getByText('Cargando…')).toBeInTheDocument();
  });

  it('si una ficha rota hace fallar la lista, lo dice y el resto de la web sigue viva', async () => {
    const rota = { ...atleta('rota', 'Rota', []), name: 123 } as unknown as Atleta;
    servidor['api/events/1/data'] = () => json(200, { ...DATOS, athletes: [...DATOS.athletes, rota] }, { ETag: '"v1"' });
    await entrarAlEvento();
    fireEvent.click(screen.getByRole('tab', { name: 'Buscar' }));
    fireEvent.change(screen.getByLabelText('Buscar atleta'), { target: { value: 'ana' } });

    expect(await screen.findByText('No se pudo mostrar la búsqueda', { exact: false })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Tatamis' })).toBeInTheDocument();
    expect(screen.getByLabelText('Buscar atleta')).toHaveValue('ana');
    // React cuenta el fallo por consola: aquí es lo esperado, no un descuido.
    expect(errores).toHaveBeenCalled();
    errores.mockClear();
  });

  it('tocar el nombre abre la ficha con medallas, llaves y combates, y × la cierra', async () => {
    localStorage.setItem('sbjj:seguidos', JSON.stringify(['ana']));
    await act(async () => { location.hash = '#/evento/1'; render(<App />); });
    await screen.findByText('Próximos combates');

    fireEvent.click(within(document.getElementById('lista-seguidos')!).getAllByText('Ana Pérez').at(-1)!);
    const ficha = await screen.findByRole('dialog', { name: 'Ana Pérez' });
    expect(within(ficha).getByRole('img', { name: 'Oro' })).toBeInTheDocument();
    expect(within(ficha).getByText('Combates')).toBeInTheDocument();
    expect(within(ficha).getByText('vs Eva Gómez')).toBeInTheDocument();
    expect(within(ficha).getByText('vs Luz Díaz')).toBeInTheDocument();

    fireEvent.click(within(ficha).getByRole('button', { name: 'Cerrar' }));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('«Tatamis» enseña qué hay en cada uno, con lo que está en curso primero', async () => {
    await entrarAlEvento();
    fireEvent.click(screen.getByRole('tab', { name: 'Tatamis' }));
    const tatamis = document.getElementById('vista-tatamis')!;
    expect(within(tatamis).getByText('Mat 1')).toBeInTheDocument();
    expect(within(tatamis).getByText('2 combates · 1 en curso')).toBeInTheDocument();
    expect(within(tatamis).getByText('Ana Pérez vs Eva Gómez')).toBeInTheDocument();
    expect(within(tatamis).getByText('EN CURSO')).toBeInTheDocument();
  });

  it('un evento que no existe lo dice, sin pestañas, y lleva de vuelta al inicio', async () => {
    location.hash = '#/evento/999';
    render(<App />);
    expect(await screen.findByText('Ese evento no existe en Smoothcomp')).toBeInTheDocument();
    expect(document.getElementById('estado')).toHaveTextContent('Ese evento no existe');
    expect(screen.queryByRole('tab')).toBeNull();
    expect(screen.getByRole('link', { name: /Volver a los eventos/ })).toHaveAttribute('href', '#/');
  });

  it('un evento sin schedule publicado enseña el aviso en cada pestaña', async () => {
    servidor['api/events/1/data'] = () => json(200, {
      ...DATOS, matches: [], athletes: [], mats: [], events: [{ id: '1', label: null, name: 'Futuro', published: false }],
    }, { ETag: '"v1"' });
    location.hash = '#/evento/1';
    render(<App />);
    expect(await screen.findByText('El schedule aún no está publicado.')).toBeInTheDocument();
    expect(document.getElementById('estado')).toHaveTextContent('Schedule sin publicar');

    fireEvent.click(screen.getByRole('tab', { name: 'Buscar' }));
    fireEvent.change(screen.getByLabelText('Buscar atleta'), { target: { value: 'ana' } });
    expect(within(document.getElementById('resultados')!).getByText('El schedule aún no está publicado.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: 'Tatamis' }));
    expect(within(document.getElementById('vista-tatamis')!).getByText('El schedule aún no está publicado.')).toBeInTheDocument();
  });

  it('el botón de volver lleva al inicio', async () => {
    await entrarAlEvento();
    fireEvent.click(screen.getByRole('button', { name: 'Volver a los eventos' }));
    expect(location.hash).toBe('#/');
  });
});

describe('el servidor no contesta al abrir la web', () => {
  it('lo dice y vuelve a probar hasta que conteste, sin caer al modo estático', async () => {
    let intentos = 0;
    servidor['api/config'] = () => {
      intentos += 1;
      return intentos === 1
        ? json(503, { error: 'desplegando' })
        : json(200, { teamName: 'FC Team', logo: 'img/logo.png' });
    };
    render(<App />);
    expect(await screen.findByText(/No se pudo conectar con el servidor/)).toBeInTheDocument();

    // Al segundo intento (a los 1000 ms) ya es el servidor de siempre: lista los eventos.
    expect(await screen.findByText('Open de Prueba', {}, { timeout: 4000 })).toBeInTheDocument();
    expect(screen.queryByText(/No se pudo conectar/)).toBeNull();
    expect(intentos).toBe(2);
    expect(screen.queryByText('Aún no hay datos publicados')).toBeNull();
  });
});

describe('modo estático (sin servidor)', () => {
  it('si no hay API lee data.json y no ofrece volver', async () => {
    const llamadas: string[] = [];
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      llamadas.push(url);
      if (url === 'data.json') return json(200, DATOS);
      return json(404, {});
    }));
    render(<App />);
    expect(await screen.findByRole('heading', { name: 'Open de Prueba' })).toBeInTheDocument();
    expect(llamadas).toContain('data.json');
    expect(screen.queryByRole('button', { name: 'Volver a los eventos' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Actualizar ahora' })).toBeInTheDocument();
  });
});

describe('panel del grupo (en el equipo del servidor)', () => {
  const abrirPanel = async () => {
    // jsdom corre en localhost, así que esto es «el equipo del servidor»: el panel ya está abierto.
    await entrarAlEvento();
    return screen.getByRole('button', { name: 'Añadir' }).closest('form')!;
  };

  it('apuntar a mano manda el alta y enseña el aviso y la lista nueva', async () => {
    servidor['api/events/1/grupo'] = (init) => init?.method === 'POST'
      ? json(200, { atletas: [{ id: 'nadie|club z', name: 'Nadie Nuevo', club: 'Club Z' }] })
      : json(200, { atletas: [] });
    const form = await abrirPanel();

    fireEvent.change(within(form).getByLabelText('Nombre del atleta'), { target: { value: 'Nadie Nuevo' } });
    fireEvent.change(within(form).getByLabelText('Club'), { target: { value: 'Club Z' } });
    await act(async () => { fireEvent.click(within(form).getByRole('button', { name: 'Añadir' })); });

    expect(await screen.findByText('Nadie Nuevo añadido. Ya lo ve todo el grupo.')).toBeInTheDocument();
    const enviado = vi.mocked(fetch).mock.calls.find(([, init]) => init?.method === 'POST')!;
    expect(JSON.parse(String(enviado[1]!.body))).toEqual({ name: 'Nadie Nuevo', club: 'Club Z', accion: 'añadir' });
    expect(await screen.findByText('Lista del grupo (1)')).toBeInTheDocument();
    expect(screen.getByText('Nadie Nuevo')).toBeInTheDocument();
    expect(screen.getByText('sin combates todavía')).toBeInTheDocument();
  });

  it('si el servidor rechaza el alta, avisa del error y conserva lo escrito', async () => {
    servidor['api/events/1/grupo'] = (init) => init?.method === 'POST'
      ? json(403, { error: 'Solo desde el equipo del servidor' }) : json(200, { atletas: [] });
    const form = await abrirPanel();

    fireEvent.change(within(form).getByLabelText('Nombre del atleta'), { target: { value: 'Nadie' } });
    await act(async () => { fireEvent.click(within(form).getByRole('button', { name: 'Añadir' })); });

    expect(await screen.findByText(/No se pudo guardar \(Solo desde el equipo del servidor\)/)).toBeInTheDocument();
    expect(within(form).getByLabelText('Nombre del atleta')).toHaveValue('Nadie');
  });

  it('«Seguir para todos» marca al atleta en el acto, sin esperar a los datos', async () => {
    servidor['api/events/1/grupo'] = (init) => init?.method === 'POST'
      ? json(200, { atletas: [{ id: 'eva', name: 'Eva Gómez', club: 'Club A' }] }) : json(200, { atletas: [] });
    await abrirPanel();
    fireEvent.click(screen.getByRole('tab', { name: 'Buscar' }));
    fireEvent.change(screen.getByLabelText('Buscar atleta'), { target: { value: 'eva' } });

    await act(async () => {
      fireEvent.click(within(document.getElementById('resultados')!).getByRole('button', { name: 'Seguir para todos' }));
    });
    const r = document.getElementById('resultados')!;
    expect(await within(r).findByRole('button', { name: '✓ Lo ve todo el grupo' })).toBeInTheDocument();
    expect(within(r).getByText('grupo', { selector: '.fc-etiqueta' })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('Añadido. Ya lo ve todo el grupo.')).toBeInTheDocument());
  });
});
