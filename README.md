# champions2paste

Convierte capturas de pantalla de un equipo de **Pokémon Champions** en un
**pokepaste** válido para **Pokémon Showdown**.

Subes una o dos capturas de la pantalla *"Replicate This Battle Team?"*, se leen
por OCR, cada nombre se ancla contra el vocabulario real de Showdown, y sale el
texto listo para pegar en el Teambuilder.

Corre entero en un NAS modesto: **sin GPU, sin internet y sin coste**. No usa
ningún modelo de lenguaje.

```
Salamence (F) @ Salamencite          Kingambit (M) @ Chople Berry
Ability: Intimidate                  Ability: Defiant
Level: 50                            Level: 50
EVs: 9 HP / 25 SpA / 32 Spe          EVs: 32 HP / 19 Atk / 2 Def / 4 SpD / 9 Spe
Timid Nature                         Adamant Nature
- Draco Meteor                       - Kowtow Cleave
- Hyper Voice                        - Iron Head
- Tailwind                           - Sucker Punch
- Protect                            - Low Kick
```

---

## Cómo se usa

Las capturas entran de tres formas: **arrastrándolas**, **haciendo clic** para
elegir fichero, o **pegándolas con Ctrl+V** desde el portapapeles. Cada hueco
tiene una × para vaciarlo, y puedes arrastrar una imagen de un hueco al otro.

Hay dos pestañas en el juego que interesan:

- **Moves & More** — especies, géneros, habilidades, objetos y movimientos.
- **Stats** — puntos invertidos (SP) y naturaleza.

**El orden da igual y ninguna es obligatoria.** Cada captura se reconoce por la
pestaña que tiene resaltada en verde, no por el hueco donde la pongas:

| Subes | Obtienes |
|---|---|
| Las dos | El paste completo |
| Solo *Moves & More* | El equipo sin spreads |
| Solo *Stats* | Especies, SP y naturalezas, sin movimientos |

Tras la conversión aparece un editor con todo lo leído. Los campos que el
diccionario tuvo que corregir salen en **ámbar** y los que no reconoció en
**rojo**, con el aviso escrito debajo. Corregir a mano no vuelve a llamar al OCR.

---

## Por qué la entrada son capturas y no el código del juego

El código replica que da Champions (`P302HFTLGP`) **no contiene el equipo**: es
un identificador que se resuelve contra los servidores del juego.

Diez caracteres alfanuméricos son unos 51 bits de información. Seis Pokémon con
objeto, habilidad, naturaleza, cuatro movimientos y spread necesitan varios
cientos. La información no está ahí, así que ninguna herramienta local puede
descifrarlo — por muy buena que sea. De ahí que se parta de capturas.

---

## El sistema de estadísticas de Champions

Champions no usa EVs ni IVs clásicos, y la herramienta trabaja en su escala:

- Cada estadística admite de **0 a 32 SP**, y el total de cada Pokémon es
  **siempre 66**.
- **No hay IVs**: equivalen a 31. Por eso el paste no emite línea `IVs:`, que es
  justo lo que Showdown asume cuando falta.
- **La naturaleza no se escribe en ninguna parte**: se deduce de las flechas
  rosas hacia arriba (potenciada) y azules hacia abajo (reducida).
- Los combates son a **nivel 50**.

El paste lleva los SP **en crudo**, que es lo que esperan los formatos de
Champions en Showdown. El interruptor *EVs clásicos (×8)* los convierte a la
escala antigua (1 SP = 8 EVs, tope 252) para calculadoras que aún la usan; en ese
modo avisa de que el spread supera los 508 EVs, porque 66 SP equivalen a 528.

### Megaevolución

Champions permite megaevolución, y la herramienta trata las piedras como
cualquier otro objeto, conservando la **habilidad de la forma base**
(`Intimidate`, no `Aerilate`), que es lo que Showdown espera.

---

## Cómo funciona

No hay modelo de lenguaje ni prompt: el resultado es determinista y no puede
inventarse un dato. La pantalla del juego siempre se dibuja igual, así que cada
dato se busca donde está.

1. **Las seis tarjetas se localizan por color** (moradas sobre fondo amarillo) y
   se ordenan como las numera el juego. La pestaña activa se detecta por su
   resaltado verde, de ahí que el orden de subida no importe.

2. **El texto** (especie, habilidad, objeto, movimientos) se lee en dos pasadas:
   una detección sobre la imagen completa acota dónde está cada texto, y luego el
   reconocedor lee esos recortes ajustados en un solo lote. Por separado ninguna
   de las dos sirve: el detector parte los nombres de dos palabras y el
   reconocedor se degrada si el recorte lleva mucho fondo vacío.

3. **Los números se autocalibran con la barra** de cada estadística, que se aísla
   por color. El número grande queda a su izquierda y el pequeño a su derecha,
   siempre a la misma distancia medida en anchos de barra. Esto evita depender de
   posiciones fijas: un par de píxeles de diferencia al detectar una tarjeta
   bastaban para cortar el último dígito.

4. **El género y la naturaleza no usan OCR**: son un recuento de píxeles. El
   símbolo de género por su color, y las flechas en la banda del nombre de cada
   estadística.

### Cuatro señales que se corrigen entre sí

Un OCR se equivoca. Lo que hace fiable el resultado es que cada dato se contrasta
con algo independiente:

- **El diccionario cerrado de Showdown** corrige el texto. El vocabulario real
  (1416 especies, 951 movimientos, 583 objetos, 321 habilidades) se hornea en la
  imagen desde `play.pokemonshowdown.com`, y cada cadena leída se ancla al nombre
  canónico más cercano con un umbral que escala con la longitud de la palabra:
  `'Grsy Surge'` → `Grassy Surge`, `'Chople Bery'` → `Chople Berry`.

- **La longitud de la barra** contrasta cada número de SP. Su error medio es de
  0.06 puntos y nunca pasa de 2, así que cuando el número leído se aleja más de
  eso, el OCR ha perdido un dígito (un `17` leído como `7`) y manda la barra.

- **El checksum de los 66 SP** delata cualquier número que siga mal.

- **El recálculo de las estadísticas** cierra el círculo: con las estadísticas
  base, los SP, la naturaleza, nivel 50 e IVs 31, el valor final es determinista.
  Si no cuadra con el número grande de la pantalla, algo se leyó mal.

Nada se corrige a espaldas del usuario: toda corrección aparece como aviso.

### Precisión medida

Sobre las dos capturas reales del fixture, comparando los 96 campos (especie,
género, habilidad, objeto, 4 movimientos, 6 SP y las 2 flechas de cada Pokémon):

```
96/96 campos correctos (100.0%)
```

En unos 3 segundos de extremo a extremo en una CPU de escritorio.

La conversión de escala está verificada aparte: los **36 valores** de estadística
que muestran las seis tarjetas se reproducen exactamente con la fórmula del
juego (1 SP = 8 EVs, IVs 31, nivel 50, multiplicador de naturaleza).

---

## Despliegue

```bash
docker compose up -d --build
```

La web queda en `http://<ip>:8321`. No hay nada que configurar: el motor `ocr`
viene por defecto y corre dentro del contenedor.

Notas comprobadas construyendo y ejecutando la imagen:

- **El build necesita internet una sola vez**: `scripts/build_dex.py` descarga
  los nombres canónicos de Showdown y los hornea en la imagen. Después el
  contenedor funciona aislado.
- **La imagen pesa ~740 MB** (onnxruntime, opencv y numpy). Es disco, no memoria.
- **Todas las dependencias tienen rueda `manylinux aarch64`**, así que en un NAS
  ARM se instalan sin compilar. Los modelos ONNX (13 MB) viajan dentro del
  paquete de Python: no se descarga nada al arrancar.
- **Con `docker-compose` v1** (el binario antiguo con guion), reconstruir sobre
  un contenedor existente da `ERROR: 'ContainerConfig'`. Es un fallo conocido de
  esa versión contra Docker moderno: `docker-compose down` antes de levantar.

### En un Synology (GUI, sin SSH)

1. **File Station** → sube el proyecto a la carpeta `docker` y descomprímelo.
2. **Container Manager** → *Proyecto* → *Crear*, apuntando a esa carpeta.
   Detecta el `docker-compose.yml` solo.
3. Deja **sin marcar** *"Set up web portal via Web Station"*: estorba si vas a
   publicar por proxy inverso o túnel.

En una CPU ARM el build puede tardar 10-20 minutos. No compila nada, pero
descomprimir las ruedas en ese hardware es lento.

### Publicarlo con un dominio propio

Con **Cloudflare Tunnel** no hace falta abrir puertos ni exponer la IP de casa, y
el certificado lo pone Cloudflare. Un túnel sirve tantos hostnames como quieras,
así que si ya tienes uno, basta con añadirle una ruta:

| Campo | Valor |
|---|---|
| Subdomain | `champions2paste` |
| Type | `HTTP` |
| URL | `localhost:8321` *(si cloudflared usa `network_mode: host`)* |

El frontend usa solo rutas relativas, así que funciona detrás de un proxy sin
tocar nada.

Dos avisos: si el dominio es un **`.dev`**, los navegadores fuerzan HTTPS por
HSTS precargado y no hay forma de servirlo por HTTP plano. Y el plan gratuito de
Cloudflare **corta las peticiones a los 100 segundos** (error 524), lo que
importa si el OCR en tu hardware se acerca a ese tiempo.

---

## Desarrollo local

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/build_dex.py          # cachea data/dex.json
.venv/bin/uvicorn app.main:app --reload --port 8321
```

## Pruebas

```bash
.venv/bin/python tests/test_pipeline.py    # normalización y renderizado
.venv/bin/python tests/test_ocr.py         # precisión del OCR, campo a campo
node tests/test_clipboard.js               # pegado y arrastre entre huecos
```

`test_ocr.py` es el que importa al tocar el motor: compara los 96 campos contra
la transcripción real del fixture, así que cualquier regresión salta ahí.
`test_clipboard.js` extrae las funciones directamente de `index.html` para no
quedarse desincronizado con la interfaz.

## Estructura

```
app/
  main.py          API HTTP (FastAPI)
  dex.py           vocabulario de Showdown y anclaje tolerante a erratas
  champions.py     modelo de estadísticas del juego y conversión a Showdown
  paste.py         normalización, avisos y renderizado del pokepaste
  schema.py        forma de los datos que devuelve el motor de visión
  vision/
    ocr.py         motor por defecto: geometría + OCR + color
    ollama.py      alternativa con modelo local (sin verificar)
    claude.py      alternativa con la API de Anthropic (sin verificar)
  static/index.html  interfaz completa, sin dependencias externas
scripts/build_dex.py  descarga y cachea los nombres canónicos
tests/fixtures/       capturas reales y su transcripción
```

## API

| Endpoint | Qué hace |
|---|---|
| `POST /api/extract` | 1-2 imágenes (multipart) → equipo leído, normalizado y paste |
| `POST /api/render` | Equipo editado (JSON) → re-normaliza y re-renderiza |
| `GET /api/vocab` | Nombres canónicos, para el autocompletado del editor |
| `GET /api/health` | Estado y motor activo |

## Variables de entorno

| Variable | Por defecto | Para qué |
|---|---|---|
| `VISION_BACKEND` | `ocr` | `ocr`, `ollama` o `claude` |
| `MAX_IMAGE_BYTES` | `8388608` | Tamaño máximo por captura |
| `OLLAMA_HOST` | `http://localhost:11434` | Solo con `ollama` |
| `OLLAMA_MODEL` | `qwen3-vl:8b` | Solo con `ollama` |
| `ANTHROPIC_API_KEY` | — | Solo con `claude` |
| `ANTHROPIC_MODEL` | `claude-opus-5` | Solo con `claude` |

La versión de `rapidocr-onnxruntime` está **fijada a la 1.2.3**. No es purismo:
la 1.4 reorganizó su API interna y dejó de exponer `text_detector` /
`text_recognizer`, que son las dos piezas que este motor usa por separado para
acotar primero y leer después. Si se instala una versión que no las trae, el
motor lo dice con un mensaje claro en lugar de fallar por dentro.

---

## Limitaciones conocidas

**La precisión está medida sobre un solo equipo.** Seis Pokémon, 96 campos, una
sola resolución (1998×922). La geometría se expresa en fracciones de la tarjeta
detectada y los números se autocalibran con la barra, así que debería aguantar
otras resoluciones — pero eso **no está comprobado**.

**Los motores `ollama` y `claude` nunca se han ejecutado.** Comparten un prompt
calibrado contra la maquetación real del juego, pero no había ni GPU ni
credenciales para probarlos. El motor `ocr`, que es el que viene por defecto, sí
está verificado de principio a fin.

**El Teracristal no se lee**, porque no aparece en ninguna de las dos pestañas
capturadas. El campo existe en el esquema y en el editor por si el juego lo
muestra en algún sitio que aún no he visto.
