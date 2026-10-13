import type { ReactNode } from 'react';
import { TarjetaEvento } from '@fcteam/ui';

const Fondo = ({ children }: { children: ReactNode }) => (
  <div style={{ background: 'var(--fondo)', color: 'var(--texto)', padding: 16 }}>{children}</div>
);

/** Un evento por venir: título, fechas y lugar; sin pastilla. */
export function Proximo() {
  return (
    <Fondo>
      <TarjetaEvento href="#/evento/33588" titulo="Madrid BJJ Cup 2026" detalle="17–18 oct 2026 · Arganda del Rey, ES" />
    </Fondo>
  );
}

/** El que está pasando hoy lleva la pastilla roja. */
export function Hoy() {
  return (
    <Fondo>
      <TarjetaEvento href="#/evento/1535" titulo="Spain BJJ Tour · Gi" detalle="17 oct 2026 · Arganda del Rey, ES"
        etiqueta={{ texto: 'Hoy', tono: 'vivo' }} />
      <TarjetaEvento href="#/evento/1526" titulo="Liga Madrid de Jiu-Jitsu" detalle="3 oct – 29 nov 2026 · Madrid, ES"
        etiqueta={{ texto: 'En curso', tono: 'vivo' }} />
    </Fondo>
  );
}

/** Los pasados salen con «Finalizado» y los títulos largos envuelven en vez de cortarse. */
export function Finalizado() {
  return (
    <Fondo>
      <TarjetaEvento href="#/evento/26416" titulo="Campeonato de España de Jiu-Jitsu Brasileño · Categorías Master y Juvenil"
        detalle="12–13 sep 2026 · Alcalá de Henares, ES" etiqueta={{ texto: 'Finalizado' }} />
    </Fondo>
  );
}

/** Atajo al pegar el número o el enlace de un evento: borde con el color del equipo. */
export function AbrirPorNumero() {
  return (
    <Fondo>
      <TarjetaEvento variante="abrirId" href="#/evento/33588" titulo="Abrir el evento n.º 33588"
        detalle="Directamente, sin buscar" etiqueta={{ texto: 'Abrir' }} />
    </Fondo>
  );
}
