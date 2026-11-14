#!/data/data/com.termux/files/usr/bin/bash
# Envoie le projet sur GitHub (qui fabrique l'APK). Usage : bash push.sh PSEUDO NOM_DEPOT
set -e
[ $# -ge 2 ] || { echo "Usage : bash push.sh PSEUDO NOM_DEPOT"; exit 1; }
TOKEN="$3"
if [ -z "$TOKEN" ]; then
  printf "Colle ton jeton GitHub (il reste invisible) puis appuie sur Entree : "
  read -rs TOKEN
  echo
fi
[ -n "$TOKEN" ] || { echo "Jeton vide."; exit 1; }
command -v git >/dev/null || pkg install -y git
cd "$(dirname "$0")"
rm -rf .git
git init -q -b main
git config user.name "$1"; git config user.email "$1@users.noreply.github.com"
git add -A && git commit -q -m "Fadelpsaume Android"
git remote add origin "https://$1:$TOKEN@github.com/$1/$2.git"
if ! git push -f origin main >"$HOME/.push.log" 2>&1; then
  sed "s/$TOKEN/***/g" "$HOME/.push.log"; rm -f "$HOME/.push.log"; git remote remove origin
  echo "ECHEC de l'envoi (voir ci-dessus)."; exit 1
fi
rm -f "$HOME/.push.log"; git remote remove origin
echo "FINI. Va sur github.com/$1/$2 > Actions, attends ~10 min, puis Releases pour l'APK."
