/** Une nombres de clase CSS ignorando los vacíos (`false`, `null`, `undefined`, `''`). */
export function clases(...partes: Array<string | false | null | undefined>): string {
  return partes.filter(Boolean).join(' ');
}
