/* Raíz de la web. Dos pantallas según la URL:
 *   #/                 buscador de eventos (Inicio)
 *   #/evento/33588     tablero de ese evento (Evento)
 * Antes de pintar ninguna pregunta al servidor quién es (arrancar): si no contesta, la web
 * está servida como ficheros estáticos y cae al modo de siempre, con un único evento.
 */
import { useCallback, useEffect, useState } from 'react';
import { Aviso, Cabecera } from '../ui';
import { arrancar, CLAVE_ADMIN, comprobarAdmin, ES_LOCAL, type Arranque } from './api';
import { Evento } from './Evento';
import { Inicio } from './Inicio';
import { usarAviso } from './usarAviso';
import { usarBusquedaEventos } from './usarBusquedaEventos';
import { usarRutaHash } from './usarRutaHash';
import { borrarLocal, guardarLocal } from './util';

export function App() {
  const [arranque, setArranque] = useState<Arranque | null>(null);
  const [intentos, setIntentos] = useState(0);

  useEffect(() => {
    const control = new AbortController();
    arrancar({ alReintentar: setIntentos, señal: control.signal })
      .then((a) => { if (!control.signal.aborted) setArranque(a); })
      .catch(() => { /* la web se cerró mientras se esperaba al servidor */ });
    return () => control.abort();
  }, []);

  // Mientras se averigua: la cabecera sola, como la dejaba el HTML. Si el servidor no
  // contesta, además lo dice: sin esto parecería que la web está colgada.
  if (!arranque) {
    return (
      <>
        <Cabecera titulo="Eventos de Smoothcomp" logo="img/logo.png" />
        {intentos > 0 && <Aviso tono="error">No se pudo conectar con el servidor. Reintentando…</Aviso>}
      </>
    );
  }
  return <Principal arranque={arranque} />;
}

function Principal({ arranque }: { arranque: Arranque }) {
  const { marca, modoEstatico, esPanel } = arranque;
  const ids = usarRutaHash();
  // Vive aquí, no en Inicio: al volver de un evento se encuentra lo buscado como lo dejó.
  const busqueda = usarBusquedaEventos(marca.zona?.nombre);
  const { aviso, avisar } = usarAviso();

  const titular = useCallback((nombre: string | null) => {
    document.title = nombre ? `${nombre} · ${marca.teamName}` : `Eventos · ${marca.teamName}`;
  }, [marca.teamName]);

  const enInicio = !modoEstatico && !ids;
  useEffect(() => { if (enInicio) titular(null); }, [enInicio, titular]);

  /* ---------- Clave de administrador ---------- */
  async function entrarAdmin(clave: string): Promise<boolean | null> {
    const valida = await comprobarAdmin(clave);
    if (valida) {
      guardarLocal(CLAVE_ADMIN, clave);
      location.reload();     // el panel se decide al arrancar
      return true;
    }
    avisar(valida === false ? 'Clave incorrecta.' : 'No se pudo comprobar la clave. ¿Hay conexión?', true);
    return valida;
  }

  function salirAdmin() {
    borrarLocal(CLAVE_ADMIN);
    location.reload();       // el panel se decide al arrancar
  }

  if (!enInicio) {
    return <Evento key={ids ?? 'estatico'} ids={ids} arranque={arranque} alTitular={titular} />;
  }

  return (
    <>
      <Cabecera variante="inicio" titulo={marca.teamName} logo={marca.logo} />
      {aviso && <Aviso tono={aviso.error ? 'error' : 'ok'}>{aviso.texto}</Aviso>}
      <main>
        <Inicio
          busqueda={busqueda}
          // En el equipo del servidor el panel ya está abierto: no hace falta clave.
          mostrarAdmin={!!marca.admin && !ES_LOCAL}
          esPanel={esPanel}
          onEntrarAdmin={entrarAdmin}
          onSalirAdmin={salirAdmin}
        />
      </main>
    </>
  );
}
