import { CabeceraTarjeta, FilaCombate, Llaves, Medalla, PanelDetalle, Tarjeta, TextoTenue, TituloSeccion } from '@fcteam/ui';

/** La ficha de un atleta subiendo desde abajo sobre la pantalla que había detrás (aquí, unas tarjetas). */
export function Ficha() {
  return (
    <div style={{ background: 'var(--fondo)', color: 'var(--texto)', padding: 16, minHeight: 640 }}>
      <Tarjeta><CabeceraTarjeta titulo="Ana Pérez" detalle="Gracie Madrid · Women's GI / Blue / 60KG" /></Tarjeta>
      <Tarjeta><CabeceraTarjeta titulo="Eva Gómez" detalle="Gracie Madrid · Women's GI / Blue / 60KG" /></Tarjeta>
      <Tarjeta><CabeceraTarjeta titulo="Luz Díaz" detalle="Fusión BJJ · Women's GI / Blue / 60KG" /></Tarjeta>
      <PanelDetalle abierto titulo="Ana Pérez" onCerrar={() => {}}>
        <TextoTenue>Gracie Madrid · ES</TextoTenue>
        <TextoTenue>Compite en: Gi y No-Gi</TextoTenue>
        <TextoTenue>
          <Medalla tipo="oro" /> Women's GI / Blue / Adult / 60KG<br />
          <Medalla tipo="plata" /> Women's NO-GI / Blue / Adult / 60KG
        </TextoTenue>
        <Llaves llaves={[
          { url: 'https://smoothcomp.com/es/event/1535/bracket/4', texto: 'Gi · Women Blue 60KG' },
          { url: 'https://smoothcomp.com/es/event/1526/bracket/9', texto: 'No-Gi · Women Blue 60KG' },
        ]} />
        <TituloSeccion nivel={3}>Combates</TituloSeccion>
        <FilaCombate hora="09:42" titulo="vs Eva Gómez" dia="sáb 17" evento="Gi" detalle="Cuartos · Mat 3"
          resultado={{ texto: 'Ganó · puntos', tono: 'ganado' }} />
        <FilaCombate hora="11:15" titulo="vs Luz Díaz" dia="sáb 17" evento="Gi" detalle="Final · Mat 3"
          resultado={{ texto: 'EN CURSO', tono: 'vivo' }} />
      </PanelDetalle>
    </div>
  );
}
