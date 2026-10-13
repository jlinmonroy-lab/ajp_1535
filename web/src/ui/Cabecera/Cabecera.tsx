import { useState, type ReactNode } from 'react';
import { Boton } from '../Boton/Boton';
import { clases } from '../clases';

export interface CabeceraProps {
  /** `normal` (por defecto) o `inicio`: a todo el ancho, con título y logo más grandes. */
  variante?: 'normal' | 'inicio';
  titulo: string;
  /** Dirección del logo (cuadrado, ~160 px). Si falta o no carga, se omite sin dejar hueco. */
  logo?: string;
  /** Con él aparece el botón «‹» de volver. */
  onVolver?: () => void;
  /** Con una dirección `https://` aparece el botón «↗» que abre el evento en Smoothcomp. */
  enlaceEvento?: string;
  /** Con él aparece el botón «↻» de actualizar ahora. */
  onRecargar?: () => void;
  /** Va debajo de la fila: normalmente una `LineaEstado`. */
  children?: ReactNode;
}

/**
 * Cabecera fija de la página: logo, título (una línea, con «…») y, según los datos que se le
 * pasen, botones de volver, abrir en Smoothcomp y actualizar. Borde inferior con el color del equipo.
 *
 * Variantes:
 * - `normal`: la de las pantallas de evento; se centra en 720 px desde 640 px de ancho.
 * - `inicio`: la de la pantalla de inicio; ocupa todo el ancho en cualquier pantalla, con el logo de
 *   48 px y el título a 1,75 rem, que puede ocupar varias líneas en lugar de cortarse con «…».
 */
export function Cabecera({ variante = 'normal', titulo, logo, onVolver, enlaceEvento, onRecargar, children }: CabeceraProps) {
  const [logoRoto, setLogoRoto] = useState(false);

  return (
    <header className={clases('fc-cabecera', variante === 'inicio' && 'fc-cabecera--inicio')}>
      <div className="fc-cabecera-fila">
        {onVolver && (
          <Boton variante="icono" title="Volver a los eventos" aria-label="Volver a los eventos" onClick={onVolver}>
            &#8249;
          </Boton>
        )}
        {logo && !logoRoto && (
          <img
            className="fc-logo"
            src={logo}
            alt=""
            width={40}
            height={40}
            onError={() => setLogoRoto(true)}
          />
        )}
        <h1 className="fc-cabecera-titulo">{titulo}</h1>
        {enlaceEvento && (
          <Boton
            variante="icono"
            href={enlaceEvento}
            title="Ver el evento en Smoothcomp"
            aria-label="Ver el evento en Smoothcomp"
          >
            &#8599;
          </Boton>
        )}
        {onRecargar && (
          <Boton variante="icono" title="Actualizar ahora" aria-label="Actualizar ahora" onClick={onRecargar}>
            &#8635;
          </Boton>
        )}
      </div>
      {children}
    </header>
  );
}
