/* Executive report: browser print only ("Imprimir > Salvar como PDF"). */
(() => {
  'use strict';
  document.querySelectorAll('[data-print]').forEach(button => {
    button.addEventListener('click', () => window.print());
  });
})();
