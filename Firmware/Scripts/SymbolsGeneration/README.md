# Asset ST7789: PNG/SVG -> C o binario

`generate_assets.py` sostituisce il vecchio convertitore SSD1306. Richiede
Pillow (e CairoSVG per gli SVG) e legge `assets.json`. Genera `assets_generated.h`
e `.c` per gli asset interni, file `.bin` per quelli destinati alla Flash esterna. Nessun file
custom viene cercato o modificato dal Python. Ogni esecuzione rigenera l'intero
registro. Il Makefile esegue lo stesso comando, senza build del firmware.

Mettere i PNG RGBA o gli SVG sorgenti in `source/`, conservando gli originali.
Poi compilare la lista nel JSON, per esempio:

```json
{
  "output_dir": "../../EFES_FW_HumanSide/customLibs/ST7789/Assets",
  "binary_output_dir": "../../ExternalFlash/Assets",
  "assets": [
    {
      "name": "STEERING_WHEEL",
      "file": "source/steering_wheel.png",
      "size": 80,
      "output": "c",
      "format": "palette4_alpha4"
    },
    {
      "name": "STARTUP",
      "file": "source/startup.svg",
      "size": [320, 240],
      "output": "bin",
      "format": "rgb565",
      "background": "#091322"
    }
  ]
}
```

Non ci sono immagini sostitutive. Il nome deve
essere un identificatore C maiuscolo e univoco, senza il prefisso ASSET_.
I percorsi sono relativi al JSON, oppure assoluti; i file possono essere PNG RGBA
oppure SVG. Per usare un SVG basta indicarlo in `file`, per esempio
`"file": "source/logo.svg"`; il resto della configurazione resta uguale.

Gli SVG vengono rasterizzati direttamente alla risoluzione richiesta e
convertiti in RGBA in memoria. Da quel punto seguono la stessa conversione
dei PNG; non viene creato un PNG intermedio sul disco. Usare un `viewBox`
corretto per mantenere le proporzioni. Senza `size` si usano le dimensioni
intrinseche dello SVG: specificarle nel file oppure indicare `size` nel JSON.
Per risultati portabili usare SVG autosufficienti e convertire eventuali
scritte in tracciati.

Dipendenze: `python3 -m pip install -r requirements.txt` nell'ambiente Python
usato per il generatore. I soli PNG continuano a richiedere soltanto Pillow.

```sh
cd ~/Scuola/EFES_Project/Firmware/Scripts/SymbolsGeneration
python3 generate_assets.py
python3 generate_assets.py --size 72
```

`--size N` ha precedenza sulle dimensioni nel JSON. Il resize viene fatto prima
della conversione, con Lanczos, mantenendo le proporzioni e centrando l'immagine
in un quadrato trasparente NxN. Se size manca sia nella CLI sia nella voce JSON,
si conservano esattamente le dimensioni originali. Per esportare 64, 72 e 80 px
insieme, creare tre voci con nomi diversi, stesso file e size differenti.
Non c'è scaling nel renderer C.

Nel JSON `size` accetta anche `[larghezza, altezza]`: riquadro esatto,
proporzioni mantenute e immagine centrata. Il comando `--size N` continua a
imporre un quadrato a tutte le voci. Senza `output` e `format` rimangono i
default `c` e `palette4_alpha4`, compatibili con i vecchi JSON.

`--config /percorso/assets.json` e `--output /percorso/Assets` cambiano input
e cartella di destinazione. Il Python non modifica CMake o il codice della UI.
`--binary-output` cambia la cartella dei binari. Nel JSON `output_dir` e
`binary_output_dir` configurano le due cartelle una volta sola, con percorsi
relativi al JSON; gli argomenti CLI hanno precedenza.

## Formati e destinazioni

`output` e `format` sono indipendenti: entrambi i formati sono esportabili
come C o binario. Tutti i file binari restano esclusi dal registro C.
`output: "bin"` prepara un file sul PC: non programma la memoria né invia
dati UART. Il programma di caricamento e la lettura nel firmware applicativo
sono passaggi separati ancora da implementare.

### `palette4_alpha4`

- Tutti i 16 indici sono disponibili per i colori, inclusi i pixel semitrasparenti.
- Quantizzazione median-cut, senza dithering; palette di 16 valori RGB565.
- Alpha del PNG arrotondato a 16 livelli: 0 trasparente, 15 opaco.
  Il resize Lanczos conserva le semitrasparenze dei bordi prima della conversione.
- Un byte per pixel: indice colore nel nibble alto, alpha nel nibble basso.
  Righe consecutive, stride uguale alla larghezza in byte.
- Palette, bitmap e descrittori sono `const`, conservati nella Flash.

Un asset 80x80 occupa 6400 byte di bitmap + 32 di palette, oltre al descrittore.
La palette usa valori RGB565 nativi: il renderer prepara i byte SPI nei propri
buffer, senza decomprimere l'immagine intera in RAM.

Ogni immagine ha una propria palette da 32 byte. Il registro C e il renderer
esistenti `Assets` / `ST7789_DrawAsset` rimangono invariati per questo formato.

### `rgb565`

Due byte per pixel, prima il byte più significativo, senza palette né alpha.
La trasparenza viene composta su `background` (nero se omesso).
320×240 occupa 153600 byte di pixel. Per `output: "c"` i dati vengono raccolti
nel registro separato `RGB565Assets`, con descrittori `RGB565Asset`: non sono
`GraphicAsset` e non si passano a `ST7789_DrawAsset`. I byte sono già in ordine
SPI, coerente con `ST7789_DrawImage`; resta al chiamante rispettare il contratto
di quell'API, oppure usare `ST7789_DrawRectanglePixels` con un callback che
ricomponga ciascun colore come `(data[2*i] << 8) | data[2*i+1]`.

### File binario, versione 1

Ogni `NOME.bin` contiene un'intestazione di **24 byte**, seguita dal payload.
Campi dell'intestazione in little-endian, senza padding:

| Offset | Tipo | Significato |
| --- | --- | --- |
| 0 | 4 byte | Magic ASCII `EFAS` |
| 4 | uint8 | Versione: 1 |
| 5 | uint8 | Formato: 1 = palette4_alpha4, 2 = rgb565 |
| 6 | uint16 | Larghezza |
| 8 | uint16 | Altezza |
| 10 | uint16 | Colori palette: 16 oppure 0 |
| 12 | uint32 | Numero di byte dei pixel |
| 16 | uint32 | Numero di byte del payload, inclusa eventuale palette |
| 20 | uint32 | CRC-32 IEEE del payload (`zlib.crc32`) |

Payload a palette: 16 colori RGB565 **big-endian** (32 byte), poi i pixel
indice/alpha. Payload RGB565: soltanto i pixel **big-endian**. Pixel sempre
per righe, dall'alto a sinistra, senza padding. Una splash RGB565 320×240
produce quindi un file da **153624 byte**, intestazione inclusa.
Il firmware dovrà interpretare/saltare l'intestazione: il file intero non è
un'immagine raw da passare direttamente al display.

`assets_binary.json`, generato nella stessa cartella, elenca i file da inviare
dal PC. Non assegna indirizzi nella Flash: la disposizione verrà definita
con il programma di caricamento. Quando si rimuove/rinomina un asset, il
generatore elimina solo i vecchi binari elencati nel precedente indice;
preserva gli altri file della cartella.

Verifica con `make check` (o `python3 -m unittest -v test_generate_assets`).

## Disegno e rotazione

Dopo avere generato il PNG dell'esempio, la chiamata è:

```c
ST7789_DrawAsset(19, 48, ASSET_STEERING_WHEEL, angle_deci_deg, UI_BACKGROUND);
```

Il lato del riquadro è max(larghezza, altezza), con centro fisso. Il riquadro
deve stare sul display. L'angolo è in decimi di grado, positivo in senso orario;
zero disegna l'asset non ruotato. Rotazione inversa con filtro bilineare RGB565 sui quattro pixel vicini.
Ogni campione viene mescolato con background usando il suo alpha prima
dell'interpolazione; fuori immagine si usa background. Anche a rotazione zero
le semitrasparenze ammorbidiscono i bordi. Seno e coseno sono calcolati una volta per richiesta; nei blocchi
si usano moltiplicazioni intere e letture della palette.

Trasparenza e pixel fuori dall'immagine diventano il colore background passato
alla funzione. Non preservano disegni preesistenti sotto l'asset: il riquadro è
opaco e può così cancellare la posa precedente su uno sfondo uniforme.
Il trasferimento rimane RGB565: il formato a 8 bit riduce la Flash rispetto
a RGB565 con alpha separato, non i byte sul bus SPI. I vecchi asset a 4 bpp
devono essere rigenerati: il renderer usa solo il nuovo formato.

Per il volante, preparare un PNG quadrato con corona e razze dentro il cerchio
inscritto, lasciando trasparenti gli angoli. Il riquadro non si allarga ruotando:
gli angoli di un'immagine rettangolare piena possono venire tagliati.
La Home usa DrawAsset per il volante e per le icone statiche. La vecchia
primitiva geometrica rimane disponibile, senza selezione automatica tra le due.

Come le altre primitive: una richiesta alla volta, controllare OK/BUSY e
continuare a chiamare ST7789_Process a ogni giro del main. Nessun framebuffer,
allocazione dinamica o preparazione pixel nell'ISR.
