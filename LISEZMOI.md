# Fadelpsaume - application Android (APK)

Comme Remi Vortex : une vraie application, qui reste active quand Termux est fermé.

## Étapes (une seule fois)
1. Crée un compte gratuit sur github.com (pseudo + mot de passe).
2. Crée un dépôt : bouton « + » > New repository > nom `fadelpsaume` > Create.
3. Crée un jeton : Settings > Developer settings > Personal access tokens > Tokens (classic) > Generate new token, coche `repo` et `workflow`, copie-le.
4. Dans Termux : `pkg install -y tar` puis
   `tar xzf Fadelpsaume-android.tar.gz && cd fadelpsaume-android && bash push.sh TONPSEUDO fadelpsaume TONJETON`
5. Sur github.com/TONPSEUDO/fadelpsaume > Actions : attends ~10 min (coche verte).
6. Onglet Releases (à droite) > télécharge `Fadelpsaume.apk` > installe (autorise « sources inconnues »).

Si la coche est rouge : ouvre l'étape en erreur, copie les dernières lignes et envoie-les moi.

## Nouveautés
- Compatible avec presque tous les serveurs : TCP, WebSocket, gRPC, HTTP/2, HTTPUpgrade, XHTTP, mKCP, TLS, Reality ; proxy + payload ; Shadowsocks avec WebSocket.
- Couleurs douces pour les yeux, connexion plus fluide.

## Huawei
Réglages > Batterie > Lancement d'applications > Fadelpsaume > gérer manuellement (tout activer).
