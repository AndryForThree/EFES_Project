# Steering Lab

Simulatore parametrico locale di un quadrilatero di sterzo, con staffe rigide e ruote reali nella vista dall'alto. **Python + NumPy, Streamlit e Plotly**, senza account, database o servizi cloud.

Implementa i primi quattro traguardi della specifica: nucleo matematico, simulazione interattiva, diagnostica e ricerca dimensionale. **La motorizzazione non è implementata**: è il successivo traguardo indipendente, dopo la validazione del meccanismo passivo.

## Avvio su Linux

Consigliato Python 3.12. Dalla cartella `steering-simulator`:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
./run.sh
```

Apri **http://localhost:8501**. Per cambiare porta: `./run.sh --server.port 8502`.
Nel workspace di consegna l'ambiente `.venv` è già preparato; basta `./run.sh`.
L'installazione iniziale richiede accesso a PyPI. Dopo l'installazione l'app funziona localmente, senza connessione esterna.
Il server è vincolato a `127.0.0.1`; la raccolta delle statistiche Streamlit è disattivata.

Verifiche automatiche essenziali, con output breve:

```bash
.venv/bin/python -m pytest -q
```

Le versioni verificate nell'ambiente di sviluppo sono NumPy 1.26.4, Streamlit 1.66.0, Plotly 6.9.0, PyArrow 19.0.1 e Pytest 9.1.1. PyArrow è limitato a una serie compatibile con NumPy 1.x. SciPy non è necessario per questo traguardo: chiusura e punti morti si risolvono geometricamente, mentre la ricerca è una griglia limitata.

## Primo utilizzo

1. Nella scheda **Simulazione**, muovi θ SX oppure premi **Avvia**. La ruota DX viene sempre calcolata dal vincolo rigido.
2. Le dimensioni iniziali sono un parallelogramma con interasse 180 mm, bracci 25 mm, entrambi rivolti al retro, e tirante 180 mm. A ±25° le due staffe ruotano dello stesso angolo; T percorre un arco.
3. Apri gli espansori nella barra laterale per cambiare staffe, posizione delle ruote, materiali, quote Z e obiettivi. Gli offset ruota sono vettori indipendenti dalla direzione dei bracci.
4. La modalità simmetrica specchia X e conserva Y. L'orientamento del braccio destro è π−α SX: **90° su entrambi i lati significa entrambi verso il retro**, non bracci opposti.
5. Il tirante è indipendente. Dopo una modifica geometrica, l'app avvisa se la posa nominale non chiude. **Calcola tirante per posa zero** applica esplicitamente la nuova lunghezza e seleziona il ramo coerente.
6. Metti in pausa o rilascia lo slider per acquisire la posa. In **Risposta cinematica**, premi **Calcola grafici e diagnostica**: una barra di avanzamento accompagna il calcolo dei sei grafici e della verifica degli ingombri. L'indicatore rappresenta la posa acquisita; i risultati restano fermi finché non richiedi una nuova analisi.
7. **Esplora progetti** valuta l'intervallo obiettivo e confronta liste di lunghezze, orientamenti e interassi. I candidati conservano materiali, ruote e quote Z; il tirante neutro viene calcolato per ogni candidato. Nessuno viene applicato senza il relativo comando.
8. **File e Onshape** permette salvataggio/caricamento JSON, export CSV (pulsante **Prepara risposta CSV**) e un elenco di variabili CAD da trasferire manualmente. Dopo un'analisi, la vista della posa acquisita nella scheda Risposta cinematica conserva l'esportazione SVG di Plotly.

### Animazione fluida e analisi separate

Il movimento è disegnato su un canvas locale tramite `requestAnimationFrame`, sincronizzato con il refresh del browser (tipicamente 60 Hz, dipendente dal dispositivo). Il browser risolve esattamente le intersezioni dei cerchi a ogni fotogramma: **nessuna interpolazione che allunghi le aste**. Python invia i parametri e le frontiere analitiche del ramo solo quando cambia il progetto. Non ci sono chiamate a Python, aggiornamenti Streamlit o ricostruzioni Plotly durante l'animazione.

Avvia/Pausa, slider, velocità, zoom, spostamento della vista e opzioni grafiche funzionano direttamente nel browser. Pausa, reset e rilascio dello slider inviano una singola posa a Python per l'eventuale analisi. I grafici, il controllo degli ingombri, la valutazione completa del progetto e il CSV si calcolano soltanto con i rispettivi pulsanti, con indicatore di caricamento. Cambiando parametri vengono invalidati i risultati precedenti e la simulazione riparte ferma dalla posa zero. I controlli dei punti morti e del ramo restano attivi durante il movimento; gli ingombri fisici si verificano nella diagnostica su richiesta.

Il piccolo nucleo JavaScript dell'animazione replica la chiusura esatta e viene confrontato con il nucleo Python nei test di parità, incluse geometrie asimmetriche e i due rami. Non richiede librerie esterne né download dal browser. Gli inviluppi e le traiettorie vengono preparati una volta per geometria, non ricalcolati a ogni fotogramma.

### Il progetto iniziale non è pronto da costruire

Le quote iniziali riproducono quelle richieste. Il modello aggiunge ipotesi **esplicite ed editabili**: ruote 60 × 18 mm; tirante 10 × 2 mm; supporti orizzontali 10 × 2 mm; rondelle Ø9 × 1 mm, distanziali 1 mm, teste vite Ø7 mm.

Z=0 è un riferimento arbitrario; le staffe sono da Z=2 a 4, i bracci da 4 a 6, il tirante da 8 a 10 e gli assi ruota a Z=8. Queste quote non erano definite dalla specifica e **non sono misure verificate sul prototipo**.

La basetta è stata rimossa dal simulatore: nessun contorno, parametro, controllo di interferenza, vincolo di ottimizzazione o variabile CAD riguarda il supporto. I perni restano fissi nelle loro coordinate; la struttura che li sostiene si progetta successivamente in CAD. Le interferenze fra componenti del meccanismo continuano a essere verificate. `docs/specification.md` conserva la specifica originale storica, antecedente a questa modifica.

## Modello matematico

Lunghezze in **mm**, angoli interni e JSON in **radianti**, visualizzazione ed export CAD/CSV in **gradi**. X positivo verso destra, Y positivo verso il retro, fronte −Y. La visualizzazione pone +Y verso il basso e mantiene rapporto X:Y=1:1, con limiti indipendenti dall'angolo attuale.

```text
A SX = (−d/2, 0)                     A DX = (+d/2, 0)
b_i = L_i (cos α_i, sin α_i)          c_i = (offset_x_i, offset_y_i)
B_i = A_i + R(θ_i) b_i               C_i = A_i + R(θ_i) c_i
forward_i = R(θ_i + heading_offset_i) (0, −1)
F = |B DX − B SX|² − t² = 0
```

Per ogni θ SX, le intersezioni dei cerchi `(A DX, L DX)` e `(B SX, t)` determinano tutte le possibili pose. Il calcolo dell'altezza dell'intersezione usa una fattorizzazione di tipo Erone per ridurre la cancellazione vicino alla tangente. Nessuna ottimizzazione o deformazione delle aste è usata per ottenere la chiusura.

### Rami e movimento

Il ramo ± è il segno del prodotto vettoriale `(B SX − A DX) × (B DX − A DX)`. Il ramo −1 contiene la posa iniziale del parallelogramma. Il ramo non significa universalmente “aperto” o “incrociato”: dipende dalla geometria.

Il selettore di ramo è esplicito. Durante il moto, `BranchTracker` conserva il segno e svolge θ DX rispetto alla posa precedente. Prima di accettare una variazione, cerca tutte le frontiere geometriche nell'intervallo attraversato, usando:

```text
h² = d² + L SX² − 2 d L SX cos(θ SX + α SX)
h = L DX + t          oppure          h = |L DX − t|
```

Un salto dello slider non può saltare indisturbato una singolarità o una zona impossibile. Il movimento viene rifiutato, con un avviso che distingue **angolo richiesto** e **ultima posa valida visualizzata**. È possibile ritornare verso la posa precedente. Adottare esplicitamente una nuova posa di montaggio, cambiare ramo, modificare geometria o richiamare la posa zero reinizializza la continuità: non rappresenta un percorso fisico attraverso il punto morto.

Cerchi coincidenti: angolo DX indeterminato e nessun risultato inventato. Cerchi concentrici diversi, geometria impossibile e aste nulle/negative: errore esplicito. Alla tangente c'è una singola posa con ramo 0; l'animazione si arresta. Il campionamento dei grafici aggiunge le frontiere analitiche e separa i tratti di curva.

### Diagnostica

```text
dvec = B DX − B SX
B'_i = J (B_i − A_i)
k = (dvec · B' SX) / (dvec · B' DX)
T = (1−λ) B SX + λ B DX
dT/dθ SX = (1−λ) B' SX + λ k B' DX
```

Le derivate di T sono **mm/rad**, non mm/°. Il rapporto cinematico è rad/rad (equivalente a °/°). La differenza fra ruote è la differenza degli heading, ricondotta a [−π,π], non la differenza degli orientamenti geometrici dei bracci α.

Tolleranza di lunghezza: `1e-10 × max(d, t, L SX, L DX)`. La trasmissione normalizzata è `|dvec · B'_i| / (t L_i)`. La soglia numerica è 1e-9; la soglia ingegneristica predefinita è **0.05**, modificabile. Presso il punto morto di uscita k e le derivate di T sono omessi, anche nei grafici e nel CSV. Il lato ingresso ha un allarme separato di trasmissione inefficace.

La distanza dal punto morto è la distanza angolare in θ SX dalla più vicina tangente o coincidenza dei cerchi, calcolata nell'intero periodo; è infinita quando tali frontiere non esistono. Non è una distanza spaziale tra pezzi. È mostrato anche il margine radiale `min(r+t−h, h−|r−t|)` in mm.

## Ingombri e costruibilità

- Rettangoli orientati per piattine e gomme; le lunghezze delle piattine includono il margine oltre ciascun foro.
- La staffa è rappresentata dalla piattina di comando e dal supporto rigido A–C. La piega verticale della staffa a L non è ricostruita in 3D.
- Confronto dei poligoni tramite assi separanti e distanza bordo-bordo; filtro preliminare tramite bounding box.
- Quote Z rappresentate da intervalli. Il volume della ruota è un prisma conservativo (asse ± raggio in Z), non il volume esatto di un pneumatico.
- Rondelle/teste vite: impronta di un poligono circoscritto a 16 lati, altezza modellata della rondella. Altezza delle teste e volume dei gambi passanti non sono ricostruiti.
- Il gioco minimo è confrontato con la distanza fra prismi. I casi sovrapposti in XY ma sufficientemente separati in Z sono distinti dalle possibili interferenze.
- Le coppie di accoppiamento intenzionale sono escluse: braccio–tirante dello stesso lato, braccio–staffa, staffa–propria ruota, perno–propria staffa/braccio e giunto–proprio braccio/tirante. **Gli sfregamenti di tali coppie non sono verificati lungo l'intera geometria**. Una regola separata richiede spazio fra braccio e tirante per rondella e distanziale.
- Controlli elementari: foro più grande del perno, materiale ai bordi della piattina. Non sono calcoli di resistenza o tolleranza meccanica.

Le traiettorie e l'area spazzata sono visualizzate mediante contorni campionati (nessuna unione continua certificata). La valutazione usa 61 pose, la ricerca 41, oltre alle frontiere analitiche. Piccole interferenze fra campioni possono sfuggire. Ogni risultato distingue validità geometrica, condizionamento cinematico, regole costruttive, ingombri e obiettivi.

La ricerca accetta al massimo 200 candidati, confronta bracci speculari, mantiene gli offset delle ruote come vincoli. Richiede sterzata concorde, raggiungimento dei due estremi DX entro una tolleranza del 2%, differenza heading e rapporto nei limiti e distanza dai punti morti. Gli ingombri sono controllati per tutti i campioni validi: non basta un ampio angolo di sterzata per rendere un candidato adatto. Con quote Z disattivate l'esito ingombri resta non conclusivo.

## Configurazioni e CAD

`configs/default.json` contiene la configurazione iniziale. Il formato è versionato (`schema_version: 2`) e include unità, geometria completa, quote Z, obiettivi, intervallo visualizzato, λ, simmetria e ramo selezionato. Gli angoli nel JSON sono in radianti. I vecchi file dello schema 1 sono rifiutati esplicitamente, senza conversioni automatiche o parametri nascosti. Il caricamento controlla finitezza, intervalli e coerenza della simmetria; non esegue codice dal file. La posa temporanea e lo stato play/pausa non sono dimensioni del progetto e non vengono salvati.

L'export Onshape elenca nomi, valori, unità ed espressioni `#Nome_variabile`; distingue l'interasse fra fori dalla lunghezza di taglio. Non esiste alcuna connessione automatica a Onshape. Procedura suggerita:

1. Crea le variabili nel Part Studio usando i nomi esportati.
2. Posiziona A SX/DX a ±`#Interasse_sterzo/2` e realizza i bracci con interassi `#L_braccio_SX/DX`.
3. Usa i vettori offset e gli orientamenti per posizionare correttamente ruote e staffe, senza imporre la collinearità A–B–C.
4. Usa `#L_SteeringRod` come distanza fra i due centri dei giunti rotanti.
5. Fissa i perni alle coordinate previste e progetta il supporto in CAD; imponi connessioni rigide staffa–braccio e rotanti ai quattro giunti. Controlla il ramo iniziale e non forzare un moto lineare del tirante.

## Architettura

```text
app.py                      interfaccia e analisi tecniche su richiesta
steering/parameters.py      dataclass immutabili, unità, JSON e validazione
steering/geometry.py        rotazioni, poligoni, intersezioni di cerchi
steering/kinematics.py      soluzione esatta, ramo, continuità, campionamento
steering/singularities.py   rapporto, velocità, margini e punti morti
steering/clearances.py      ingombri 2.5D e regole geometriche di costruzione
steering/optimization.py    valutazione e ricerca limitata di candidati
steering/export.py          variabili CAD e CSV
visualization/              vista dall'alto e sei grafici diagnostici
visualization/browser/      animazione canvas locale e chiusura esatta JavaScript
visualization/browser_motion.py  collegamento del canvas a Streamlit
configs/default.json       parametri iniziali
tests/                     invarianti geometrici e controlli numerici mirati
```

Per usare il nucleo senza GUI:

```python
import math
from steering.parameters import Parameters
from steering.kinematics import BranchTracker
from steering.singularities import diagnose

p = Parameters()
motion = BranchTracker(p)
pose = motion.move(math.radians(25))
if pose is not None:
    print(math.degrees(pose.theta_right), diagnose(p, pose).ratio)
```

I test coprono i casi richiesti del modello passivo: parallelogramma neutro e in rotazione, conservazione della lunghezza, rigidità A/B/C, impossibilità, tangenti, centri coincidenti, continuità dei due rami, rifiuto dei salti oltre singolarità, scalatura, bracci da 40 mm, asimmetria, derivate contro differenze finite, offset heading, JSON e distinzione degli ingombri in Z.

## Limiti e fase motore

Non sono calcolati forze, attrito, deformazioni, sospensioni, dinamica di rotolamento, gioco reale, resistenza o coppia motore. Il primo modello non implementa Ackermann. Le indicazioni di costruibilità richiedono una verifica meccanica reale.

Il JGA25-370 è descritto dalla specifica come 12 V e circa 58 RPM, senza encoder. Non vengono inventate dimensioni dell'albero, coppia o montaggi. Per una futura biella-manovella, la posa passiva e T sono già accessibili dal nucleo: l'attuatore dovrà aggiungere `Q = M + r(cos φ, sin φ)` e `|T−Q|² = s²`, con selezione/continuità dei propri rami e intervallo motore consentito. I giri completi non sono garantiti e occorreranno feedback di posizione o riferimenti/finecorsa adeguati.

Riferimenti software: [Streamlit fragments](https://docs.streamlit.io/develop/api-reference/execution-flow/st.fragment), [Streamlit AppTest](https://docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest). Le equazioni cinematiche derivano dalla specifica fornita con il progetto.
