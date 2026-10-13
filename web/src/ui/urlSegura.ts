/**
 * Las direcciones que llegan de Smoothcomp (cuadros, retransmisiones, el evento) acaban en
 * un `href`. React escapa el texto pero no impide `javascript:`, así que todo enlace de la
 * librería pasa por aquí: solo se admite `https://`.
 */
export function esUrlSegura(url: string | null | undefined): url is string {
  return /^https:\/\//i.test(url ?? '');
}
