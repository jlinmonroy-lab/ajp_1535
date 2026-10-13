import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Boton } from '../Boton/Boton';
import { Campo } from '../Campo/Campo';

export interface AccesoAdminProps {
  /** Este dispositivo ya tiene la clave: el enlace pasa a ser «Administrador · Salir». */
  sesionIniciada: boolean;
  /** Recibe la clave. Devuelve true si se acepta, false si se rechaza (vacía el campo) o null si no se pudo saber. */
  onEntrar: (clave: string) => Promise<boolean | null>;
  onSalir: () => void;
}

/** Enlace discreto al pie del inicio que despliega el campo de la clave de administrador; con sesión iniciada, sirve para salir. */
export function AccesoAdmin({ sesionIniciada, onEntrar, onSalir }: AccesoAdminProps) {
  const [abierto, setAbierto] = useState(false);
  const [clave, setClave] = useState('');
  const [comprobando, setComprobando] = useState(false);
  const campo = useRef<HTMLInputElement>(null);

  useEffect(() => { if (abierto) campo.current?.focus(); }, [abierto]);

  async function enviar(ev: FormEvent) {
    ev.preventDefault();
    const limpia = clave.trim();
    if (!limpia) return;
    setComprobando(true);
    try {
      const valida = await onEntrar(limpia);
      if (valida === false) setClave('');
    } finally {
      setComprobando(false);
    }
  }

  return (
    <div className="fc-pie-admin">
      <Boton variante="enlace" onClick={sesionIniciada ? onSalir : () => setAbierto((a) => !a)}>
        {sesionIniciada ? 'Administrador · Salir' : 'Acceso de administrador'}
      </Boton>
      {abierto && !sesionIniciada && (
        <form className="fc-tarjeta fc-form-grupo" autoComplete="off" onSubmit={enviar}>
          <Campo
            ref={campo}
            name="clave"
            type="password"
            required
            placeholder="Clave de administrador"
            aria-label="Clave de administrador"
            autoComplete="off"
            value={clave}
            onChange={(ev) => setClave(ev.target.value)}
          />
          <Boton type="submit" activo disabled={comprobando}>Entrar</Boton>
        </form>
      )}
    </div>
  );
}
