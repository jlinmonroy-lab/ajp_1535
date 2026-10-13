/* El commit con el que se compiló la web (`GIT_SHA` al construir la imagen), o "dev" si se
   compila sin él. Sale en la pantalla de error y en los informes que llegan al servidor. */
export const BUILD: string = typeof __BUILD__ === 'string' ? __BUILD__ : 'dev';
