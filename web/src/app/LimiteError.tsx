/* Si algo de dentro falla al pintarse, dice que falló en vez de dejar toda la web en blanco.
 *
 * React desmonta la aplicación entera ante una excepción que nadie atrapa. Aquí se acota a un
 * trozo: el resto de la pantalla sigue viva. Se recupera solo cuando cambia `reinicio` (p. ej.
 * lo que se está escribiendo), porque entonces lo que falló ya no es lo mismo.
 *
 * Quien informa del fallo al servidor es la raíz (`onCaughtError` en main.tsx), que ve lo que
 * atrapa cualquier límite: este componente solo decide qué pintar.
 */
import { Component, type ReactNode } from 'react';
import { Boton, Vacio } from '../ui';

interface Props {
  /** Qué decir cuando algo de dentro falla. */
  mensaje: string;
  /** Cuando cambia, se vuelve a intentar pintar. */
  reinicio?: unknown;
  /** Ofrece un botón «Recargar». Para el límite de toda la web, que no se recupera sola. */
  recargable?: boolean;
  children: ReactNode;
}

export class LimiteError extends Component<Props, { fallo: boolean }> {
  state = { fallo: false };

  // React ya cuenta el fallo por consola; aquí solo se decide qué pintar.
  static getDerivedStateFromError() {
    return { fallo: true };
  }

  componentDidUpdate(anterior: Props) {
    if (this.state.fallo && anterior.reinicio !== this.props.reinicio) this.setState({ fallo: false });
  }

  render() {
    if (!this.state.fallo) return this.props.children;
    return (
      <Vacio error>
        {this.props.mensaje}
        {this.props.recargable && (
          <>
            <br />
            <Boton onClick={() => location.reload()}>Recargar</Boton>
          </>
        )}
      </Vacio>
    );
  }
}
