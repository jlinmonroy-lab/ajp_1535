/* Pantalla de inicio: buscar un evento de Smoothcomp.
 *
 * Habla con api/events/search, que el servidor contesta de su caché (nunca con una lectura de
 * Smoothcomp en medio), y lleva a #/evento/ID. El estado vive en un objeto mutable (como el
 * original) para que cada búsqueda lea lo último que se tecleó sin depender de cuándo repinte
 * React; `redibujar` solo avisa de que hay algo nuevo que enseñar.
 */
import { useCallback, useReducer, useRef, useState } from 'react';
import type { EventoBuscado, RespuestaBusqueda } from '../tipos';
import { mensajeDeError } from './api';

export const ESPERA_ESCRITURA_MS = 350;

export type Cuando = 'upcoming' | 'past' | 'all';

export interface EstadoBusqueda {
  /** Lo escrito tal cual (el campo es controlado). */
  texto: string;
  /** Lo escrito, sin espacios en los extremos: lo que se busca. */
  q: string;
  cuando: Cuando;
  pagina: number;
  eventos: EventoBuscado[];
  hayMas: boolean;
  /** Smoothcomp no respondió y el servidor contestó con lo que tenía guardado. */
  vieja: boolean;
  cargando: boolean;
  error: string | null;
  /** Lo que falló fue «Cargar más» (no la búsqueda): «Reintentar» debe pedir esa misma página. */
  falloAlCargarMas: boolean;
  /** La zona por defecto de config.json («Madrid, España»), o null si no hay. */
  zona: string | null;
  /** Si el chip está encendido. Empieza encendido en cada visita: no se recuerda que alguien lo apagara. */
  zonaActiva: boolean;
}

export interface Busqueda {
  estado: EstadoBusqueda;
  escribir: (texto: string) => void;
  /** Buscar ya (Intro en el campo), sin esperar a que pare de escribir. */
  enviar: () => void;
  cambiarCuando: (cuando: Cuando) => void;
  cargarMas: () => void;
  reintentar: () => void;
  cambiarZona: (activa: boolean) => void;
  /** Se llama al enseñar el inicio: la primera vez lanza la búsqueda. */
  mostrar: () => void;
}

export function usarBusquedaEventos(zona: string | null | undefined): Busqueda {
  const [, redibujar] = useReducer((n: number) => n + 1, 0);
  const ticket = useRef(0);       // descarta respuestas de búsquedas que ya no son la última
  const temporizador = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  // Objeto mutable y estable (ver la cabecera): se crea una vez y nunca se sustituye.
  const [est] = useState<EstadoBusqueda>(() => ({
    texto: '', q: '', cuando: 'upcoming', pagina: 1,
    eventos: [], hayMas: false, vieja: false, cargando: false, error: null, falloAlCargarMas: false,
    zona: zona || null, zonaActiva: !!zona,
  }));

  const buscar = useCallback(async (reiniciar: boolean) => {
    const e = est;
    const miTicket = ++ticket.current;
    if (reiniciar) {
      e.pagina = 1;
      e.eventos = [];
      e.hayMas = false;
      e.vieja = false;
    } else {
      e.pagina += 1;
    }
    e.error = null;
    e.falloAlCargarMas = false;
    e.cargando = true;
    redibujar();

    const params = new URLSearchParams({ q: e.q, when: e.cuando, page: String(e.pagina) });
    if (e.zonaActiva) params.set('zona', '1');
    try {
      const resp = await fetch(`api/events/search?${params}`, { cache: 'no-store' });
      if (!resp.ok) throw new Error(await mensajeDeError(resp));
      const cuerpo: RespuestaBusqueda = await resp.json();
      if (miTicket !== ticket.current) return;

      const vistos = new Set(e.eventos.map((ev) => ev.id));
      e.eventos = e.eventos.concat(cuerpo.events.filter((ev) => !vistos.has(ev.id)));
      e.hayMas = !!cuerpo.hasMore;
      e.vieja = !!cuerpo.stale;
    } catch (err) {
      if (miTicket !== ticket.current) return;
      e.error = (err instanceof Error && err.message) || 'No se pudo buscar';
      if (!reiniciar) {
        e.pagina -= 1;
        e.falloAlCargarMas = true;
      }
    } finally {
      if (miTicket === ticket.current) {
        e.cargando = false;
        redibujar();
      }
    }
  }, []);

  const buscarTrasPausa = useCallback(() => {
    clearTimeout(temporizador.current);
    temporizador.current = setTimeout(() => { void buscar(true); }, ESPERA_ESCRITURA_MS);
  }, [buscar]);

  const buscarYa = useCallback((reiniciar: boolean) => {
    clearTimeout(temporizador.current);
    void buscar(reiniciar);
  }, [buscar]);

  return {
    estado: { ...est },
    escribir: (texto) => {
      est.texto = texto;
      est.q = texto.trim();
      redibujar();     // la tarjeta "Abrir el evento n.º…" aparece sin esperar
      buscarTrasPausa();
    },
    enviar: () => buscarYa(true),
    cambiarCuando: (cuando) => {
      est.cuando = cuando;
      buscarYa(true);
    },
    cargarMas: () => { void buscar(false); },
    reintentar: () => buscarYa(!est.falloAlCargarMas),
    cambiarZona: (activa) => {
      est.zonaActiva = activa && !!est.zona;
      buscarYa(true);
    },
    mostrar: () => {
      const e = est;
      if (!e.eventos.length && !e.cargando && !e.error) void buscar(true);
    },
  };
}
