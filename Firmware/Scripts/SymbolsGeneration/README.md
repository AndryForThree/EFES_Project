# Asset ST7789: PNG RGBA -> indice colore 4 bit + alpha 4 bit

`generate_assets.py` sostituisce il vecchio convertitore SSD1306. Richiede
Pillow e legge `assets.json`. Scrive solo `assets_generated.h` e `.c`, nella
cartella `Firmware/EFES_FW_HumanSide/customLibs/ST7789/Assets/`. Nessun file
custom viene cercato o modificato dal Python. Ogni esecuzione rigenera l'intero
registro. Il Makefile esegue lo stesso comando, senza build del firmware.

Mettere i PNG sorgenti in `source/`, conservando gli originali ad alta risoluzione.
Poi compilare la lista nel JSON, per esempio:

```json
{
  "assets": [
    {
      "name": "STEERING_WHEEL",
      "file": "source/steering_wheel.png",
      "size": 80
    }
  ]
}
```

Non ci sono immagini sostitutive. Il nome deve
essere un identificatore C maiuscolo e univoco, senza il prefisso ASSET_.
I percorsi sono relativi al JSON, oppure assoluti; i file devono essere PNG RGBA.

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

`--config /percorso/assets.json` e `--output /percorso/Assets` cambiano input
e cartella di destinazione. Il Python non modifica CMake o il codice della UI.

## Formato unico

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
