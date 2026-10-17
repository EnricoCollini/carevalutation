# Calcolatore auto

Applicazione per stimare il costo di possesso di un'automobile e valutarne la sostenibilità nel proprio bilancio. Interfaccia Angular in italiano, API Flask, database MySQL e Nginx. Il modello di calcolo segue [il protocollo completo](Protocollo_completo_valutazione_auto.md).

La valutazione distingue il costo economico dell'auto dalle uscite mensili. Considera il valore recuperabile alla vendita, gli interessi e il debito residuo; così rata e svalutazione non vengono sommate due volte. Le valutazioni vengono salvate e possono essere riprese dall'utente.

## Avvio con Docker Compose

Requisiti: Docker Engine con il plugin `docker compose`. Sul computer attuale Docker potrebbe non essere installato; lo stesso progetto potrà essere avviato sulla VPS in seguito.

1. Verificare che esista `.env`. In questa cartella ne è stato generato uno con segreti casuali; se si trasferiscono solo i sorgenti, copiare `.env.example` in `.env` e sostituire **tutte** le password di esempio e `SECRET_KEY` con valori lunghi e casuali. Non pubblicare `.env`.
2. Nella cartella del progetto, eseguire `docker compose up --build -d`.
3. Aprire `http://localhost:8080` (oppure la porta impostata in `HTTP_PORT`).

Nginx espone l'applicazione e inoltra `/api/` a Flask. MySQL è raggiungibile solo dalla rete privata Compose. I dati rimangono nel volume `mysql_data` anche quando i container vengono riavviati.

Per vedere lo stato: `docker compose ps`. Per i log: `docker compose logs -f`. Per fermare: `docker compose down`. Quest'ultimo comando conserva il volume MySQL; `down -v` lo eliminerebbe e **non** va usato se servono i dati.

## Utilizzo

Si entra con un nickname e una password scelti dall'utente e si possono creare e salvare più valutazioni. La password serve a proteggere il profilo: chi non la conosce non accede alle valutazioni e al reddito salvati. Per ritrovare le valutazioni su un altro browser basta inserire lo stesso nickname e la stessa password. Se la password viene dimenticata, il profilo non è recuperabile dall'interfaccia.

Per ogni auto si indicano prezzo proposto, nuovo/usato, chilometri attuali e annui, anni di possesso, eventuale valutazione dell'auto data in permuta, gestione, assicurazione, gomme, tagliandi, revisione, finanziamento e dati del bilancio. L'app mostra il costo economico mensile, la cassa necessaria, la rivendita stimata, la composizione dei costi e i criteri di sostenibilità.

La rivendita futura è un'ipotesi esplicita, modificabile dall'utente. Per un usato si può inoltre indicare il prezzo originario da nuova: l'app produce una fascia indicativa del valore attuale basata su età e chilometri e la confronta con il prezzo richiesto. Il calcolo del costo usa comunque il prezzo realmente concordato. Non è stata confermata un'API italiana completa per prezzi modello/km gratuitamente accessibile senza credenziali; i fornitori e i dati consultati sono documentati nel protocollo. Le cifre non inserite come prezzi effettivi sono stime e vanno controllate prima di un acquisto.

## Sviluppo e struttura

- `frontend/`: applicazione Angular, installabile come PWA (manifest + service worker; le chiamate `/api/` non vengono messe in cache).
- `backend/`: API Flask e modello di calcolo.
- `docker/`: immagini e configurazione Nginx.
- `compose.yaml`: orchestrazione di web, API e MySQL.
- `Protocollo_completo_valutazione_auto.md`: formule, ipotesi e ricerca delle fonti.

Per eseguire in locale senza Docker si possono avviare separatamente Angular e Flask con SQLite per la fase di sviluppo; vedere le indicazioni dentro `backend/` e `frontend/` se presenti. In produzione usare MySQL.

## Pubblicazione successiva su VPS

Prima di aprire il servizio su Internet, configurare un dominio e HTTPS con un certificato valido, password segrete, backup periodici del volume MySQL e aggiornamenti delle immagini. La procedura concreta sulla VPS Aruba verrà definita quando sarà disponibile l'ambiente: questo progetto non richiede modifiche preventive sul server.

L'accesso con nickname e password è pensato per uso personale e semplice. Prima di un'eventuale apertura pubblica, vanno valutati ulteriori controlli sugli accessi e sui dati finanziari. Non inserire dati sensibili nei nickname e non condividere la password di accesso.
