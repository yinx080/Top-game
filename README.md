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

El diseño se realizara en react, se debera hacer un diseño para el menu y dentro de las salas tendra otro. El menu sera simple con dos seleccionables el menu de busqueda y el menu de ajustes (sonido, ...), dentro de las salas tendra un diseño siempre igual. Habra una mesa en mitad bastante grande que ocupe toda la pantalla con las cartas sobre la mesa (o nada si no hay cartas), cuando se pongan las cartas de los jugadores apareceran boca abajo, de manera que la posicion es arbitraria, ya que la primera carta que se ponga aparecera en medio de la mesa y la siguiente se podra colocar o a la izquierda o a la derecha, y en la tercera carta se podra colacar igualmente a la izquierda o la derecha de cualquier carta de manera que permita colocar las cartas entre ellas. Cada carta tiene arriba la respuesta del jugador de manera que siempre se pueda ver las respuestas de todos los jugadores en todo momento. Cuando el juego termina simplemente se dan la vuelta las cartas de manera incremental, se empieza por la "menor" y termina por la "mayor". 

Cada jugador vera la mesa en su pantalla, pero tambien vera un modelo en 2d de la carta que le ha tocado de manera que se imite la posición de tener una carta en la mano, cuando el jugador coloque la carta, el jugador solo vera la mesa con las cartas boca abajo.

En cada partida se vera el tema arriba a la derecha de la pantalla, el sistema de temas sera un poco diferente, el juego puede tener temas aleatorios predeterminados, pero en cada sala los jugadores podran proponer un tema para la siguiente ronda y cuando propongan uno (o no), entre todos votan el tema de la siguiente ronda entre los propuestos.
