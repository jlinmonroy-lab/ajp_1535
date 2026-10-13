import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
// Los estilos de la librería van primero (app.css se apoya en ellos) y se importan directos:
// vía el barril `./ui` el bundler los descarta, porque el barril no declara efectos.
import './ui/estilos';
import './app/app.css';
import { App } from './app/App';
import { informarError, iniciarInformes } from './app/informes';
import { LimiteError } from './app/LimiteError';
import { BUILD } from './app/version';

// Antes de pintar nada: lo que falle al arrancar también tiene que quedar contado.
iniciarInformes();
document.documentElement.dataset.build = BUILD;     // para saber qué versión es desde las devtools

createRoot(document.getElementById('raiz')!, {
  // Lo que atrapa cualquier LimiteError (el de la búsqueda o el de toda la web). Lo que nadie
  // atrapa llega a `window.onerror` y lo recoge iniciarInformes. Se mantiene el aviso por
  // consola que React daría por defecto.
  onCaughtError: (error, info) => {
    console.error(error);
    informarError('render', error, info.componentStack);
  },
}).render(
  <StrictMode>
    <LimiteError mensaje={`Algo ha fallado y la web no se puede mostrar. Recarga la página. (versión ${BUILD})`} recargable>
      <App />
    </LimiteError>
  </StrictMode>,
);
