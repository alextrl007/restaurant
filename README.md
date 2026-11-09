# Cine plătește? (rotația plăților la restaurant)

Aplicație mică (Python + SQLite, un singur container Docker) care ține evidența ieșirilor și arată al cui e rândul la plată.

## Regula

Fiecare are un **sold**:
- plătești la o masă cu *n* persoane: `+(n−1)`
- mănânci pe banii altcuiva: `−1`
- lipsești: nu se schimbă nimic

La o ieșire plătește, dintre cei prezenți, cel cu **soldul cel mai mic**. La egalitate se trage la sorți, iar tragerea se salvează în istoric. Cu toți 6 prezenți, regula e echivalentă cu „plătești după ce ai mâncat 5 mese pe banii altora". Soldurile se calculează din istoric, deci ștergerea unei ieșiri greșite le recalculează corect.

## Deploy pe mașina de la Hostinger

Pe VPS trebuie să existe Docker cu Docker Compose.

```bash
# 1. copiază folderul pe server (de pe calculatorul tău)
scp -r restaurant-rota user@IP_VPS:~/

# 2. pe server
cd ~/restaurant-rota
cp .env.example .env
nano .env                      # setează GROUP_PIN
docker compose up -d --build
```

Aplicația rulează pe `http://IP_VPS:8080`. Dacă portul e blocat, deschide-l din firewall-ul Hostinger.

### HTTPS cu domeniu (recomandat, ca să meargă bine de pe telefon)

1. Creează o înregistrare DNS `A` (de ex. `rota.exemplu.ro`) către IP-ul VPS-ului.
2. În `.env` setează `DOMAIN=rota.exemplu.ro` și `BIND=127.0.0.1`.
3. Pornește: `docker compose --profile https up -d --build`

Caddy obține singur certificatul. Porturile 80 și 443 trebuie să fie libere pe server. Dacă ai deja Nginx, Traefik sau Nginx Proxy Manager, nu folosi profilul `https`: pune `BIND=127.0.0.1` și fă proxy către `127.0.0.1:8080`.

## Întreținere

- **Actualizare:** copiază fișierele noi, apoi `docker compose up -d --build`. Datele rămân în volumul `rota_data`.
- **Backup:** după autentificare, `/api/export` returnează tot istoricul ca JSON. Sau copiază baza de date:
  `docker compose cp app:/data/rota.db ./rota-backup.db`
- **Schimbare PIN:** modifici `GROUP_PIN` în `.env` și rulezi `docker compose up -d`. Toți vor trebui să se autentifice din nou.
- **Schimbare nume:** variabila `MEMBERS` din `.env` (nume separate prin virgulă). Dacă schimbi un nume după ce există istoric, ieșirile vechi cu numele vechi nu se mai contabilizează.
- **Log-uri:** `docker compose logs -f app`

## Securitate

Accesul se face cu un PIN comun (cookie valabil un an, maxim 10 încercări greșite la 10 minute per adresă IP). E gândit pentru un grup de prieteni, nu pentru date sensibile. Pagina conține doar nume, date și restaurante.
