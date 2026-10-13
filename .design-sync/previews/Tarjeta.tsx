import type { ReactNode } from 'react';
import { CabeceraTarjeta, Etiqueta, FilaCombate, Tarjeta, TextoTenue } from '@fcteam/ui';

const Fondo = ({ children }: { children: ReactNode }) => (
  <div style={{ background: 'var(--fondo)', color: 'var(--texto)', padding: 16 }}>{children}</div>
);

/** Una tarjeta con su cabecera y filas debajo: así se arma la de un tatami. */
export function ConCabeceraYFilas() {
  return (
    <Fondo>
      <Tarjeta>
        <CabeceraTarjeta titulo="Mat 3" detalle="12 combates · 1 en curso" />
        <FilaCombate hora="11:15" titulo="Ana Pérez vs Luz Díaz" dia="sáb 17" diaComo="texto" evento="Gi"
          detalle="Women's GI / Blue / Adult / 60KG" resultado={{ texto: 'EN CURSO', tono: 'vivo' }} />
        <FilaCombate hora="11:32" titulo="Eva Gómez vs Marta Ruiz" dia="sáb 17" diaComo="texto" evento="Gi"
          detalle="Women's GI / Blue / Adult / 60KG" />
      </Tarjeta>
    </Fondo>
  );
}

/** Los tres bordes: normal, con el color del equipo (acento) y dorado (avisos). */
export function Bordes() {
  return (
    <Fondo>
      <Tarjeta>
        <CabeceraTarjeta titulo="Borde normal" detalle="El de cualquier tarjeta" />
      </Tarjeta>
      <Tarjeta borde="acento">
        <CabeceraTarjeta titulo="Borde de acento" derecha={<Etiqueta>Abrir</Etiqueta>} detalle="Llama la atención con el color del equipo" />
      </Tarjeta>
      <Tarjeta borde="oro">
        <strong>El schedule aún no está publicado.</strong>
        <br />
        <TextoTenue como="span">Borde dorado: un aviso que no es un error.</TextoTenue>
      </Tarjeta>
    </Fondo>
  );
}
