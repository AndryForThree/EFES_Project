# Generatore di font proporzionali

Genera esclusivamente `fonts_generated.h` e `fonts_generated.c`: enum `FontId`,
registro `Fonts`, metriche `FontGlyph` e bitmap con copertura a 4 bit. Non modifica
il driver. Non applica kerning e non cerca font di sistema.

1. Installare Pillow nell'ambiente Python usato: `python3 -m pip install pillow`.
2. Mettere i `.ttf` / `.otf` in `baseFonts/`, conservando le licenze.
3. Elencare font e dimensioni in `fonts.json`.
4. Dalla cartella dello script eseguire:

```sh
python3 generate_font.py
```

La destinazione è `Firmware/EFES_FW_HumanSide/customLibs/ST7789/Fonts/`.
Ogni esecuzione ricrea entrambi i file usando tutta la lista nel JSON.

Git conserva i TTF effettivamente usati da `fonts.json`, le relative licenze,
lo script, il JSON e i C/H generati. Le altre varianti scaricate in `baseFonts/`
restano locali e sono ignorate. Se aggiungi un nuovo file sorgente al JSON,
aggiungi anche la sua eccezione nella sezione font del `.gitignore` principale.
Cambiare solo dimensione o intervallo di un font già presente non richiede
modificare il `.gitignore`. I C/H generati permettono di compilare il firmware
senza eseguire Python; i TTF servono quando vuoi rigenerarli.

Per scegliere configurazione o destinazione diverse:

```sh
python3 generate_font.py --config /percorso/fonts.json --output /percorso/Fonts
```

## Configurazione

- `name`: nome C maiuscolo e univoco, senza il prefisso `FONT_`.
- `file`: percorso TTF/OTF relativo al JSON oppure assoluto. Deve esistere.
- `size`: dimensione richiesta a Pillow in pixel. L'altezza effettiva della
  riga dipende dal font e dai caratteri esportati, ed è stampata alla fine.
- `first_char`, `last_char`: intervallo inclusivo opzionale; default 32..126,
  valori ammessi 0..255. Per il grado usare `last_char: 176`.

Il formato è unico: font proporzionali antialias con 4 bit di copertura per
pixel. La scala di grigi prodotta da Pillow viene quantizzata in 16 livelli:
0 è sfondo, 15 è testo pieno. Non c'è una soglia binaria né l'opzione --threshold.

## Metriche generate

Ogni FontGlyph contiene offset nella bitmap, larghezza, altezza, avanzamento
orizzontale e offset x/y. L'avanzamento di ogni carattere viene arrotondato al
pixel più vicino, indipendentemente dal carattere adiacente: niente kerning.
Gli offset conservano bearings e allineamento verticale. Tutti i glifi di un
font condividono la baseline e l'altezza di riga FontInfo.height.

Le bitmap contengono solo il rettangolo del singolo glifo: righe dall'alto al
basso, due pixel per byte, primo nel nibble alto. Righe allineate a byte; se
la larghezza è dispari, l'ultimo nibble è zero. Non c'è un limite di 16 pixel.
Per un carattere supportato e coordinate interne alla sua bitmap:

```c
const FontInfo *font = &Fonts[FONT_INTER_MEDIUM_12];
const FontGlyph *glyph = &font->glyphs[ch - font->first_char];
unsigned stride = (glyph->width + 1U) / 2U;
uint8_t packed = font->data[glyph->offset + y * stride + x / 2];
uint8_t coverage = (x & 1U) ? packed & 0x0F : packed >> 4;
```

Gli ID enum seguono l'ordine del JSON, non sono identificatori persistenti.
Il renderer riceve caratteri a un byte, non UTF-8: il grado si passa con `"\xB0"`.
Un carattere fuori dall'intervallo del font viene rifiutato dal renderer.

## Uso dal firmware

```c
ST7789_TextSize size;
ST7789_MeasureText("SPEED", FONT_INTER_MEDIUM_12, &size);

ST7789_WriteTextField(27, 145, 60, "SPEED", FONT_INTER_MEDIUM_12,
                      ST7789_TEXT_CENTER, WHITE, BLACK);
```

MeasureText restituisce larghezza massima delle righe e altezza complessiva,
includendo gli avanzamenti, gli spazi esportati e gli eventuali overhang.
Non applica il wrapping del display. Testo vuoto: dimensioni 0x0.
WriteTextField accetta una sola riga e la allinea a sinistra, al centro o a
destra in un'area larga un numero di pixel. Cancella tutta l'area per evitare
residui al cambio testo. Se il testo non entra restituisce INVALID_ARGUMENT,
senza troncare o ridurre il font. Il testo deve restare invariato fino a IDLE.

## Colore e costo a runtime

Il renderer prepara una palette di 16 RGB565 una volta per scritta, combinando
il colore del testo con il colore dello sfondo. Per ogni pixel legge soltanto
la copertura e il colore corrispondente. La palette occupa 32 byte di RAM.
La copertura viene composta temporaneamente nel buffer DMA libero, poi
convertita in RGB565 prima di pubblicarlo; nessun framebuffer aggiuntivo.
Gli overhang sovrapposti conservano la copertura maggiore.

Le bitmap richiedono circa quattro volte i bit del precedente formato binario
(il rapporto esatto dipende dal padding di riga). Metriche, misurazione,
centratura, allineamento e slot tabulari dei numeri restano gli stessi.
Il formato 1 bpp non viene mantenuto: rigenerare tutti i font con questo script.
