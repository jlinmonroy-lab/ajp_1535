import { Tarjeta } from '../Tarjeta/Tarjeta';
import { TextoTenue } from '../TextoTenue/TextoTenue';

/** Tarjeta dorada que explica que el organizador aún no ha publicado el schedule: sin atletas ni combates que enseñar. */
export function AvisoSinSchedule() {
  return (
    <Tarjeta borde="oro">
      <strong>El schedule aún no está publicado.</strong>
      <br />
      <TextoTenue como="span">
        El organizador todavía no ha publicado los cuadros ni los horarios,
        así que no hay atletas ni combates que enseñar. Esta pantalla lo vuelve a comprobar sola.
      </TextoTenue>
    </Tarjeta>
  );
}
