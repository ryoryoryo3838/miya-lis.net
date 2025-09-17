echo "dune building...";
echo "";
if [ -d "_build" ]; then
  echo "dune build already executed";
  echo "";
else
  npm run build;
fi;

wait;

echo "vite building...";
echo "";
npm run bundle; # build into /dist

echo "";
case "$@" in
  --local)
    echo "wrangler local deploying...";
    npx wrangler pages deploy;; #local deploy
  --public)
    echo "wrangler public local deploying...";
    npx wrangler pages deploy --project-name miya-list;; #local deploy
  *)
    echo "$@";
    echo "Error";
    exit 1;;
esac

wait;

echo "removing /dist"
echo ""

rm dist -fr
