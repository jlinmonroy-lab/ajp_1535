import type { ReactNode } from 'react';
import { FilaCombate, Tarjeta } from '@fcteam/ui';

// Una fila nunca va suelta: vive dentro de una tarjeta, apilada con otras.
const Fondo = ({ children }: { children: ReactNode }) => (
  <div style={{ background: 'var(--fondo)', color: 'var(--texto)', padding: 16 }}>
    <Tarjeta>{children}</Tarjeta>
  </div>
);

/** Visto desde un atleta: los cuatro estados posibles de un combate. */
export function Estados() {
  return (
    <Fondo>
      <FilaCombate hora="09:42" titulo="vs Eva Gómez" dia="sáb 17" evento="Gi" detalle="Cuartos · Mat 3"
        resultado={{ texto: 'Ganó · puntos', tono: 'ganado' }} />
      <FilaCombate hora="10:20" titulo="vs Luz Díaz" dia="sáb 17" evento="Gi" detalle="Semifinal · Mat 3"
        resultado={{ texto: 'Perdió · sumisión', tono: 'perdido' }} />
      <FilaCombate hora="11:15" titulo="vs Marta Ruiz" dia="sáb 17" evento="Gi" detalle="Combate por el bronce · Mat 3"
        resultado={{ texto: 'EN CURSO', tono: 'vivo' }} />
      <FilaCombate hora="13:30" titulo="vs Por determinar" dia="sáb 17" evento="Gi" detalle="Final · Mat 3"
        resultado={{ texto: 'Pendiente' }} />
    </Fondo>
  );
}

/** Visto desde un tatami: quiénes pelean, el día como texto y la categoría debajo. */
export function DesdeUnTatami() {
  return (
    <Fondo>
      <FilaCombate hora="11:15" titulo="Ana Pérez vs Luz Díaz" dia="sáb 17" diaComo="texto" evento="No-Gi"
        detalle="Women's NO-GI / Blue / Adult / 60KG" resultado={{ texto: 'EN CURSO', tono: 'vivo' }} />
      <FilaCombate hora="11:32" titulo="Eva Gómez vs Marta Ruiz" dia="sáb 17" diaComo="texto" evento="No-Gi"
        detalle="Women's NO-GI / Blue / Adult / 60KG" />
    </Fondo>
  );
}

/** Sin hora estimada todavía: la hora sale como «--:--». */
export function SinHora() {
  return (
    <Fondo>
      <FilaCombate hora="--:--" titulo="vs Por determinar" detalle="Octavos · Mat 1" resultado={{ texto: 'Pendiente' }} />
    </Fondo>
  );
}
