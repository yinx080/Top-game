// Arranca la animación de bienvenida (ver index.html) cuando las cartas y la tipografía
// ya están descargadas y decodificadas. Sin esto, en la primera visita el reloj de la
// animación avanza mientras las imágenes siguen llegando y sólo se ve el final.
// Va en un fichero aparte porque la política de seguridad no permite scripts en línea.
(function () {
  var boot = document.getElementById('boot');
  if (!boot) return;
 
  var started = false;
  function start() {
    if (started) return;
    started = true;
    boot.setAttribute('data-start', String(performance.now())); // lo lee dismissBoot()
    boot.classList.add('is-go');
  }
 
  var jobs = [];
  var imgs = boot.querySelectorAll('img');
  for (var i = 0; i < imgs.length; i++) {
    var img = imgs[i];
    jobs.push(img.decode ? img.decode().catch(function () {}) : Promise.resolve());
  }
  if (document.fonts && document.fonts.load) {
    jobs.push(document.fonts.load('1em Bungee', 'TOPCARDS').catch(function () {}));
  }
 
  Promise.all(jobs).then(start, start);
  // Conexión muy lenta o algo bloqueado: no dejes la pantalla vacía más de esto.
  setTimeout(start, 1200);
})();
 