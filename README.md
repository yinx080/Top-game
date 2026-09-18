# Top Card

Juego de cartas **cooperativo** para el navegador. Cada jugador recibe una carta
que nadie más ve, el grupo vota un tema, y por turnos cada uno coloca su carta
boca abajo donde cree que encaja dentro del top acompañándola de una palabra. Al
final se destapan una a una: si quedan ordenadas de menor a mayor, gana el grupo
entero.

React + Three-less CSS 3D en el frontend, FastAPI + WebSocket en el backend, sin
registro de usuarios ni base de datos.

---

## Cómo ejecutarlo

Necesitas **Python 3.11+** y **Node 20+**.

### Desarrollo

```powershell
.\dev.ps1          # Windows: abre backend y frontend en dos ventanas
```

O a mano, en dos terminales:

```bash
# terminal 1
cd backend
pip install -r requirements-dev.txt
python -m uvicorn app.main:app --reload --port 8000

# terminal 2
cd frontend
npm install
npm run dev        # http://localhost:5173
```

Vite hace de proxy de `/api` y `/ws` hacia el backend, así que se juega desde
`http://localhost:5173`.

### Producción (un solo proceso)

```bash
cd frontend && npm run build          # genera frontend/dist
cd ../backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Si existe `frontend/dist`, FastAPI lo sirve él mismo y todo queda en el puerto
8000, sin CORS ni proxy de por medio.

### Jugar tú contra bots

Para probar la partida entera sin reunir a cuatro personas, `scripts/bots.py`
mete jugadores automáticos que proponen tema, votan, colocan su carta según su
valor (con algo de ruido, para que también fallen) y sueltan alguna frase por el
chat.

```bash
# Creas tú la sala en el navegador y metes bots con su código.
# Eres el anfitrión: tú decides cuándo empieza cada ronda.
python scripts/bots.py --code AB3K9P --bots 3

# O que abran ellos la sala y te pasen el enlace: la ronda arranca en
# cuanto entras, y encadenan las siguientes solas.
python scripts/bots.py --bots 3
```

Opciones útiles: `--pace 0.5` para que reaccionen rápido, `--password` si la
sala es privada, `--base` si el backend no está en el 8000. Se paran con Ctrl+C.

### Comprobaciones

```bash
cd backend && python -m pytest        # 57 tests: reglas, chat, API y partida por WebSocket
cd frontend && npm run typecheck
python scripts/play_demo.py --players 5          # partida completa contra un servidor vivo
python scripts/play_demo.py --players 5 --smart  # colocando bien: debe ganar
```

`scripts/build_assets.py` regenera las cartas y la textura a partir de `data/`
(sólo hace falta si se cambian los originales).

---

## Arquitectura

```
navegador ──REST──►  /api/rooms…      listar, buscar, crear y entrar en salas
          ──WS────►  /ws/{código}     todo lo que pasa dentro de la partida
```

**Backend** (`backend/app/`)

| Fichero | Qué hace |
| --- | --- |
| `room.py` | Estado de la sala, máquina de estados de la ronda y chat. Sin E/S: aquí viven todas las reglas. |
| `store.py` | Salas en memoria, un `asyncio.Lock` por sala, difusión por WebSocket y barrendero de salas muertas. |
| `views.py` | Serialización **por jugador**. Es donde se garantiza que nadie vea la carta de otro. |
| `ws.py` | Traduce acciones del cliente a llamadas a `room.py` y difunde el resultado. |
| `api.py` | REST del menú. |
| `deck.py`, `topics.py`, `security.py`, `config.py`, `errors.py` | Baraja, fondo de temas, contraseñas y tokens, ajustes, errores de dominio. |

**Frontend** (`frontend/src/`)

| Carpeta | Qué hay |
| --- | --- |
| `screens/` | `Menu` (inicio, buscador, ajustes, crear/entrar) y `Room` (la mesa). |
| `room/` | Piezas de la mesa: carta, cartas colocadas, fichas de jugador, carta en mano, chat y paneles de fase. |
| `state/` | `useSession` (nombre, ajustes y asientos, persistidos) y `useRoom` (estado vivo de la sala). |
| `lib/` | Cliente REST, WebSocket con reconexión, enrutado por hash y sonidos sintetizados. |
| `styles/` | Tokens de diseño y hojas de menú y sala. |

### Ciclo de una ronda

```
lobby ──(anfitrión)──► proposing ──► voting ──► placing ──► revealing ──► result
  ▲                                                                          │
  └──────────────────────── (otra ronda / volver al lobby) ──────────────────┘
```

Cada fase se cierra sola en cuanto han respondido todos los jugadores
conectados; el anfitrión puede adelantarla si alguien se demora. El destape lo
marca el servidor (una carta cada 1,25 s) para que todo el mundo vea el mismo
volteo en el mismo instante.

---

## Decisiones que el enunciado dejaba abiertas

**Sistema de servidores: un único proceso con las salas en RAM.** No hay cuentas
ni historial que guardar, una partida dura minutos y el estado de una sala son
unos pocos kilobytes. Una base de datos sólo añadiría latencia y piezas que
mantener. Cada sala tiene su propio lock, de modo que mutar el estado y difundir
el resultado es atómico y todos los clientes reciben la misma secuencia de
eventos. Si algún día hicieran falta varios procesos, `RoomStore` es la única
pieza a reimplementar (por ejemplo sobre Redis con pub/sub).

**El estado viaja completo en cada cambio.** Es un objeto pequeño y evita toda
una familia de errores de sincronización por parches perdidos. Junto a él va un
evento suelto (`card_placed`, `reveal`, `result`…) que la interfaz usa para saber
qué animar y qué sonido disparar.

**La baraja es la francesa completa: As = 1 … K = 13.** El enunciado numeraba la
K como 12; se ha mantenido su intención (el As es la carta más baja y la K la más
alta) pero con los 13 rangos reales de la baraja. Un valor más sólo reparte mejor
las cartas entre los jugadores y no cambia ninguna regla. Dos jugadores pueden
sacar el mismo valor con palos distintos: el empate está contemplado y sigue
contando como victoria.

**Sin three.js.** El único efecto 3D que pide el diseño es el volteo de la carta,
y eso lo resuelve CSS con `transform-style: preserve-3d` de forma más ligera,
accesible y nítida que un lienzo WebGL. Las cartas son las del set de Freepik
recortadas a PNG con transparencia.

**Reconexión en lugar de expulsión.** Caerse no te echa de la sala: el asiento se
guarda en el navegador, el WebSocket reintenta con espera creciente y la partida
sigue. Si alguien no vuelve en 2 minutos, el barrendero le retira; las cartas que
ya hubiera colocado se quedan en la mesa con su nombre. El anfitrión puede saltar
el turno de quien se haya caído.

**El chat viaja dentro del estado de la sala.** Se conservan los últimos 40
mensajes y van en cada difusión, así que quien entra a mitad de partida ve el
hilo reciente sin un canal aparte ni una petición extra. Cada jugador tiene medio
segundo de espera entre mensajes, suficiente para cortar el spam sin que se note
al escribir normal. El chat no se borra al empezar una ronda nueva.

**Sonido sintetizado, no ficheros.** Los efectos se generan con WebAudio: pesan
cero, no arrastran licencias y suenan exactamente al timbre arcade que pide el
enunciado.

**Tipografía.** *Bungee* para rótulos (letrero de recreativa) y *Chakra Petch*
para la interfaz: arcade reconocible sin caer en la fuente de píxeles ilegible.

---

## Créditos

Cartas y textura de madera: <a href="http://www.freepik.com">Designed by
Macrovector / Freepik</a> (ver `data/*/License*.txt`).

---

# Especificación original

## Proceso de juego

Se utilizarán las cartas de la baraja francesa, donde el número 1 corresponde al As y el 12 a la K.

1. Se reparte una carta aleatoria a cada uno de los jugadores.
2. Se establece un tópico por consenso o elegidos aleatoriamente por la aplicación para realizar el top.
3. De uno en uno, cada jugador debe colocar la carta boca abajo en la posición que estime adecuada dentro del orden creado por el resto de jugadores y decir una palabra que, respecto a ese tópico, considere que merece ese puesto en el top.
4. Una vez se hayan colocado las cartas de todos los jugadores, se desvelan una a una.
5. El grupo ganará si las cartas desveladas se encuentran ordenadas numéricamente (tener en cuenta que un empate también se considera victoria en caso de que las demás cartas sigan ordenadas).

## Reglas básicas 

1. Los jugadores no pueden saber las cartas del resto.
2. Sólo se desvelan las cartas una vez estén todas colocadas.
3. No se puede cambiar la posición de una carta una vez esté colocada.

## Desarrollo

El juego en su primera versión solo estara disponible para navegador, por tanto se debera usar react para hacer el diseño del frontend y python con su framework fastapi para su backend.
Ahora bien, los jugadores crearan salas publicas o privadas, si son publicas saldran en el menu de inicio si son privadas se mostraran en el menu de busqueda con un candado, para poder unirse a
estas salas publicas se debera introducir una contraseña que define el anfitrion. No habra ningun tipo de loggeo de usuarios, solo se debera introducir el nombre de la persona al entrar en la sala.

Las salas se guardaran en el servidor del backend y el sistema de servidores lo debera decidir el llm correspondiente de hacer este sistema.

## Diseño 

El diseño se realizara en react y si se requiere diseño avanzado tambien three.js, se debera hacer un diseño para el menu y dentro de las salas tendra otro. El menu sera simple con dos seleccionables el menu de busqueda y el menu de ajustes (sonido, ...), dentro de las salas tendra un diseño siempre igual. Habra una mesa en mitad bastante grande que ocupe toda la pantalla con las cartas sobre la mesa (o nada si no hay cartas), cuando se pongan las cartas de los jugadores apareceran boca abajo, de manera que la posicion es arbitraria, ya que la primera carta que se ponga aparecera en medio de la mesa y la siguiente se podra colocar o a la izquierda o a la derecha, y en la tercera carta se podra colacar igualmente a la izquierda o la derecha de cualquier carta de manera que permita colocar las cartas entre ellas. Cada carta tiene arriba la respuesta del jugador de manera que siempre se pueda ver las respuestas de todos los jugadores en todo momento. Cuando el juego termina simplemente se dan la vuelta las cartas de manera incremental, se empieza por la "menor" y termina por la "mayor". 

Cada jugador vera la mesa en su pantalla, pero tambien vera un modelo en 2d de la carta que le ha tocado de manera que se imite la posición de tener una carta en la mano, cuando el jugador coloque la carta, el jugador solo vera la mesa con las cartas boca abajo.

En cada partida se vera el tema arriba a la derecha de la pantalla, el sistema de temas sera un poco diferente, el juego puede tener temas aleatorios predeterminados, pero en cada sala los jugadores podran proponer un tema para la siguiente ronda y cuando propongan uno (o no), entre todos votan el tema de la siguiente ronda entre los propuestos. Si un jugador propone un tema y este gana la votación, el tema se guardará entre los temas aleatorios que se propondrán en las siguientes partidas de esa sala.

## Apartado artistico

Se han añadido el estilo de las cartas y el tablero de juego al repositorio, usa esos ejemplos para crear toda la parte de diseño de las salas. Aparte todo el juego tendra una estetica arcade eligiendo una tipografia propia de estos tipos de juego pero no muy exagerada.
