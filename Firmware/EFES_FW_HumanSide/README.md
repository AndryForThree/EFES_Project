# EFES firmware — Human Side

La repository conserva la configurazione CubeMX e il codice personalizzato.
Driver HAL/CMSIS, inizializzazioni delle periferiche, startup, linker e file
CMake generati si ricreano localmente: non sono versionati.

## Ricreare il progetto dopo un clone

1. Usare STM32CubeMX e il pacchetto firmware indicati nel file `.ioc`.
   La configurazione attuale riporta CubeMX **6.18.1** e
   **STM32Cube FW_G4 V1.6.3**. Per riprodurre lo stesso progetto, evitare di
   migrare automaticamente il pacchetto a una versione diversa.
2. Aprire `EFES_FW_HumanSide.ioc` e generare il codice con il target **CMake**.
   La generazione ricrea `Drivers/`, gli altri file `Core/`, `cmake/`,
   `CMakePresets.json`, startup e linker.
3. Conservare il `CMakeLists.txt` principale della repository: include i sorgenti
   personalizzati ST7789 e UI. Nel file è esplicitamente indicato che non viene
   rigenerato alle generazioni successive.
4. Conservare `Core/Src/main.c` e le sue sezioni `USER CODE`.
   L'opzione CubeMX `KeepUserCode` è già attiva nel `.ioc`.
5. Dopo la generazione, configurare/compilare con i preset CMake generati e la
   toolchain ARM. Il clone da solo non contiene tutti i sorgenti necessari
   alla compilazione: il passaggio di generazione è obbligatorio.

## File da versionare

- `.ioc`: pin, clock, periferiche, DMA e opzioni della generazione.
- `CMakeLists.txt`: integrazione dei sorgenti custom.
- `Core/Src/main.c`: inizializzazione, superloop e instradamento delle callback HAL.
- `customLibs/ST7789/`: libreria display, font, configurazione e documentazione.
- `customLibs/UI/`: stato, eventi, pagine e timer TIM6 dedicato alla UI.
- `.clangd`, `.gitignore` e questo documento.

Le regole ignorano le altre directory e i sorgenti generati da CubeMX. Non
aggiungere codice personalizzato in un file ignorato: non arriverebbe sul PC
di chi clona. Per nuove librerie custom, usare una directory esterna a `Core/`
(per esempio `App/` o `Libraries/`) e aggiungerla al CMakeLists principale;
queste directory vengono versionate normalmente. Se si personalizzano startup,
linker, toolchain o altri file finora generati, aggiornare prima il `.gitignore`.

Le directory di build e i prodotti compilati restano esclusi. Ignorare o
rimuovere un file dall'indice Git non lo cancella dal disco.

Per il comportamento della libreria e delle API asincrone, vedere
[`customLibs/ST7789/README.md`](customLibs/ST7789/README.md).
Per il modulo UI vedere [`customLibs/UI/README.md`](customLibs/UI/README.md).
