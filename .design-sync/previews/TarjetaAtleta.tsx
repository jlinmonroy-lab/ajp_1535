import type { ReactNode } from 'react';
import { TarjetaAtleta } from '@fcteam/ui';

const Fondo = ({ children }: { children: ReactNode }) => (
  <div style={{ background: 'var(--fondo)', color: 'var(--texto)', padding: 16 }}>{children}</div>
);

// Foto de ejemplo sin red: un cuadrado con iniciales, como las que dejaría Smoothcomp.
const avatar = (iniciales: string) =>
  'data:image/svg+xml;utf8,' + encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" width="88" height="88"><rect width="88" height="88" fill="#3a3a3a"/>' +
    `<text x="44" y="57" font-size="34" text-anchor="middle" fill="#fff" font-family="sans-serif">${iniciales}</text></svg>`);

const combates = [
  { id: 'a', hora: '09:42', titulo: 'vs Eva Gómez', dia: 'sáb 17', evento: 'Gi', detalle: 'Cuartos · Mat 3',
    resultado: { texto: 'Ganó · puntos', tono: 'ganado' as const } },
  { id: 'b', hora: '11:15', titulo: 'vs Luz Díaz', dia: 'sáb 17', evento: 'Gi', detalle: 'Semifinal · Mat 3',
    resultado: { texto: 'EN CURSO', tono: 'vivo' as const } },
  { id: 'c', hora: '13:30', titulo: 'vs Por determinar', dia: 'sáb 17', evento: 'Gi', detalle: 'Final · Mat 3',
    resultado: { texto: 'Pendiente' } },
];

const base = { id: 'ana perez|gracie madrid', nombre: 'Ana Pérez', club: 'Gracie Madrid',
  categoria: "Women's GI / Blue / Adult / 60KG", foto: avatar('AP'), siguiendo: false, onSeguir: () => {} };

/** En una búsqueda: solo la cabecera, con el botón de seguir. */
export function EnLaBusqueda() {
  return <Fondo><TarjetaAtleta {...base} /></Fondo>;
}

/** En «Mis atletas»: sus combates hora a hora, el estado de cada uno y el enlace a su cuadro. */
export function ConCombates() {
  return (
    <Fondo>
      <TarjetaAtleta
        {...base}
        siguiendo
        combates={combates}
        llaves={[{ url: 'https://smoothcomp.com/es/event/33588/bracket/1', texto: 'Ver llave' }]}
      />
    </Fondo>
  );
}

/** Con medalla de oro, del grupo y con dos cuadros (Gi y No-Gi): los enlaces se distinguen por categoría. */
export function MedallaYGrupo() {
  return (
    <Fondo>
      <TarjetaAtleta
        {...base}
        nombre="Marta Ruiz"
        id="marta ruiz|fusion bjj"
        club="Fusión BJJ"
        foto={avatar('MR')}
        medalla="oro"
        delGrupo
        siguiendo
        combates={combates.slice(0, 1)}
        llaves={[
          { url: 'https://smoothcomp.com/es/event/1535/bracket/4', texto: 'Gi · Women Blue 60KG' },
          { url: 'https://smoothcomp.com/es/event/1526/bracket/9', texto: 'No-Gi · Women Blue 60KG' },
        ]}
      />
    </Fondo>
  );
}

/** En el panel del servidor: el botón «Seguir para todos», apagado y ya activado. */
export function PanelDelGrupo() {
  return (
    <Fondo>
      <TarjetaAtleta {...base} paraTodos={{ activo: false, onAlternar: () => {} }} />
      <TarjetaAtleta
        {...base}
        id="eva gomez|gracie madrid"
        nombre="Eva Gómez"
        foto={avatar('EG')}
        delGrupo
        paraTodos={{ activo: true, onAlternar: () => {} }}
      />
    </Fondo>
  );
}

/** Aún sin combates en el schedule. */
export function SinCombatesTodavia() {
  return <Fondo><TarjetaAtleta {...base} siguiendo combates={[]} /></Fondo>;
}
